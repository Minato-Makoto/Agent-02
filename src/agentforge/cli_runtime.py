from __future__ import annotations

import atexit
import logging
import os
import signal
import sys
from typing import Any, Callable, Dict, Optional

from .agent_core import Agent, AgentConfig, StreamCallbacks
from .cli_args import (
    build_inference_config,
    find_workspace,
    get_arg,
    is_openai_api_base_url,
    load_env_file,
)
from .context import ContextBuilder
from .llm_inference import InferenceConfig, LLMInference
from .session import SessionManager
from .skills import SkillLoader
from .summarizer import Summarizer
from .tools import ToolRegistry

logger = logging.getLogger(__name__)


def _require_positive_int_arg(args: Any, name: str) -> int:
    value = get_arg(args, name, None)
    if value is None:
        raise ValueError(f"Missing required argument --{name.replace('_', '-')}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid --{name.replace('_', '-')}: must be integer") from exc
    if parsed <= 0:
        raise ValueError(f"Invalid --{name.replace('_', '-')}: must be > 0")
    return parsed


def _require_positive_float_arg(args: Any, name: str) -> float:
    value = get_arg(args, name, None)
    if value is None:
        raise ValueError(f"Missing required argument --{name.replace('_', '-')}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid --{name.replace('_', '-')}: must be number") from exc
    if parsed <= 0:
        raise ValueError(f"Invalid --{name.replace('_', '-')}: must be > 0")
    return parsed


def _create_or_load_session(session_mgr: SessionManager, requested_id: str, ui: Any):
    if requested_id:
        session = session_mgr.load_session(requested_id)
        if session:
            return session
        ui.status(f"Session '{requested_id}' not found, creating new session.")
    return session_mgr.new_session()


def _connect_backend(llm: LLMInference, args: Any, config: InferenceConfig, ui: Any) -> bool:
    provider = str(get_arg(args, "provider", "local"))
    model = str(get_arg(args, "model", "") or "")
    server_exe = str(get_arg(args, "server_exe", "") or "")
    base_url = str(get_arg(args, "base_url", "") or "")
    api_key_env = str(get_arg(args, "api_key_env", "OPENAI_API_KEY") or "OPENAI_API_KEY")

    if provider == "local":
        if not model:
            ui.error("Missing model path for local mode.")
            return False
        if not server_exe:
            ui.error("Missing --server-exe for local mode.")
            return False

        ui.status(f"Loading model: {os.path.basename(model)}")
        ui.status(f"Server: {server_exe} ({config.host}:{config.port})")
        ui.status(
            "Reasoning effort: "
            f"{config.reasoning_effort or '(none)'} "
            "(levels: low|medium|high|extra_high; always sent to model endpoint)."
        )
        if not llm.load_model(model, config, server_exe=server_exe):
            ui.error("Failed to load model.")
            return False
        return True

    if not base_url:
        ui.error("Missing --base-url for openai_compatible mode.")
        return False

    api_key = os.environ.get(api_key_env, "")
    if is_openai_api_base_url(base_url) and not api_key:
        ui.error(f"Missing API key: set environment variable {api_key_env} for OpenAI endpoint.")
        return False

    ui.status(f"Provider: {provider}")
    ui.status(f"Base URL: {base_url}")
    ui.status(f"Model ID: {config.model_id}")
    ui.status(
        "Reasoning effort: "
        f"{config.reasoning_effort or '(none)'} "
        "(levels: low|medium|high|extra_high; always sent to model endpoint)."
    )
    ui.status(
        "Reasoning stream length is backend/model behavior; effort level is only a request hint."
    )
    ui.status(
        "Transport: Chat Completions-compatible endpoint "
        "(Responses API is recommended for new OpenAI-native projects)."
    )
    if not llm.connect_remote(
        base_url=base_url,
        model_id=config.model_id,
        api_key=api_key,
        config=config,
    ):
        ui.error("Failed to connect remote endpoint.")
        return False
    return True


