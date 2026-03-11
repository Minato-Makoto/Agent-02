"""
AgentForge — LLM inference transport.

Supports:
- Local llama-server process mode
- Remote OpenAI-compatible endpoint mode
- Structured tool-calling with runtime capability fallback
"""

import os
import sys
import json
import time
import re
import logging
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .contracts import ChatCompletionResult, ProviderCapabilities, ToolCall
from .schema_normalizer import normalize_openai_tools_for_provider
from .transcript_policy import (
    apply_transcript_policy,
    detect_provider_kind,
    resolve_transcript_policy,
)
from .tool_id import sanitize_tool_call_id

logger = logging.getLogger(__name__)


@dataclass
class InferenceConfig:
    """Configuration for LLM inference."""

    n_ctx: int = 8192
    n_gpu_layers: int = -1
    n_threads: int = 0
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 4096
    seed: int = -1
    repeat_penalty: float = 1.1
    host: str = "127.0.0.1"
    port: int = 8080
    model_id: str = "local"
    boot_timeout_s: int = 120
    health_timeout_s: int = 2
    request_timeout_s: int = 300
    shutdown_timeout_s: int = 5
    health_path: str = "/health"
    local_chat_endpoint: str = "/v1/chat/completions"
    local_completion_endpoint: str = "/completion"
    remote_chat_endpoint: str = "/v1/chat/completions"
    remote_completion_endpoint: str = "/v1/completions"
    # Unified reasoning level sent as-is (normalized).
    # Supported levels: low, medium, high, extra_high.
    reasoning_effort: str = ""
    tools_probe_user_prompt: str = "ping"
    tools_probe_tool_name: str = "probe_noop"
    tools_probe_description: str = "probe"
    tools_probe_max_tokens: int = 1
    health_poll_interval_s: float = 1.0
    compat_retry_limit: int = 8
    max_requests_per_minute: int = 0
    http_error_body_chars: int = 1200
    sse_data_prefix: str = "data: "
    sse_done_marker: str = "[DONE]"
    unsupported_error_keywords: Tuple[str, ...] = (
        "unsupported",
        "not supported",
        "not compatible",
        "unknown field",
        "unknown parameter",
        "invalid param",
        "unrecognized",
        "extra inputs are not permitted",
        "not allowed",
        "unexpected keyword",
    )


