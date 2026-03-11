from agentforge.llm_inference import InferenceConfig, LLMInference


def test_load_model_does_not_detach_child_process_from_console(monkeypatch):
    llm = LLMInference()
    captured_kwargs = {}

    class _FakeProc:
        stderr = None

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            del timeout
            return 0

        def kill(self):
            return None

    monkeypatch.setattr("agentforge.llm_inference.os.path.exists", lambda _path: True)
    monkeypatch.setattr(
        "agentforge.llm_inference.subprocess.Popen",
        lambda *args, **kwargs: captured_kwargs.update(kwargs) or _FakeProc(),
    )
    monkeypatch.setattr(LLMInference, "_wait_for_server", lambda self, timeout=120: True)

    ok = llm.load_model(
        model_path="D:/models/mock.gguf",
        config=InferenceConfig(),
        server_exe="D:/bin/llama-server.exe",
    )

    assert ok is True
    assert "creationflags" not in captured_kwargs