def _build_callbacks(ui: Any) -> tuple[StreamCallbacks, Dict[str, bool]]:
    stream_state: Dict[str, bool] = {"token_emitted": False}

    def on_token(token: str) -> None:
        stream_state["token_emitted"] = True
        ui.stream_token(token)

    def on_thinking_start() -> None:
        # Track token streaming per model iteration (agent may iterate multiple times per turn).
        stream_state["token_emitted"] = False
        ui.thinking_start()

    def on_stream_end() -> None:
        # Do not close blindly: non-stream final text is rendered by _render_agent_result().
        if stream_state.get("token_emitted", False):
            ui.stream_end()

    def on_skill_activated(name: str) -> None:
        ui.status(f"Skill activated: {name}")

    def on_tool_call_start(name: str, _index: int) -> None:
        # Keep lifecycle parity with preview flow where tool call rendering
        # begins after the model stream settles.
        ui.stream_end()
        ui.tool_call_stream_start(name)

    def on_tool_call_delta(_index: int, token: str) -> None:
        ui.tool_call_stream_token(token)

    def on_tool_call_end(_index: int) -> None:
        ui.tool_call_stream_end()

    callbacks = StreamCallbacks(
        on_token=on_token,
        on_reasoning=ui.stream_reasoning,
        on_tool_call=ui.show_tool_call,
        on_tool_call_start=on_tool_call_start,
        on_tool_call_delta=on_tool_call_delta,
        on_tool_call_end=on_tool_call_end,
        on_tool_result=ui.show_tool_result,
        on_stream_start=ui.stream_start,
        on_stream_end=on_stream_end,
        on_thinking_start=on_thinking_start,
        on_thinking_end=ui.thinking_stop,
        on_skill_activated=on_skill_activated,
        on_status=ui.status,
    )
    return callbacks, stream_state


def _handle_command(
    cmd: str,
    *,
    agent: Agent,
    ui: Any,
    skill_loader: SkillLoader,
    session_mgr: SessionManager,
) -> Optional[bool]:
    if cmd in {"exit", "quit"}:
        return False

    if cmd == "reset":
        agent.reset()
        ui.status("Conversation reset.")
        return True

    if cmd == "clear":
        os.system("cls" if sys.platform == "win32" else "clear")
        return True

    if cmd == "skills":
        ui.status(skill_loader.build_status_panel())
        return True

    if cmd == "session":
        active_id = session_mgr.session.id if session_mgr.session else "(none)"
        ui.status(f"Session: {active_id}")
        ui.status(f"Messages: {session_mgr.get_message_count()}")
        return True

    return None


def _render_agent_result(ui: Any, result: str, stream_state: Dict[str, bool]) -> None:
    if result.startswith("[LLM Error:"):
        ui.error(result[1:-1])
        return
    if result.startswith("[Agent stopped:") or result.startswith("[Agent reached"):
        ui.status(result)
        return
    if result and not stream_state.get("token_emitted", False) and not result.startswith("["):
        ui.stream_start()
        ui.stream_token(result)
        ui.stream_end()
        return
    if not stream_state.get("token_emitted", False):
        ui.stream_end()


def _cleanup_runtime_resources() -> None:
    """
    Best-effort shutdown of long-lived tool subprocesses.

    Prevents Playwright Node driver EPIPE errors on process exit by explicitly
    stopping the browser/session bridge before Python tears down stdio.
    """
    try:
        from builtin_tools.browser_tools import BrowserManager

        BrowserManager.close()
    except Exception:
        logger.debug("Browser cleanup failed (best-effort).", exc_info=True)

    try:
        from builtin_tools.photoshop_tools import PhotoshopClient

        PhotoshopClient.disconnect()
    except Exception:
        logger.debug("Photoshop cleanup failed (best-effort).", exc_info=True)


def _install_shutdown_signal_handlers(handler: Callable[[int, Any], None]) -> Dict[Any, Any]:
    """Install best-effort signal handlers for graceful shutdown."""
    installed: Dict[Any, Any] = {}
    for name in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            installed[sig] = signal.getsignal(sig)
            signal.signal(sig, handler)
        except (ValueError, OSError, RuntimeError):
            logger.debug("Could not install signal handler for %s", name, exc_info=True)
    return installed


def _restore_shutdown_signal_handlers(installed: Dict[Any, Any]) -> None:
    """Restore previous signal handlers."""
    for sig, previous in installed.items():
        try:
            signal.signal(sig, previous)
        except (ValueError, OSError, RuntimeError):
            logger.debug("Could not restore signal handler for %s", sig, exc_info=True)


