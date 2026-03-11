"""
AgentForge — File Operations tools.

Tools: write_file, list_directory, search_files, file_info,
       move_file, copy_file, rename_path, make_directory, find_duplicates
"""

from __future__ import annotations

import datetime
import glob
import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

from agentforge.tools import Tool, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


def register(registry: ToolRegistry, skill_name: str = "file_operations") -> None:
    """Register file operation tools (excluding read_file — provided by bootstrap)."""
    tools = [
        Tool(
            name="write_file",
            description=(
                "Write content to a file inside workspace only. "
                "Creates the file if it doesn't exist, overwrites if it does."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path inside workspace (relative or absolute under workspace).",
                    },
                    "content": {"type": "string", "description": "Content to write."},
                },
                "required": ["path", "content"],
            },
            execute_fn=_write_file,
        ),
        Tool(
            name="list_directory",
            description="List files and subdirectories in a directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the directory."},
                    "recursive": {
                        "type": "boolean",
                        "description": "List recursively.",
                        "default": False,
                    },
                },
                "required": ["path"],
            },
            execute_fn=_list_directory,
        ),
        Tool(
            name="search_files",
            description="Search for files matching a glob pattern.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to search in."},
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. '*.py', '**/*.md').",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return.",
                        "default": 20,
                    },
                },
                "required": ["path", "pattern"],
            },
            execute_fn=_search_files,
        ),
        Tool(
            name="file_info",
            description="Get metadata about a file (size, modified date, type).",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Absolute path to the file."}},
                "required": ["path"],
            },
            execute_fn=_file_info,
        ),
        Tool(
            name="move_file",
            description="Move a file or directory inside the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path inside workspace."},
                    "destination": {
                        "type": "string",
                        "description": "Destination path inside workspace.",
                    },
                },
                "required": ["source", "destination"],
            },
            execute_fn=_move_file,
        ),
        Tool(
            name="copy_file",
            description="Copy a file or directory inside the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path inside workspace."},
                    "destination": {
                        "type": "string",
                        "description": "Destination path inside workspace.",
                    },
                },
                "required": ["source", "destination"],
            },
            execute_fn=_copy_file,
        ),
        Tool(
            name="rename_path",
            description="Rename a file or directory in place inside the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Existing file or directory path."},
                    "new_name": {"type": "string", "description": "New name without path separators."},
                },
                "required": ["path", "new_name"],
            },
            execute_fn=_rename_path,
        ),
        Tool(
            name="make_directory",
            description="Create a directory (and parents) inside the workspace.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Directory path to create."}},
                "required": ["path"],
            },
            execute_fn=_make_directory,
        ),
        Tool(
            name="find_duplicates",
            description=(
                "Find duplicate files by SHA-256 hash under a workspace directory. "
                "Report only; does not delete files."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root directory to scan."},
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum number of files to hash.",
                        "default": 5000,
                    },
                },
                "required": ["path"],
            },
            execute_fn=_find_duplicates,
        ),
    ]
    registry.register_skill(skill_name, tools)


def _resolve_workspace_root() -> Path:
    raw = str(os.environ.get("AGENTFORGE_WORKSPACE", "")).strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.cwd() / "workspace").resolve()


def _resolve_workspace_safe_path(raw_path: str, *, code: str) -> Path:
    workspace = _resolve_workspace_root()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise PermissionError(
            f"SECURITY[{code}]: Path must stay under workspace: {workspace}"
        ) from exc
    return resolved


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _write_file(args: Dict[str, Any]) -> ToolResult:
    path = args.get("path", "")
    content = str(args.get("content", ""))
    if not path:
        return ToolResult(success=False, output=None, error="Missing 'path'")
    try:
        safe_path = _resolve_workspace_safe_path(str(path), code="WRITE_OUTSIDE_WORKSPACE")
        _atomic_write_text(safe_path, content)
        return ToolResult(success=True, output=f"Written {len(content)} bytes to {safe_path}")
    except PermissionError as exc:
        return ToolResult(success=False, output=None, error=str(exc))
    except Exception as exc:
        return ToolResult.from_exception(exc, context="write_file failed", logger=logger)


def _list_directory(args: Dict[str, Any]) -> ToolResult:
    path = args.get("path", "")
    recursive = args.get("recursive", False)
    if not path or not os.path.isdir(path):
        return ToolResult(success=False, output=None, error=f"Not a valid directory: {path}")
    try:
        entries: List[Dict[str, Any]] = []
        if recursive:
            for root, dirs, files in os.walk(path):
                for name in dirs:
                    full = os.path.join(root, name)
                    entries.append({"name": os.path.relpath(full, path), "type": "directory"})
                for name in files:
                    full = os.path.join(root, name)
                    entries.append(
                        {
                            "name": os.path.relpath(full, path),
                            "type": "file",
                            "size": os.path.getsize(full),
                        }
                    )
        else:
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                entry: Dict[str, Any] = {
                    "name": name,
                    "type": "directory" if os.path.isdir(full) else "file",
                }
                if os.path.isfile(full):
                    entry["size"] = os.path.getsize(full)
                entries.append(entry)
        return ToolResult(success=True, output=entries)
    except Exception as exc:
        return ToolResult.from_exception(exc, context="list_directory failed", logger=logger)


def _search_files(args: Dict[str, Any]) -> ToolResult:
    path = args.get("path", "")
    pattern = args.get("pattern", "")
    if not path or not pattern:
        return ToolResult(success=False, output=None, error="Missing 'path' or 'pattern'")
    try:
        max_results = int(args.get("max_results", 20))
        search_pattern = os.path.join(path, pattern)
        matches = glob.glob(search_pattern, recursive=True)[: max(1, max_results)]
        return ToolResult(success=True, output=matches)
    except Exception as exc:
        return ToolResult.from_exception(exc, context="search_files failed", logger=logger)


