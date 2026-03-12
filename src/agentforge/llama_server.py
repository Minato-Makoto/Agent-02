"""
Lightweight llama-server process management for Agent-02.

This module intentionally does not add any chat/session/model ownership on top of
llama-server. It only starts the process, probes /health, and exposes basic
diagnostics for launcher output.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import IO, Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

_HEALTH_POLL_INTERVAL = 2.0


@dataclass
class LlamaServerConfig:
    server_exe: str = ""
    models_dir: str = ""
    host: str = "127.0.0.1"
    port: int = 8080
    models_max: int = 1
    boot_timeout: int = 120
    shutdown_timeout: int = 5
    extra_flags: list[str] = field(default_factory=list)


class LlamaServerProcess:
    """Lifecycle manager for a local llama-server process."""

    def __init__(self, config: LlamaServerConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._base_url = f"http://{config.host}:{config.port}"
        self._command: list[str] = []
        self._last_error = ""
        self._last_error_category = ""
        self._last_exit_code: Optional[int] = None
        self._stdout_path = ""
        self._stderr_path = ""
        self._stdout_handle: Optional[IO[bytes]] = None
        self._stderr_handle: Optional[IO[bytes]] = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_running(self) -> bool:
        if self._process is None:
            return False
        status = self._process.poll()
        if status is None:
            return True
        self._last_exit_code = status
        return False

    @property
    def command(self) -> list[str]:
        return list(self._command)

    @property
    def command_line(self) -> str:
        return subprocess.list2cmdline(self._command) if self._command else ""

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def last_error_category(self) -> str:
        return self._last_error_category

    @property
    def last_exit_code(self) -> Optional[int]:
        return self._last_exit_code

    @property
    def last_stderr_tail(self) -> str:
        return self._read_output_tail(self._stderr_path)

    @property
    def last_stdout_tail(self) -> str:
        return self._read_output_tail(self._stdout_path)

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "command_line": self.command_line,
            "last_error": self.last_error,
            "last_error_category": self.last_error_category,
            "last_exit_code": self.last_exit_code,
            "last_stderr_tail": self.last_stderr_tail,
            "last_stdout_tail": self.last_stdout_tail,
        }

    def start(self) -> bool:
        if self.is_running:
            logger.info("llama-server already running (pid=%s).", self._process.pid)
            return True

        self._reset_diagnostics()
        exe = self.config.server_exe
        if not exe or not os.path.isfile(exe):
            self._record_failure("missing_executable", f"llama-server executable not found: {exe}")
            logger.error(self._last_error)
            return False

        models_dir = self.config.models_dir
        if not models_dir or not os.path.isdir(models_dir):
            self._record_failure("missing_models_dir", f"Models directory not found: {models_dir}")
            logger.error(self._last_error)
            return False

        cmd = [
            exe,
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
            "--models-dir",
            models_dir,
            "--models-max",
            str(self.config.models_max),
            "--models-autoload",
            *self.config.extra_flags,
        ]
        self._command = list(cmd)
        logger.info("Starting llama-server: %s", " ".join(cmd))

        try:
            self._open_output_logs()
            self._process = subprocess.Popen(
                cmd,
                stdout=self._stdout_handle,
                stderr=self._stderr_handle,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            self._record_failure("spawn_os_error", f"Failed to start llama-server: {exc}")
            logger.error(self._last_error)
            self._close_output_handles()
            return False

        if not self._wait_for_health():
            if self._last_error:
                logger.error(self._last_error)
            stderr_tail = self.last_stderr_tail
            if stderr_tail:
                logger.error("llama-server stderr tail:\n%s", stderr_tail)
            self.stop()
            return False

        logger.info("llama-server healthy (pid=%s).", self._process.pid)
        return True

    def wait(self) -> int:
        if self._process is None:
            return 0
        try:
            return self._process.wait()
        finally:
            self._last_exit_code = self._process.returncode

    def stop(self) -> None:
        if self._process is None:
            self._close_output_handles()
            return
        logger.info("Stopping llama-server (pid=%s)...", self._process.pid)
        try:
            self._process.terminate()
            self._process.wait(timeout=self.config.shutdown_timeout)
        except subprocess.TimeoutExpired:
            logger.warning("llama-server did not stop gracefully, killing.")
            self._process.kill()
            self._process.wait(timeout=5)
        except Exception:
            logger.exception("Error stopping llama-server.")
        finally:
            self._last_exit_code = self._process.returncode
            self._process = None
            self._close_output_handles()

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self._base_url}/health", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def _wait_for_health(self) -> bool:
        deadline = time.time() + self.config.boot_timeout
        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                self._last_exit_code = self._process.returncode
                self._classify_runtime_failure(
                    fallback_message=f"llama-server exited prematurely (code={self._process.returncode})."
                )
                return False
            if self.health_check():
                return True
            time.sleep(_HEALTH_POLL_INTERVAL)
        self._record_failure(
            "health_timeout",
            f"llama-server did not become healthy within {self.config.boot_timeout}s.",
        )
        return False

    def _reset_diagnostics(self) -> None:
        self._command = []
        self._last_error = ""
        self._last_error_category = ""
        self._last_exit_code = None
        self._stdout_path = ""
        self._stderr_path = ""
        self._close_output_handles()

    def _record_failure(self, category: str, message: str) -> None:
        self._last_error_category = category
        self._last_error = message

    def _open_output_logs(self) -> None:
        self._close_output_handles()
        stdout_fd, self._stdout_path = tempfile.mkstemp(prefix="agent02-llama-stdout-", suffix=".log")
        stderr_fd, self._stderr_path = tempfile.mkstemp(prefix="agent02-llama-stderr-", suffix=".log")
        self._stdout_handle = os.fdopen(stdout_fd, "wb", buffering=0)
        self._stderr_handle = os.fdopen(stderr_fd, "wb", buffering=0)

    def _close_output_handles(self) -> None:
        for handle_name in ("_stdout_handle", "_stderr_handle"):
            handle = getattr(self, handle_name)
            if handle is None:
                continue
            try:
                handle.flush()
            except Exception:
                pass
            try:
                handle.close()
            except Exception:
                pass
            setattr(self, handle_name, None)

    def _read_output_tail(self, path: str, *, max_lines: int = 40) -> str:
        if not path or not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
        except OSError:
            return ""
        return "\n".join(line.rstrip("\r\n") for line in lines[-max_lines:])

    def _classify_runtime_failure(self, *, fallback_message: str) -> None:
        stderr_tail = self.last_stderr_tail
        lowered = stderr_tail.lower()
        summary_line = ""
        for line in reversed(stderr_tail.splitlines()):
            rendered = line.strip()
            if rendered:
                summary_line = rendered
                break

        if "invalid argument" in lowered or "unknown option" in lowered or "unrecognized option" in lowered:
            detail = summary_line or "llama-server rejected a startup flag."
            self._record_failure("invalid_flag", f"llama-server rejected a startup flag: {detail}")
            return

        bind_markers = (
            "address already in use",
            "only one usage of each socket address",
            "failed to bind",
            "bind failed",
            "failed to listen",
        )
        if any(marker in lowered for marker in bind_markers):
            detail = summary_line or fallback_message
            self._record_failure("port_bind", f"llama-server could not bind the requested port: {detail}")
            return

        if summary_line:
            self._record_failure("runtime_error", summary_line)
            return

        self._record_failure("runtime_error", fallback_message)
