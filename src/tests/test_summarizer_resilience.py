from agentforge.summarizer import Summarizer


def test_graceful_summarize_falls_back_when_llm_summary_raises():
    summarizer = Summarizer(max_tokens=128)
    messages = []
    for idx in range(12):
        role = "user" if idx % 2 == 0 else "assistant"
        messages.append({"role": role, "content": f"{role}-{idx} " + ("x" * 120)})

    def _boom(_: str) -> str:
        raise RuntimeError("llm unavailable")

    summary, remaining = summarizer.graceful_summarize(
        messages=messages,
        existing_summary="baseline",
        llm_fn=_boom,
    )

    assert "baseline" in summary
    assert "[Compressed" in summary
    assert 8 <= len(remaining) <= 12


def test_emergency_compress_keeps_broader_tail_and_summary_hint():
    summarizer = Summarizer(max_tokens=128)
    messages = []
    for idx in range(14):
        role = "user" if idx % 2 == 0 else "assistant"
        messages.append({"role": role, "content": f"{role}-{idx} " + ("y" * 80)})

    compacted, meta = summarizer.emergency_compress(messages, existing_summary="baseline summary")

    assert meta["dropped_count"] > 0
    assert meta["kept_count"] >= 6
    assert compacted[0]["role"] == "system"
    assert "emergency compaction" in compacted[0]["content"].lower()
    assert len(compacted) >= 7
