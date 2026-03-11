import argparse

from agentforge.cli import build_inference_config
from agentforge.llm_inference import InferenceConfig


def test_cli_uses_inference_defaults_when_flags_not_provided():
    args = argparse.Namespace(
        ctx_size=None,
        gpu_layers=None,
        threads=None,
        temp=None,
        top_p=None,
        top_k=None,
        repeat_penalty=None,
        seed=None,
        reasoning_effort="",
        max_tokens=None,
        port=None,
        host="",
        boot_timeout=None,
        health_timeout=None,
        request_timeout=None,
        shutdown_timeout=None,
        compat_retry_limit=None,
        max_requests_per_minute=None,
        model_id="",
    )
    cfg = build_inference_config(args)
    defaults = InferenceConfig()
    assert cfg.n_ctx == defaults.n_ctx
    assert cfg.temperature == defaults.temperature
    assert cfg.top_p == defaults.top_p
    assert cfg.top_k == defaults.top_k
    assert cfg.repeat_penalty == defaults.repeat_penalty
    assert cfg.seed == defaults.seed
    assert cfg.reasoning_effort == defaults.reasoning_effort
    assert cfg.max_tokens == defaults.max_tokens
    assert cfg.port == defaults.port
    assert cfg.boot_timeout_s == defaults.boot_timeout_s
    assert cfg.health_timeout_s == defaults.health_timeout_s
    assert cfg.request_timeout_s == defaults.request_timeout_s
    assert cfg.shutdown_timeout_s == defaults.shutdown_timeout_s
    assert cfg.compat_retry_limit == defaults.compat_retry_limit
    assert cfg.max_requests_per_minute == defaults.max_requests_per_minute
    assert cfg.model_id == defaults.model_id


def test_cli_overrides_inference_defaults_when_flags_are_set():
    args = argparse.Namespace(
        ctx_size=16384,
        gpu_layers=-1,
        threads=4,
        temp=0.2,
        top_p=0.85,
        top_k=20,
        repeat_penalty=1.05,
        seed=123,
        reasoning_effort="medium",
        max_tokens=9000,
        port=9001,
        host="0.0.0.0",
        boot_timeout=150,
        health_timeout=4,
        request_timeout=450,
        shutdown_timeout=9,
        compat_retry_limit=11,
        max_requests_per_minute=25,
        model_id="qwen-test",
    )
    cfg = build_inference_config(args)
    assert cfg.n_ctx == 16384
    assert cfg.n_gpu_layers == -1
    assert cfg.n_threads == 4
    assert cfg.temperature == 0.2
    assert cfg.top_p == 0.85
    assert cfg.top_k == 20
    assert cfg.repeat_penalty == 1.05
    assert cfg.seed == 123
    assert cfg.reasoning_effort == "medium"
    assert cfg.max_tokens == 9000
    assert cfg.port == 9001
    assert cfg.host == "0.0.0.0"
    assert cfg.boot_timeout_s == 150
    assert cfg.health_timeout_s == 4
    assert cfg.request_timeout_s == 450
    assert cfg.shutdown_timeout_s == 9
    assert cfg.compat_retry_limit == 11
    assert cfg.max_requests_per_minute == 25
    assert cfg.model_id == "qwen-test"


def test_cli_normalizes_extra_high_reasoning_effort():
    args = argparse.Namespace(
        ctx_size=None,
        gpu_layers=None,
        threads=None,
        temp=None,
        top_p=None,
        top_k=None,
        repeat_penalty=None,
        seed=None,
        reasoning_effort="extra high",
        max_tokens=None,
        port=None,
        host="",
        boot_timeout=None,
        health_timeout=None,
        request_timeout=None,
        shutdown_timeout=None,
        compat_retry_limit=None,
        max_requests_per_minute=None,
        model_id="",
    )
    cfg = build_inference_config(args)
    assert cfg.reasoning_effort == "extra_high"
