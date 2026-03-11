import pytest

from agentforge.llm_inference import InferenceConfig, LLMInference


def test_llm_rate_limit_blocks_excess_requests():
    llm = LLMInference()
    llm._config = InferenceConfig(max_requests_per_minute=2)

    llm._consume_rate_limit_slot()
    llm._consume_rate_limit_slot()

    with pytest.raises(RuntimeError, match="Rate limit exceeded"):
        llm._consume_rate_limit_slot()


def test_llm_rate_limit_can_be_disabled():
    llm = LLMInference()
    llm._config = InferenceConfig(max_requests_per_minute=0)

    for _ in range(20):
        llm._consume_rate_limit_slot()
