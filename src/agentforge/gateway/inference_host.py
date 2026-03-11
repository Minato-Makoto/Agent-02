"""
InferenceHost — manage the llama-server process in router mode.

Boots ``llama-server.exe`` with ``--models-dir`` pointing at the shared
``models/`` directory and exposes health-check / shutdown helpers.
The Gateway treats the llama-server ``/v1/models`` endpoint as the only
source of truth for available models.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_HEALTH_POLL_INTERVAL = 2.0


@dataclass
class InferenceHostConfig:
    """Configuration for the local llama-server process."""

    server_exe: str = ""
    models_dir: str = ""
    host: str = "127.0.0.1"
    port: int = 8080
    models_max: int = 1
    boot_timeout: int = 120
    shutdown_timeout: int = 5
    extra_flags: list = field(default_factory=list)


class InferenceHost:
    """Lifecycle manager for a local llama-server process in router mode."""

    def __init__(self, config: InferenceHostConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._base_url = f"http://{config.host}:{config.port}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> bool:
        """Boot llama-server in router mode and wait for health."""
        if self.is_running:
            logger.info("InferenceHost already running (pid=%s).", self._process.pid)
            return True

        exe = self.config.server_exe
        if not exe or not os.path.isfile(exe):
            logger.error("llama-server executable not found: %s", exe)
            return False

        models_dir = self.config.models_dir
        if not models_dir or not os.path.isdir(models_dir):
            logger.error("Models directory not found: %s", models_dir)
            return False

        cmd = [
            exe,
            "--host", self.config.host,
            "--port", str(self.config.port),
            "--models-dir", models_dir,
            "--models-max", str(self.config.models_max),
            "--models-autoload",
            "--webui",
            *self.config.extra_flags,
        ]
        logger.info("Starting llama-server: %s", " ".join(cmd))

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            logger.error("Failed to start llama-server: %s", exc)
            return False

        if not self._wait_for_health():
            logger.error("llama-server did not become healthy within %ss.", self.config.boot_timeout)
            self.stop()
            return False

        logger.info("llama-server healthy (pid=%s).", self._process.pid)
        return True

    def stop(self) -> None:
        """Gracefully terminate the llama-server process."""
        if self._process is None:
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
            self._process = None

    def health_check(self) -> bool:
        """Return True if llama-server responds to /health."""
        try:
            resp = requests.get(f"{self._base_url}/health", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _wait_for_health(self) -> bool:
        deadline = time.time() + self.config.boot_timeout
        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                logger.error("llama-server exited prematurely (code=%s).", self._process.returncode)
                return False
            if self.health_check():
                return True
            time.sleep(_HEALTH_POLL_INTERVAL)
        return False