def _file_info(args: Dict[str, Any]) -> ToolResult:
    path = args.get("path", "")
    if not path or not os.path.exists(path):
        return ToolResult(success=False, output=None, error=f"Path not found: {path}")
    try:
        stat = os.stat(path)
        info = {
            "path": os.path.abspath(path),
            "name": os.path.basename(path),
            "type": "directory" if os.path.isdir(path) else "file",
            "size": stat.st_size,
            "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created": datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(),
        }
        return ToolResult(success=True, output=info)
    except Exception as exc:
        return ToolResult.from_exception(exc, context="file_info failed", logger=logger)


def _move_file(args: Dict[str, Any]) -> ToolResult:
    source = str(args.get("source", "")).strip()
    destination = str(args.get("destination", "")).strip()
    if not source or not destination:
        return ToolResult.error_result("Missing 'source' or 'destination'")
    try:
        src = _resolve_workspace_safe_path(source, code="MOVE_OUTSIDE_WORKSPACE")
        dst = _resolve_workspace_safe_path(destination, code="MOVE_OUTSIDE_WORKSPACE")
        if not src.exists():
            return ToolResult.error_result(f"Source path not found: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return ToolResult(success=True, output=f"Moved: {src} -> {dst}")
    except PermissionError as exc:
        return ToolResult.error_result(str(exc))
    except Exception as exc:
        return ToolResult.from_exception(exc, context="move_file failed", logger=logger)


def _copy_file(args: Dict[str, Any]) -> ToolResult:
    source = str(args.get("source", "")).strip()
    destination = str(args.get("destination", "")).strip()
    if not source or not destination:
        return ToolResult.error_result("Missing 'source' or 'destination'")
    try:
        src = _resolve_workspace_safe_path(source, code="COPY_OUTSIDE_WORKSPACE")
        dst = _resolve_workspace_safe_path(destination, code="COPY_OUTSIDE_WORKSPACE")
        if not src.exists():
            return ToolResult.error_result(f"Source path not found: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        return ToolResult(success=True, output=f"Copied: {src} -> {dst}")
    except PermissionError as exc:
        return ToolResult.error_result(str(exc))
    except Exception as exc:
        return ToolResult.from_exception(exc, context="copy_file failed", logger=logger)


def _rename_path(args: Dict[str, Any]) -> ToolResult:
    path = str(args.get("path", "")).strip()
    new_name = str(args.get("new_name", "")).strip()
    if not path or not new_name:
        return ToolResult.error_result("Missing 'path' or 'new_name'")
    if "/" in new_name or "\\" in new_name:
        return ToolResult.error_result("new_name must not contain path separators")
    try:
        src = _resolve_workspace_safe_path(path, code="RENAME_OUTSIDE_WORKSPACE")
        if not src.exists():
            return ToolResult.error_result(f"Path not found: {src}")
        dst = src.with_name(new_name)
        if dst.exists():
            return ToolResult.error_result(f"Target already exists: {dst}")
        src.rename(dst)
        return ToolResult(success=True, output=f"Renamed: {src} -> {dst}")
    except PermissionError as exc:
        return ToolResult.error_result(str(exc))
    except Exception as exc:
        return ToolResult.from_exception(exc, context="rename_path failed", logger=logger)


def _make_directory(args: Dict[str, Any]) -> ToolResult:
    path = str(args.get("path", "")).strip()
    if not path:
        return ToolResult.error_result("Missing 'path'")
    try:
        dst = _resolve_workspace_safe_path(path, code="MKDIR_OUTSIDE_WORKSPACE")
        dst.mkdir(parents=True, exist_ok=True)
        return ToolResult(success=True, output=f"Directory ready: {dst}")
    except PermissionError as exc:
        return ToolResult.error_result(str(exc))
    except Exception as exc:
        return ToolResult.from_exception(exc, context="make_directory failed", logger=logger)


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _find_duplicates(args: Dict[str, Any]) -> ToolResult:
    root = str(args.get("path", "")).strip()
    max_files = max(1, int(args.get("max_files", 5000)))
    if not root:
        return ToolResult.error_result("Missing 'path'")
    try:
        root_path = _resolve_workspace_safe_path(root, code="SCAN_OUTSIDE_WORKSPACE")
        if not root_path.is_dir():
            return ToolResult.error_result(f"Not a valid directory: {root_path}")

        files: List[Path] = []
        for dir_path, _dir_names, file_names in os.walk(root_path):
            for name in file_names:
                files.append(Path(dir_path) / name)
                if len(files) >= max_files:
                    break
            if len(files) >= max_files:
                break

        buckets: Dict[tuple[str, int], List[Path]] = {}
        for file_path in files:
            try:
                size = file_path.stat().st_size
                file_hash = _hash_file(file_path)
            except OSError:
                continue
            key = (file_hash, size)
            buckets.setdefault(key, []).append(file_path)

        groups: List[Dict[str, Any]] = []
        for (file_hash, size), paths in sorted(buckets.items(), key=lambda item: item[0][1], reverse=True):
            if len(paths) < 2:
                continue
            files_payload = []
            for p in sorted(paths):
                stat = p.stat()
                files_payload.append(
                    {
                        "path": str(p),
                        "size": stat.st_size,
                        "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )
            groups.append({"hash": file_hash, "size": size, "files": files_payload})

        return ToolResult(
            success=True,
            output={
                "root": str(root_path),
                "scanned_files": len(files),
                "duplicate_groups": len(groups),
                "groups": groups,
            },
        )
    except PermissionError as exc:
        return ToolResult.error_result(str(exc))
    except Exception as exc:
        return ToolResult.from_exception(exc, context="find_duplicates failed", logger=logger)
