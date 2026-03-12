from agentforge.llama_server import LlamaServerConfig, LlamaServerProcess


class _HealthyProcess:
    pid = 4242
    returncode = None

    def poll(self):
        return None

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        del timeout
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = 1


class _ExitedProcess:
    pid = 4242
    returncode = 1

    def poll(self):
        return self.returncode

    def terminate(self):
        return None

    def wait(self, timeout=None):
        del timeout
        return self.returncode

    def kill(self):
        return None


def test_llama_server_process_starts_without_duplicate_webui_flags(monkeypatch, tmp_path):
    server_exe = tmp_path / "llama-server.exe"
    server_exe.write_text("binary", encoding="utf-8")
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["kwargs"] = kwargs
        return _HealthyProcess()

    monkeypatch.setattr("agentforge.llama_server.subprocess.Popen", fake_popen)
    monkeypatch.setattr("agentforge.llama_server.requests.get", lambda *args, **kwargs: type("Resp", (), {"status_code": 200})())

    host = LlamaServerProcess(
        LlamaServerConfig(
            server_exe=str(server_exe),
            models_dir=str(models_dir),
            host="127.0.0.1",
            port=8080,
        )
    )

    assert host.start() is True
    assert "--webui" not in captured["cmd"]
    host.stop()


def test_llama_server_process_surfaces_invalid_flag_stderr(monkeypatch, tmp_path):
    server_exe = tmp_path / "llama-server.exe"
    server_exe.write_text("binary", encoding="utf-8")
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    def fake_popen(cmd, **kwargs):
        stderr_handle = kwargs["stderr"]
        assert stderr_handle is not None
        stderr_handle.write(b"error: invalid argument: --badflag\n")
        return _ExitedProcess()

    monkeypatch.setattr("agentforge.llama_server.subprocess.Popen", fake_popen)

    host = LlamaServerProcess(
        LlamaServerConfig(
            server_exe=str(server_exe),
            models_dir=str(models_dir),
            host="127.0.0.1",
            port=8080,
            boot_timeout=1,
            extra_flags=["--badflag"],
        )
    )

    assert host.start() is False
    assert host.last_error_category == "invalid_flag"
    assert "--badflag" in host.command_line
    assert "invalid argument" in host.last_stderr_tail.lower()
    assert "rejected a startup flag" in host.last_error.lower()