def run_interactive(
    args: Any,
    *,
    ui_factory: Callable[..., Any],
    llm_factory: Callable[[], LLMInference],
) -> int:
    """Run interactive chat session with skill system."""
    ui = ui_factory(verbose=bool(get_arg(args, "verbose", False)))

    env_file = str(get_arg(args, "env_file", "") or "").strip()
    if env_file:
        env_file_abs = os.path.abspath(env_file)
        if not os.path.isfile(env_file_abs):
            ui.error(f"Env file not found: {env_file_abs}")
            return 1
        try:
            loaded = load_env_file(env_file_abs, override=False)
            ui.status(f"Loaded {len(loaded)} env vars from: {env_file_abs}")
        except (OSError, UnicodeDecodeError) as exc:
            ui.error(f"Failed to load env file: {exc}")
            return 1

    config = build_inference_config(args)

    workspace_dir = find_workspace(args)
    if not os.path.isdir(workspace_dir):
        ui.error(f"Workspace not found: {workspace_dir}")
        ui.status("Run setup to create workspace directory.")
        return 1
    os.environ["AGENTFORGE_WORKSPACE"] = workspace_dir

    session_mgr = SessionManager(os.path.join(workspace_dir, "sessions"))
    skill_loader = SkillLoader(workspace_dir)
    context_builder = ContextBuilder(workspace_dir)
    summarizer = Summarizer(max_tokens=config.n_ctx)
    tools = ToolRegistry()

    session_id = str(get_arg(args, "session", "") or "").strip()
    session = _create_or_load_session(session_mgr, session_id, ui)

    skills = skill_loader.discover()
    skill_count = len(skills)
    discovered_tool_count = sum(len(s.tools) for s in skills.values())

    llm = llm_factory()
    if not _connect_backend(llm, args, config, ui):
        return 1

    ui.status(f"Workspace: {workspace_dir}")
    ui.status(f"Skills discovered: {skill_count} ({discovered_tool_count} tools total)")

    try:
        max_iterations = _require_positive_int_arg(args, "max_iterations")
        max_repeats = _require_positive_int_arg(args, "max_repeats")
        agent_timeout = _require_positive_float_arg(args, "agent_timeout")
    except ValueError as exc:
        ui.error(str(exc))
        return 1

    agent = Agent(
        config=AgentConfig(
            max_iterations=max_iterations,
            max_repeats=max_repeats,
            timeout=agent_timeout,
            workspace_dir=workspace_dir,
            verbose=bool(get_arg(args, "verbose", False)),
        ),
        llm=llm,
        tools=tools,
        session_mgr=session_mgr,
        summarizer=summarizer,
        skill_loader=skill_loader,
        context_builder=context_builder,
    )

    provider = str(get_arg(args, "provider", "local"))

    shutdown_state = {"done": False}

    def _shutdown_runtime() -> None:
        if shutdown_state["done"]:
            return
        shutdown_state["done"] = True
        _cleanup_runtime_resources()
        llm.unload()

    def _handle_shutdown_signal(signum: int, _frame: Any) -> None:
        try:
            ui.status(f"Received signal {signum}. Shutting down...")
        except Exception:
            logger.debug("Signal status update failed.", exc_info=True)
        raise KeyboardInterrupt

    installed_signal_handlers = _install_shutdown_signal_handlers(_handle_shutdown_signal)
    atexit.register(_shutdown_runtime)

    try:
        tool_names = [tool.name for tool in tools.get_all()]
        ui.welcome(
            llm.model_desc,
            tool_names,
            session_id=session_mgr.session.id if session_mgr.session else session.id,
            skill_count=skill_count,
            total_tool_count=discovered_tool_count,
            workspace=workspace_dir,
            provider=provider,
        )

        while True:
            line = ui.get_input()
            if line is None:
                break
            if not line:
                continue

            cmd = line.strip().lower()
            command_result = _handle_command(
                cmd,
                agent=agent,
                ui=ui,
                skill_loader=skill_loader,
                session_mgr=session_mgr,
            )
            if command_result is False:
                break
            if command_result is True:
                continue

            before_session_id = session_mgr.session.id if session_mgr.session else ""
            callbacks, stream_state = _build_callbacks(ui)
            result = agent.run(line, callbacks=callbacks)
            after_session_id = session_mgr.session.id if session_mgr.session else ""
            if after_session_id and after_session_id != before_session_id:
                ui.status(
                    f"Session continued: {before_session_id or '(none)'} -> {after_session_id}"
                )
            _render_agent_result(ui, result, stream_state)
    finally:
        _restore_shutdown_signal_handlers(installed_signal_handlers)
        try:
            atexit.unregister(_shutdown_runtime)
        except Exception:
            logger.debug("Could not unregister shutdown hook.", exc_info=True)
        _shutdown_runtime()
        ui.goodbye()
    return 0
