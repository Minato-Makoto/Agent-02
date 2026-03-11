"""
AgentForge — System tools.

Tools:
- shell_command
- process_list

Security profile: strict-default allowlist with blocked-command precedence.
"""

import os
import shlex
import subprocess
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agentforge.tools import Tool, ToolRegistry, ToolResult
from agentforge.runtime_config import load_shell_policy_config, load_tool_timeout_config

logger = logging.getLogger(__name__)


def register(registry: ToolRegistry, skill_name: str = "system") -> None:
    tools = [
        Tool(
            name="shell_command",
            description="Execute a shell command. Returns stdout, stderr, and exit code.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute."},
                    "cwd": {"type": "string", "description": "Working directory."},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (1-120).",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
            execute_fn=_shell_command,
        ),
        Tool(
            name="process_list",
            description="List running processes.",
            input_schema={
                "type": "object",
                "properties": {"filter": {"type": "string", "description": "Name filter."}},
            },
            execute_fn=_process_list,
        ),
    ]
    registry.register_skill(skill_name, tools)


ALLOWED_COMMANDS = {
    "ls",
    "dir",
    "cat",
    "type",
    "head",
    "tail",
    "wc",
    "grep",
    "findstr",
    "find",
    "pwd",
    "mkdir",
    "cp",
    "copy",
    "move",
    "mv",
    "python",
    "py",
    "pip",
    "npm",
    "node",
    "npx",
    "git",
    "echo",
    "set",
    "env",
    "whoami",
    "hostname",
    "date",
    "time",
    "ps",
    "tasklist",
    "lsof",
    "netstat",
    "ping",
    "curl",
    "wget",
    "touch",
    "tree",
    "du",
    "df",
    "file",
    "stat",
    "chmod",
    # PowerShell cmdlets for safe local inspection workflows.
    "get-childitem",
    "get-content",
    "select-string",
    "where-object",
    "select-object",
    "sort-object",
    "measure-object",
    "test-path",
    "join-path",
    "get-filehash",
}

BLOCKED_COMMANDS = {
    "rm",
    "del",
    "rmdir",
    "format",
    "mkfs",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "dd",
    "fdisk",
    "parted",
}

STDOUT_LIMIT = 5000
STDERR_LIMIT = 2000

PYTHON_BLOCKED_FLAGS = {"-c", "-m", "-i", "-"}
PIP_ALLOWED_SUBCOMMANDS = {"list", "show", "freeze", "help", "-v", "--version"}
NODE_BLOCKED_FLAGS = {"-e", "--eval", "-p", "--print", "-i", "--interactive", "-"}
NPX_ALLOWED_COMMANDS = {"playwright"}


def _workspace_root() -> Path:
    raw = os.environ.get("AGENTFORGE_WORKSPACE", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.cwd() / "workspace").resolve()


def _is_within_workspace(path: Path) -> bool:
    workspace = _workspace_root()
    try:
        path.resolve().relative_to(workspace)
        return True
    except ValueError:
        return False


def _split_command_segments(command: str) -> List[str]:
    """
    Split command string by shell control operators at top-level.

    Handles:
    - `|`, `||`, `&&`, `;`
    - quote contexts
    - subshell and command substitution depth `(...)`, `$(...)`
    """
    if not command:
        return []

    out: List[str] = []
    buf: List[str] = []
    quote: str = ""
    escape = False
    paren_depth = 0
    i = 0

    def flush():
        seg = "".join(buf).strip()
        if seg:
            out.append(seg)
        buf.clear()

    while i < len(command):
        ch = command[i]
        nxt = command[i + 1] if i + 1 < len(command) else ""

        if escape:
            buf.append(ch)
            escape = False
            i += 1
            continue

        if ch == "\\" and quote != "'":
            buf.append(ch)
            escape = True
            i += 1
            continue

        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
            i += 1
            continue

        if ch == "$" and nxt == "(":
            paren_depth += 1
            buf.append(ch)
            buf.append(nxt)
            i += 2
            continue

        if ch == "(":
            paren_depth += 1
            buf.append(ch)
            i += 1
            continue

        if ch == ")" and paren_depth > 0:
            paren_depth -= 1
            buf.append(ch)
            i += 1
            continue

        if paren_depth == 0:
            if ch == ";":
                flush()
                i += 1
                continue
            if ch == "|" and nxt == "|":
                flush()
                i += 2
                continue
            if ch == "&" and nxt == "&":
                flush()
                i += 2
                continue
            if ch == "|":
                flush()
                i += 1
                continue

        buf.append(ch)
        i += 1

    flush()
    return out


