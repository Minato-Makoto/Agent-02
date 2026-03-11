"""
AgentForge — Web Operations tools.

Tools:
- http_request
- web_scrape

Security (strict-default):
- Block local/private/link-local targets by default
- Restrict schemes to http/https
"""

import ipaddress
import re
import socket
import logging
from typing import Any, Dict
from urllib.parse import urlparse

from agentforge.tools import Tool, ToolRegistry, ToolResult
from agentforge.runtime_config import load_tool_timeout_config


ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "169.254.169.254"}
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
logger = logging.getLogger(__name__)


def register(registry: ToolRegistry, skill_name: str = "web_operations") -> None:
    tools = [
        Tool(
            name="http_request",
            description="Make an HTTP request (GET, POST, PUT, DELETE).",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to request."},
                    "method": {"type": "string", "description": "HTTP method.", "default": "GET"},
                    "headers": {"type": "object", "description": "HTTP headers."},
                    "body": {"type": "string", "description": "Request body."},
                    "allow_private_network": {
                        "type": "boolean",
                        "description": "Allow requests to local/private addresses (unsafe).",
                        "default": False,
                    },
                },
                "required": ["url"],
            },
            execute_fn=_http_request,
        ),
        Tool(
            name="web_scrape",
            description="Fetch a web page and extract its text content.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to scrape."},
                    "selector": {
                        "type": "string",
                        "description": "CSS selector to extract specific content.",
                    },
                    "allow_private_network": {
                        "type": "boolean",
                        "description": "Allow local/private targets (unsafe).",
                        "default": False,
                    },
                },
                "required": ["url"],
            },
            execute_fn=_web_scrape,
        ),
    ]
    registry.register_skill(skill_name, tools)


def _is_private_ip(ip: str) -> bool:
    try:
        obj = ipaddress.ip_address(ip)
        return bool(
            obj.is_private
            or obj.is_loopback
            or obj.is_link_local
            or obj.is_multicast
            or obj.is_reserved
        )
    except ValueError:
        return True


def _sanitize_external_text(text: str, max_len: int = 10000) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = CONTROL_CHARS_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text[:max_len]


def _validate_url(url: str, allow_private_network: bool = False) -> tuple[bool, str]:
    if not url:
        return False, "Missing URL"

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").strip().lower()

    if scheme not in ALLOWED_SCHEMES:
        return False, f"Unsupported URL scheme: {scheme or '(empty)'}"
    if not host:
        return False, "URL host is missing"

    if not allow_private_network and host in BLOCKED_HOSTS:
        return False, f"Blocked host: {host}"

    if not allow_private_network:
        # Direct IP check
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", host) or ":" in host:
            if _is_private_ip(host):
                return False, f"Blocked private/local IP: {host}"

        # DNS resolution check
        try:
            infos = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
            for info in infos:
                sockaddr = info[4]
                ip = sockaddr[0]
                if _is_private_ip(ip):
                    return False, f"Blocked target resolved to private/local IP: {ip}"
        except socket.gaierror:
            # DNS failure should be returned as request failure later
            pass

    return True, ""


def _http_request(args: Dict[str, Any]) -> ToolResult:
    import urllib.error
    import urllib.request

    url = args.get("url", "")
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    body = args.get("body", "")
    allow_private = bool(args.get("allow_private_network", False))

    ok, reason = _validate_url(url, allow_private_network=allow_private)
    if not ok:
        return ToolResult.error_result(f"BLOCKED: {reason}")

    try:
        request_timeout = load_tool_timeout_config().web_request_s
        data = body.encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method)
        if isinstance(headers, dict):
            for k, v in headers.items():
                req.add_header(str(k), str(v))
        if "User-Agent" not in {str(k) for k in headers.keys()} if isinstance(headers, dict) else set():
            req.add_header("User-Agent", "Agent-02/2.0")

        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            content = _sanitize_external_text(resp.read().decode("utf-8", errors="replace"))
            return ToolResult(
                success=True,
                output={
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": content,
                },
            )
    except urllib.error.HTTPError as e:
        return ToolResult.error_result(f"HTTP {e.code}: {e.reason}")
    except Exception as e:
        return ToolResult.from_exception(e, context="http_request failed", logger=logger)


def _web_scrape(args: Dict[str, Any]) -> ToolResult:
    import urllib.request

    url = args.get("url", "")
    selector = args.get("selector", "")
    allow_private = bool(args.get("allow_private_network", False))

    ok, reason = _validate_url(url, allow_private_network=allow_private)
    if not ok:
        return ToolResult.error_result(f"BLOCKED: {reason}")

    try:
        request_timeout = load_tool_timeout_config().web_request_s
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Agent-02/2.0")
        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()

            if selector:
                elements = soup.select(selector)
                text = "\n".join(el.get_text(strip=True) for el in elements)
            else:
                text = soup.get_text(separator="\n", strip=True)

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return ToolResult(success=True, output=_sanitize_external_text("\n".join(lines)))
        except ImportError:
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return ToolResult(success=True, output=_sanitize_external_text(text))
    except Exception as e:
        return ToolResult.from_exception(e, context="web_scrape failed", logger=logger)