class LLMInference:
    """Manages LLM endpoint and chat-completion requests."""

    def __init__(self):
        self._config = InferenceConfig()
        self._loaded = False
        self._mode = "local"  # local | remote
        self._model_path = ""
        self._server_process: Optional[subprocess.Popen] = None
        self._server_exe = ""
        self._base_url = ""
        self._chat_endpoint = self._config.local_chat_endpoint
        self._completion_endpoint = self._config.local_completion_endpoint
        self._api_key = ""
        self._capabilities = ProviderCapabilities()
        self._provider_kind = "llama_cpp"
        self._request_timestamps: List[float] = []

    def load_model(
        self, model_path: str, config: Optional[InferenceConfig] = None, server_exe: str = ""
    ) -> bool:
        """Start local llama-server with the given model."""
        if config:
            self._config = config

        self._mode = "local"
        self._model_path = model_path
        self._server_exe = server_exe
        self._base_url = f"http://{self._config.host}:{self._config.port}"
        self._chat_endpoint = self._config.local_chat_endpoint
        self._completion_endpoint = self._config.local_completion_endpoint
        self._api_key = ""
        self._capabilities = ProviderCapabilities()
        self._provider_kind = "llama_cpp"

        if not server_exe or not os.path.exists(server_exe):
            logger.error("[LLM] llama-server.exe not found: %s", server_exe)
            return False

        if not os.path.exists(model_path):
            logger.error("[LLM] Model file not found: %s", model_path)
            return False

        cmd = [
            server_exe,
            "-m",
            model_path,
            "-c",
            str(self._config.n_ctx),
            "-ngl",
            str(self._config.n_gpu_layers),
            "--host",
            self._config.host,
            "--port",
            str(self._config.port),
        ]
        if self._config.n_threads > 0:
            cmd.extend(["-t", str(self._config.n_threads)])

        logger.info("[LLM] Starting llama-server...")
        logger.info("[LLM] Model: %s", os.path.basename(model_path))

        try:
            self._server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            logger.exception("[LLM] Failed to start server")
            return False

        if not self._wait_for_server(timeout=self._config.boot_timeout_s):
            logger.error("[LLM] Server failed to start within timeout.")
            self.unload()
            return False

        self._loaded = True
        logger.info("[LLM] Server ready at %s", self._base_url)
        return True

    def connect_remote(
        self, base_url: str, model_id: str, api_key: str = "", config: Optional[InferenceConfig] = None
    ) -> bool:
        """Attach to a remote OpenAI-compatible endpoint (no local process)."""
        if config:
            self._config = config
        if not base_url:
            logger.error("[LLM] base_url is required for remote mode.")
            return False

        self._mode = "remote"
        self._model_path = ""
        self._server_exe = ""
        self._server_process = None
        self._api_key = api_key or ""
        self._config.model_id = model_id or "local"
        self._base_url = base_url.rstrip("/")
        self._capabilities = ProviderCapabilities()
        self._provider_kind = detect_provider_kind(
            mode="remote", base_url=self._base_url, model_id=self._config.model_id
        )

        if self._base_url.endswith("/v1"):
            self._chat_endpoint = "/chat/completions"
            self._completion_endpoint = "/completions"
        else:
            self._chat_endpoint = self._config.remote_chat_endpoint
            self._completion_endpoint = self._config.remote_completion_endpoint

        self._loaded = True
        logger.info("[LLM] Remote endpoint ready: %s", self._base_url)
        return True

    def _wait_for_server(self, timeout: int = 120) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self._server_process and self._server_process.poll() is not None:
                stderr = ""
                if self._server_process.stderr is not None:
                    stderr = self._server_process.stderr.read().decode("utf-8", errors="replace")
                logger.error("[LLM] Server crashed: %s", stderr[:500])
                return False

            try:
                req = urllib.request.Request(f"{self._base_url}{self._config.health_path}")
                resp = urllib.request.urlopen(req, timeout=self._config.health_timeout_s)
                data = json.loads(resp.read())
                status = data.get("status", "")
                if status == "ok":
                    return True
            except (urllib.error.URLError, ConnectionError, OSError, json.JSONDecodeError):
                logger.debug("[LLM] Health probe not ready yet.", exc_info=True)
            time.sleep(self._config.health_poll_interval_s)
        return False

    def unload(self):
        """Stop local server process (if any)."""
        if self._server_process:
            try:
                self._server_process.terminate()
                try:
                    self._server_process.wait(timeout=self._config.shutdown_timeout_s)
                except subprocess.TimeoutExpired:
                    self._server_process.kill()
            except (OSError, ValueError):
                logger.debug("[LLM] Failed to terminate server process cleanly.", exc_info=True)
            self._server_process = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def model_desc(self) -> str:
        if self._mode == "remote":
            return self._config.model_id
        if not self._model_path:
            return ""
        return os.path.basename(self._model_path)

    @property
    def is_connected(self) -> bool:
        """Return True if the transport is ready (loaded or connected)."""
        return self._loaded

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def set_model_id(self, model_id: str) -> None:
        """Update the model ID for future requests (gateway model switching)."""
        self._config.model_id = model_id or self._config.model_id

    def generate(
        self,
        prompt: str,
        grammar: str = "",
        stop: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text using completion endpoint (mainly local compatibility)."""
        if not self._loaded:
            return "[Error: Server not running]"

        payload: Dict[str, Any] = {
            "prompt": prompt,
            "max_tokens": max_tokens or self._config.max_tokens,
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
        }
        if stop:
            payload["stop"] = stop
        if grammar:
            payload["grammar"] = grammar
        if self._config.seed >= 0:
            payload["seed"] = self._config.seed

        try:
            resp = self._post(self._completion_endpoint, payload)
            if "content" in resp:
                return str(resp["content"])
            choices = resp.get("choices", [])
            if choices:
                return str(choices[0].get("text", ""))
            return ""
        except Exception as e:
            return f"[Error: {e}]"

    def _is_unsupported_param_error(self, error_text: str, *params: str) -> bool:
        msg = (error_text or "").lower()
        if not msg:
            return False
        if not any((p or "").lower() in msg for p in params):
            return False
        keywords = self._config.unsupported_error_keywords
        return any(k in msg for k in keywords)

    def _is_tools_unsupported_error(self, error_text: str) -> bool:
        return self._is_unsupported_param_error(
            error_text,
            "tools",
            "tool_choice",
        )

    def _normalized_reasoning_effort(self) -> str:
        raw = str(self._config.reasoning_effort or "").strip().lower()
        if not raw:
            return ""
        normalized = raw.replace("-", "_").replace(" ", "_")
        if normalized == "extrahigh":
            normalized = "extra_high"
        if normalized in {"low", "medium", "high", "extra_high"}:
            return normalized
        logger.warning("Ignoring unsupported reasoning_effort value: %s", self._config.reasoning_effort)
        return ""

    def _should_send_reasoning_effort(self) -> bool:
        if self._capabilities.supports_reasoning_effort is False:
            return False
        if not self._normalized_reasoning_effort():
            return False
        return True

    def _resolved_model_id(self) -> str:
        model = (self._config.model_id or "").strip().lower()
        if "/" in model:
            model = model.rsplit("/", 1)[-1]
        return model

    def _should_prefer_max_completion_tokens(self) -> bool:
        # OpenAI Chat Completions marks `max_tokens` incompatible with o-series models.
        if self._provider_kind not in {"openai", "openrouter", "openai_compatible"}:
            return False
        model = self._resolved_model_id()
        return bool(re.match(r"^o\d", model))

    def _apply_chat_token_limit(self, payload: Dict[str, Any], max_tokens: Optional[int]) -> None:
        limit = max_tokens if max_tokens is not None else self._config.max_tokens
        if self._should_prefer_max_completion_tokens():
            payload["max_completion_tokens"] = limit
            payload.pop("max_tokens", None)
            return
        payload["max_tokens"] = limit
        payload.pop("max_completion_tokens", None)

    def _apply_compat_payload_fallback(
        self, payload: Dict[str, Any], error_text: str
    ) -> Tuple[bool, bool]:
        """
        Try to remove unsupported optional params and retry.

        Returns:
            (changed_payload, used_tools_fallback)
        """
        used_tools_fallback = False

        if ("tools" in payload or "tool_choice" in payload) and self._is_tools_unsupported_error(
            error_text
        ):
            self._capabilities.supports_tools = False
            self._capabilities.supports_parallel_tool_calls = False
            payload.pop("tools", None)
            payload.pop("tool_choice", None)
            payload.pop("parallel_tool_calls", None)
            return True, True

        if ("parallel_tool_calls" in payload) and self._is_unsupported_param_error(
            error_text, "parallel_tool_calls"
        ):
            self._capabilities.supports_parallel_tool_calls = False
            payload.pop("parallel_tool_calls", None)
            return True, used_tools_fallback

        if ("response_format" in payload) and self._is_unsupported_param_error(
            error_text, "response_format"
        ):
            self._capabilities.supports_response_format = False
            payload.pop("response_format", None)
            return True, used_tools_fallback

        if ("max_completion_tokens" in payload) and self._is_unsupported_param_error(
            error_text, "max_completion_tokens"
        ):
            payload["max_tokens"] = payload.pop("max_completion_tokens")
            return True, used_tools_fallback

        if ("max_tokens" in payload) and self._is_unsupported_param_error(
            error_text, "max_tokens"
        ):
            payload["max_completion_tokens"] = payload.pop("max_tokens")
            return True, used_tools_fallback

        if ("reasoning_effort" in payload) and self._is_unsupported_param_error(
            error_text, "reasoning_effort"
        ):
            self._capabilities.supports_reasoning_effort = False
            payload.pop("reasoning_effort", None)
            return True, used_tools_fallback

        if ("stream" in payload) and self._is_unsupported_param_error(error_text, "stream"):
            self._capabilities.supports_stream = False
            payload.pop("stream", None)
            return True, used_tools_fallback

        if ("grammar" in payload) and self._is_unsupported_param_error(error_text, "grammar"):
            payload.pop("grammar", None)
            return True, used_tools_fallback

        if ("stop" in payload) and self._is_unsupported_param_error(error_text, "stop"):
            payload.pop("stop", None)
            return True, used_tools_fallback

        return False, used_tools_fallback

    def _post_with_compat_fallback(
        self, endpoint: str, payload: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], bool]:
        used_tools_fallback = False
        for _ in range(max(1, self._config.compat_retry_limit)):
            try:
                return self._post(endpoint, payload), used_tools_fallback
            except Exception as e:
                changed, used_tools = self._apply_compat_payload_fallback(payload, str(e))
                used_tools_fallback = used_tools_fallback or used_tools
                if changed:
                    continue
                raise
        raise RuntimeError("Provider compatibility retry limit reached.")

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        parallel_tool_calls: bool = False,
        response_format: Optional[Dict[str, Any]] = None,
        grammar: str = "",
        stop: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        on_token=None,
        on_reasoning=None,
        on_tool_call_start=None,
        on_tool_call_delta=None,
        on_tool_call_end=None,
    ) -> ChatCompletionResult:
        """
        Generate from chat-completions endpoint.

        Returns structured `ChatCompletionResult`.
        """
        if not self._loaded:
            return ChatCompletionResult(error="Server not running")

        transcript_policy = resolve_transcript_policy(
            provider=self._provider_kind, model_id=self._config.model_id
        )
        policy_messages, _ = apply_transcript_policy(messages, transcript_policy)
        effective_messages = policy_messages or messages
        can_use_tools = bool(tools) and self._capabilities.supports_tools is not False
        provider_tools = normalize_openai_tools_for_provider(
            tools or [], self._provider_kind
        ) if tools else []

        payload: Dict[str, Any] = {
            "model": self._config.model_id,
            "messages": effective_messages,
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
        }
        self._apply_chat_token_limit(payload, max_tokens)
        if self._should_send_reasoning_effort():
            payload["reasoning_effort"] = self._normalized_reasoning_effort()
        if can_use_tools and provider_tools:
            payload["tools"] = provider_tools
            payload["tool_choice"] = tool_choice
            if parallel_tool_calls and self._capabilities.supports_parallel_tool_calls is not False:
                payload["parallel_tool_calls"] = True

        if response_format and self._capabilities.supports_response_format is not False:
            payload["response_format"] = response_format
        if stop:
            payload["stop"] = stop
        if grammar:
            payload["grammar"] = grammar

        if stream or on_token is not None:
            if self._capabilities.supports_stream is not False:
                payload["stream"] = True
            return self._stream_chat_completion(
                payload=payload,
                on_token=on_token,
                on_reasoning=on_reasoning,
                on_tool_call_start=on_tool_call_start,
                on_tool_call_delta=on_tool_call_delta,
                on_tool_call_end=on_tool_call_end,
            )

        try:
            resp, used_fallback = self._post_with_compat_fallback(self._chat_endpoint, payload)
        except Exception as e:
            return ChatCompletionResult(error=str(e))

        if "parallel_tool_calls" in payload:
            self._capabilities.supports_parallel_tool_calls = True
        if "response_format" in payload:
            self._capabilities.supports_response_format = True
        if "reasoning_effort" in payload:
            self._capabilities.supports_reasoning_effort = True

        result = self._parse_chat_completion_response(resp)
        result.used_tools_fallback = used_fallback
        return result

    def _parse_tool_calls(self, message: Dict[str, Any]) -> List[ToolCall]:
        raw_tool_calls = message.get("tool_calls", [])
        if not isinstance(raw_tool_calls, list):
            return []

        parsed: List[ToolCall] = []
        for i, tc in enumerate(raw_tool_calls):
            if not isinstance(tc, dict):
                continue
            raw_id = str(tc.get("id") or f"call_{i+1}")
            tc_id = sanitize_tool_call_id(raw_id, mode="strict")
            fn = tc.get("function", {})
            if not isinstance(fn, dict):
                fn = {}
            name = str(fn.get("name", "")).strip()
            if not name:
                continue
            raw_args = fn.get("arguments", "{}")
            args: Dict[str, Any]
            if isinstance(raw_args, dict):
                args = raw_args
            elif isinstance(raw_args, str):
                try:
                    parsed_args = json.loads(raw_args)
                    args = parsed_args if isinstance(parsed_args, dict) else {"raw": raw_args}
                except json.JSONDecodeError:
                    args = {"raw": raw_args}
            else:
                args = {}
            parsed.append(ToolCall(id=tc_id, name=name, arguments=args))
        return parsed

    def _extract_content(self, message: Dict[str, Any]) -> str:
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            return "".join(text_parts)
        return str(content) if content is not None else ""

    def _parse_chat_completion_response(self, resp: Dict[str, Any]) -> ChatCompletionResult:
        choices = resp.get("choices", [])
        if not choices:
            return ChatCompletionResult(raw_response=resp)

        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message", {})
        if not isinstance(message, dict):
            message = {}
        content = self._extract_content(message)
        tool_calls = self._parse_tool_calls(message)
        finish_reason = str(choice.get("finish_reason", "stop"))
        return ChatCompletionResult(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw_response=resp,
        )

    def _stream_chat_completion(
        self,
        payload: Dict[str, Any],
        on_token=None,
        on_reasoning=None,
        on_tool_call_start=None,
        on_tool_call_delta=None,
        on_tool_call_end=None,
    ) -> ChatCompletionResult:
        used_fallback = False
        for _ in range(max(1, self._config.compat_retry_limit)):
            try:
                if "stream" not in payload:
                    resp, retry_used_fallback = self._post_with_compat_fallback(
                        self._chat_endpoint, payload
                    )
                    used_fallback = used_fallback or retry_used_fallback
                    result = self._parse_chat_completion_response(resp)
                    if result.content and on_token:
                        on_token(result.content)
                    result.used_tools_fallback = used_fallback
                    return result

                result = self._stream_post(
                    endpoint=self._chat_endpoint,
                    payload=payload,
                    on_token=on_token,
                    on_reasoning=on_reasoning,
                    on_tool_call_start=on_tool_call_start,
                    on_tool_call_delta=on_tool_call_delta,
                    on_tool_call_end=on_tool_call_end,
                )
                self._capabilities.supports_stream = True
                if "parallel_tool_calls" in payload:
                    self._capabilities.supports_parallel_tool_calls = True
                if "response_format" in payload:
                    self._capabilities.supports_response_format = True
                if "reasoning_effort" in payload:
                    self._capabilities.supports_reasoning_effort = True
                result.used_tools_fallback = used_fallback
                return result
            except Exception as e:
                changed, used_tools = self._apply_compat_payload_fallback(payload, str(e))
                used_fallback = used_fallback or used_tools
                if changed:
                    continue
                return ChatCompletionResult(error=str(e))
        return ChatCompletionResult(error="Provider compatibility retry limit reached.")

    def _build_json_post_request(self, endpoint: str, payload: Dict[str, Any]) -> urllib.request.Request:
        url = f"{self._base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return urllib.request.Request(url, data=data, headers=headers, method="POST")

    def _raise_http_error(self, err: urllib.error.HTTPError) -> None:
        body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {err.code}: {body[:self._config.http_error_body_chars]}")

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._consume_rate_limit_slot()
        req = self._build_json_post_request(endpoint, payload)
        try:
            with urllib.request.urlopen(req, timeout=self._config.request_timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(body)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Invalid JSON response: {body[:300]}") from exc
        except urllib.error.HTTPError as err:
            self._raise_http_error(err)
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e}")

    def _stream_post(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        on_token=None,
        on_reasoning=None,
        on_tool_call_start=None,
        on_tool_call_delta=None,
        on_tool_call_end=None,
    ) -> ChatCompletionResult:
        self._consume_rate_limit_slot()
        req = self._build_json_post_request(endpoint, payload)

        full_text = ""
        finish_reason = "stop"
        tc_parts: Dict[int, Dict[str, Any]] = {}
        started_tool_stream_indices: List[int] = []
        tool_stream_callbacks_enabled = any(
            callback is not None
            for callback in (on_tool_call_start, on_tool_call_delta, on_tool_call_end)
        )

        try:
            with urllib.request.urlopen(req, timeout=self._config.request_timeout_s) as resp:
                for line in resp:
                    line = line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith(self._config.sse_data_prefix):
                        continue

                    data_str = line[len(self._config.sse_data_prefix) :]
                    if data_str == self._config.sse_done_marker:
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choice = (chunk.get("choices") or [{}])[0]
                    if isinstance(choice, dict):
                        finish_reason = str(choice.get("finish_reason") or finish_reason)
                    delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
                    if not isinstance(delta, dict):
                        delta = {}

                    reasoning = delta.get("reasoning_content", "")
                    if reasoning and on_reasoning:
                        on_reasoning(reasoning)

                    content = delta.get("content", "")
                    if content:
                        full_text += content
                        if on_token:
                            on_token(content)

                    raw_tool_calls = delta.get("tool_calls", [])
                    if isinstance(raw_tool_calls, list):
                        for part in raw_tool_calls:
                            if not isinstance(part, dict):
                                continue
                            idx = part.get("index", 0)
                            if not isinstance(idx, int):
                                idx = 0
                            entry = tc_parts.setdefault(
                                idx,
                                {
                                    "id": "",
                                    "name": "",
                                    "arguments_parts": [],
                                    "pending_stream_parts": [],
                                    "stream_started": False,
                                },
                            )
                            if isinstance(part.get("id"), str):
                                entry["id"] = part["id"]
                            fn = part.get("function", {})
                            if isinstance(fn, dict):
                                if isinstance(fn.get("name"), str):
                                    entry["name"] = fn["name"]
                                    if (
                                        not entry["stream_started"]
                                        and entry["name"]
                                        and tool_stream_callbacks_enabled
                                    ):
                                        if on_tool_call_start is not None:
                                            on_tool_call_start(entry["name"], idx)
                                        entry["stream_started"] = True
                                        started_tool_stream_indices.append(idx)
                                        pending_stream_parts = entry.get("pending_stream_parts", [])
                                        for pending_part in pending_stream_parts:
                                            if on_tool_call_delta is not None and pending_part:
                                                on_tool_call_delta(idx, pending_part)
                                        entry["pending_stream_parts"] = []
                                if isinstance(fn.get("arguments"), str):
                                    arg_delta = fn["arguments"]
                                    entry["arguments_parts"].append(arg_delta)
                                    if entry["stream_started"]:
                                        if on_tool_call_delta is not None and arg_delta:
                                            on_tool_call_delta(idx, arg_delta)
                                    else:
                                        pending = entry.get("pending_stream_parts", [])
                                        pending.append(arg_delta)
                                        entry["pending_stream_parts"] = pending
        except urllib.error.HTTPError as err:
            self._raise_http_error(err)
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e}")

        for idx in sorted(tc_parts.keys()):
            item = tc_parts[idx]
            if item.get("stream_started"):
                continue
            name = str(item.get("name", "")).strip()
            if not name or not tool_stream_callbacks_enabled:
                continue
            if on_tool_call_start is not None:
                on_tool_call_start(name, idx)
            item["stream_started"] = True
            started_tool_stream_indices.append(idx)
            pending_stream_parts = item.get("pending_stream_parts", [])
            for pending_part in pending_stream_parts:
                if on_tool_call_delta is not None and pending_part:
                    on_tool_call_delta(idx, pending_part)
            item["pending_stream_parts"] = []

        if on_tool_call_end is not None:
            for idx in sorted(set(started_tool_stream_indices)):
                on_tool_call_end(idx)

        tool_calls: List[ToolCall] = []
        for idx in sorted(tc_parts.keys()):
            item = tc_parts[idx]
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            raw_id = str(item.get("id") or f"call_{idx+1}")
            tc_id = sanitize_tool_call_id(raw_id, mode="strict")
            raw_args = "".join(item.get("arguments_parts", []))
            try:
                parsed_args = json.loads(raw_args) if raw_args else {}
                if not isinstance(parsed_args, dict):
                    parsed_args = {"raw": raw_args}
            except json.JSONDecodeError:
                parsed_args = {"raw": raw_args}
            tool_calls.append(ToolCall(id=tc_id, name=name, arguments=parsed_args))

        return ChatCompletionResult(
            content=full_text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw_response={},
            tool_calls_streamed=bool(started_tool_stream_indices),
        )

    def __del__(self):
        self.unload()

    def _consume_rate_limit_slot(self) -> None:
        """
        Guardrail to prevent runaway request storms.

        Applies to both regular and streaming requests.
        Set `max_requests_per_minute <= 0` to disable.
        """
        limit = int(self._config.max_requests_per_minute)
        if limit <= 0:
            return

        now = time.monotonic()
        cutoff = now - 60.0
        self._request_timestamps = [t for t in self._request_timestamps if t >= cutoff]

        if len(self._request_timestamps) >= limit:
            raise RuntimeError(
                f"Rate limit exceeded: more than {limit} LLM requests within 60 seconds."
            )

        self._request_timestamps.append(now)