def _extract_command_name(segment: str) -> str:
    if not segment:
        return ""
    segment = segment.strip()
    if segment.startswith("(") and segment.endswith(")"):
        inner = segment[1:-1].strip()
        nested = _split_command_segments(inner)
        if not nested:
            return ""
        return _extract_command_name(nested[0])
    try:
        tokens = shlex.split(segment, posix=(sys.platform != "win32"))
    except ValueError:
        tokens = segment.split()
    if not tokens:
        return ""
    return _normalize_command_name(tokens[0])


def _tokenize_segment(segment: str) -> List[str]:
    try:
        tokens = shlex.split(segment, posix=(sys.platform != "win32"))
    except ValueError:
        tokens = segment.split()
    return tokens


def _normalize_command_name(raw_command: str) -> str:
    cmd = os.path.basename(raw_command).strip().lower()
    if cmd.endswith(".exe"):
        cmd = cmd[:-4]
    return cmd


def _validate_python_invocation(tokens: List[str]) -> Tuple[bool, str, str]:
    if len(tokens) <= 1:
        return False, "BLOCKED_PYTHON_INVOCATION", "Interactive python shell is not allowed"

    first_arg = tokens[1].strip()
    first_arg_lower = first_arg.lower()
    if first_arg_lower in PYTHON_BLOCKED_FLAGS or first_arg_lower.startswith("-c"):
        return (
            False,
            "BLOCKED_PYTHON_FLAG",
            f"Python flag '{first_arg}' is blocked. Inline code execution is not allowed.",
        )

    if first_arg_lower in {"-v", "--version", "-h", "--help"}:
        return True, "OK", ""

    if first_arg.startswith("-"):
        return (
            False,
            "BLOCKED_PYTHON_FLAG",
            f"Python flag '{first_arg}' is blocked for shell_command safety.",
        )

    script_path = Path(first_arg).expanduser()
    if not script_path.is_absolute():
        script_path = (Path.cwd() / script_path).resolve()
    else:
        script_path = script_path.resolve()

    if script_path.suffix.lower() != ".py":
        return (
            False,
            "BLOCKED_PYTHON_SCRIPT",
            "Only .py script execution is allowed for python command.",
        )

    if not _is_within_workspace(script_path):
        return (
            False,
            "BLOCKED_PYTHON_PATH",
            f"Python script must be inside workspace: {_workspace_root()}",
        )

    return True, "OK", ""


def _validate_pip_invocation(tokens: List[str]) -> Tuple[bool, str, str]:
    if len(tokens) <= 1:
        return False, "BLOCKED_PIP_SUBCOMMAND", "pip requires an explicit safe subcommand"
    sub = tokens[1].strip().lower()
    if sub not in PIP_ALLOWED_SUBCOMMANDS:
        return (
            False,
            "BLOCKED_PIP_SUBCOMMAND",
            f"pip subcommand '{sub}' is blocked. Allowed: {', '.join(sorted(PIP_ALLOWED_SUBCOMMANDS))}",
        )
    return True, "OK", ""


def _resolve_script_path(raw_path: str) -> Path:
    script_path = Path(raw_path).expanduser()
    if not script_path.is_absolute():
        script_path = (Path.cwd() / script_path).resolve()
    else:
        script_path = script_path.resolve()
    return script_path


def _validate_node_invocation(tokens: List[str]) -> Tuple[bool, str, str]:
    if len(tokens) <= 1:
        return False, "BLOCKED_NODE_INVOCATION", "Interactive node shell is not allowed"

    first_arg = tokens[1].strip()
    first_arg_lower = first_arg.lower()
    if first_arg_lower in NODE_BLOCKED_FLAGS or first_arg_lower.startswith("-e"):
        return (
            False,
            "BLOCKED_NODE_FLAG",
            f"Node flag '{first_arg}' is blocked. Inline code execution is not allowed.",
        )
    if first_arg_lower in {"-v", "--version", "-h", "--help"}:
        return True, "OK", ""
    if first_arg.startswith("-"):
        return (
            False,
            "BLOCKED_NODE_FLAG",
            f"Node flag '{first_arg}' is blocked for shell_command safety.",
        )

    script_path = _resolve_script_path(first_arg)
    if script_path.suffix.lower() not in {".js", ".mjs", ".cjs"}:
        return (
            False,
            "BLOCKED_NODE_SCRIPT",
            "Only .js/.mjs/.cjs script execution is allowed for node command.",
        )
    if not _is_within_workspace(script_path):
        return (
            False,
            "BLOCKED_NODE_PATH",
            f"Node script must be inside workspace: {_workspace_root()}",
        )
    return True, "OK", ""


def _validate_npx_invocation(tokens: List[str]) -> Tuple[bool, str, str]:
    if len(tokens) <= 1:
        return False, "BLOCKED_NPX_INVOCATION", "npx requires an explicit allowed command"

    # Allow trivial help/version probes.
    if len(tokens) == 2 and tokens[1].strip().lower() in {"-v", "--version", "-h", "--help"}:
        return True, "OK", ""

    cmd = ""
    for tok in tokens[1:]:
        candidate = tok.strip()
        if not candidate or candidate.startswith("-"):
            continue
        cmd = candidate.lower()
        break

    if not cmd:
        return False, "BLOCKED_NPX_COMMAND", "npx command is missing"
    if cmd not in NPX_ALLOWED_COMMANDS:
        return (
            False,
            "BLOCKED_NPX_COMMAND",
            f"npx command '{cmd}' is blocked. Allowed: {', '.join(sorted(NPX_ALLOWED_COMMANDS))}",
        )
    return True, "OK", ""


def _validate_command_policy(command_name: str, tokens: List[str]) -> Tuple[bool, str, str]:
    if command_name in {"python", "py"}:
        return _validate_python_invocation(tokens)
    if command_name == "pip":
        return _validate_pip_invocation(tokens)
    if command_name == "node":
        return _validate_node_invocation(tokens)
    if command_name == "npx":
        return _validate_npx_invocation(tokens)
    return True, "OK", ""


def _extract_commands(command_string: str) -> List[str]:
    commands: List[str] = []
    for segment in _split_command_segments(command_string):
        name = _extract_command_name(segment)
        if name:
            commands.append(name)
    return commands


def _validate_command(command_string: str) -> Tuple[bool, str, str]:
    """
    Validate against strict allowlist.

    Returns tuple: (allowed, code, reason).
    """
    segments = _split_command_segments(command_string)
    if not segments:
        return False, "PARSE_ERROR", "Could not parse command"

    for segment in segments:
        tokens = _tokenize_segment(segment)
        if not tokens:
            return False, "PARSE_ERROR", "Could not tokenize command segment"

        cmd = _normalize_command_name(tokens[0])

        if cmd in BLOCKED_COMMANDS:
            return False, "BLOCKED_COMMAND", f"Command '{cmd}' is blocked for safety"
        if cmd not in ALLOWED_COMMANDS:
            return (
                False,
                "NOT_ALLOWED",
                "Command "
                f"'{cmd}' is not allowlisted. Use a safe command/cmdlet "
                f"from: {', '.join(sorted(ALLOWED_COMMANDS))}",
            )
        allowed, code, reason = _validate_command_policy(cmd, tokens)
        if not allowed:
            return False, code, reason

    return True, "OK", ""


def _sanitize_timeout(value: Any) -> int:
    try:
        t = int(value)
    except Exception:
        t = 30
    return max(1, min(120, t))


def _shell_command(args: Dict[str, Any]) -> ToolResult:
    command = str(args.get("command", "")).strip()
    cwd = args.get("cwd")
    timeout = _sanitize_timeout(args.get("timeout", 30))
    policy = load_shell_policy_config()
    workspace = _workspace_root()

    if not command:
        return ToolResult.error_result("Missing 'command'")

    allowed, code, reason = _validate_command(command)
    if not allowed:
        return ToolResult.error_result(f"SECURITY[{code}]: {reason}")

    resolved_cwd: Path | None = None
    if cwd:
        candidate = Path(str(cwd)).expanduser()
        if not candidate.is_absolute():
            base = workspace if policy.workspace_only else Path.cwd()
            candidate = (base / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if not candidate.is_dir():
            return ToolResult.error_result(f"SECURITY[INVALID_CWD]: Not a directory: {candidate}")
        if policy.workspace_only and not _is_within_workspace(candidate):
            return ToolResult.error_result(
                f"SECURITY[CWD_OUTSIDE_WORKSPACE]: cwd must be under workspace: {workspace}"
            )
        resolved_cwd = candidate
    elif policy.workspace_only:
        if not workspace.is_dir():
            return ToolResult.error_result(
                f"SECURITY[INVALID_WORKSPACE]: workspace directory not found: {workspace}"
            )
        resolved_cwd = workspace

    cwd_for_subprocess = str(resolved_cwd) if resolved_cwd is not None else None

    try:
        if sys.platform == "win32":
            shell_cmd = ["powershell", "-Command", command]
        else:
            shell_cmd = ["bash", "-c", command]

        result = subprocess.run(
            shell_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd_for_subprocess,
            env=os.environ.copy(),
        )

        return ToolResult(
            success=True,
            output={
                "stdout": result.stdout[:STDOUT_LIMIT],
                "stderr": result.stderr[:STDERR_LIMIT],
                "exit_code": result.returncode,
                "timed_out": False,
            },
        )
    except subprocess.TimeoutExpired:
        return ToolResult.error_result(f"SECURITY[TIMEOUT]: Command timed out after {timeout}s")
    except Exception as e:
        return ToolResult.from_exception(e, context="RUNTIME[EXEC_ERROR]", logger=logger)


def _process_list(args: Dict[str, Any]) -> ToolResult:
    name_filter = str(args.get("filter", "")).lower().strip()
    timeout_s = load_tool_timeout_config().process_list_s
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            lines = result.stdout.strip().split("\n")
            processes = []
            for line in lines[:50]:
                parts = line.strip().strip('"').split('","')
                if len(parts) < 5:
                    continue
                name = parts[0].strip('"')
                pid = parts[1].strip('"')
                mem = parts[4].strip('"')
                if not name_filter or name_filter in name.lower():
                    processes.append({"name": name, "pid": pid, "memory": mem})
        else:
            result = subprocess.run(
                ["ps", "aux", "--sort=-rss"],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            lines = result.stdout.strip().split("\n")[1:51]
            processes = []
            for line in lines:
                parts = line.split(None, 10)
                if len(parts) < 11:
                    continue
                name = parts[10]
                if not name_filter or name_filter in name.lower():
                    processes.append(
                        {
                            "name": name,
                            "pid": parts[1],
                            "cpu": parts[2],
                            "memory": parts[3],
                        }
                    )
        return ToolResult(success=True, output=processes)
    except Exception as e:
        return ToolResult.from_exception(e, context="process_list failed", logger=logger)
