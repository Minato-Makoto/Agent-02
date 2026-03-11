"""
AgentForge — Web Search tool (DuckDuckGo HTML scraping).

Zero-dependency web search via DuckDuckGo HTML.
"""

import re
import urllib.request
import urllib.parse
import urllib.error
import logging
from html import unescape
from typing import Any, Dict, List

from agentforge.tools import Tool, ToolRegistry, ToolResult
from agentforge.runtime_config import load_tool_timeout_config

logger = logging.getLogger(__name__)


def register(registry: ToolRegistry, skill_name: str = "web_search") -> None:
    """Register web search tools."""
    tools = [
        Tool(
            name="web_search",
            description="Search the web using DuckDuckGo. Returns titles, URLs, and descriptions for the top results. Use this to find current information, documentation, or answers not in your training data.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query."
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results to return (1-10).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
            execute_fn=_web_search,
        ),
    ]
    registry.register_skill(skill_name, tools)


def _web_search(args: Dict[str, Any]) -> ToolResult:
    query = args.get("query", "")
    count = min(max(args.get("count", 5), 1), 10)

    if not query:
        return ToolResult.error_result("Missing 'query'")

    try:
        results = _search_duckduckgo(query, count)
        if not results:
            return ToolResult.llm_result(
                for_llm=f"No results found for: {query}",
                for_user=f"🔍 No results for: {query}",
            )

        # Format for LLM (concise, structured)
        llm_lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            llm_lines.append(f"{i}. {r['title']}")
            llm_lines.append(f"   URL: {r['url']}")
            if r.get("snippet"):
                llm_lines.append(f"   {r['snippet']}")
            llm_lines.append("")

        # Format for user (readable)
        user_lines = [f"🔍 **{query}** — {len(results)} results\n"]
        for i, r in enumerate(results, 1):
            user_lines.append(f"  {i}. {r['title']}")
            user_lines.append(f"     {r['url']}")

        return ToolResult.llm_result(
            for_llm="\n".join(llm_lines),
            for_user="\n".join(user_lines),
        )
    except Exception as e:
        return ToolResult.from_exception(e, context="Search failed", logger=logger)


def _search_duckduckgo(query: str, count: int = 5) -> List[Dict[str, str]]:
    """Search DuckDuckGo HTML and extract results (zero dependency)."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Agent-02/2.0")

    with urllib.request.urlopen(req, timeout=load_tool_timeout_config().web_search_s) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    results = []

    # Extract result blocks — DuckDuckGo HTML uses <a class="result__a"> for titles
    # and <a class="result__snippet"> for descriptions
    title_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL
    )
    snippet_pattern = re.compile(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL
    )

    titles = title_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (raw_url, raw_title) in enumerate(titles[:count]):
        # Clean HTML tags from title
        title = re.sub(r'<[^>]+>', '', raw_title).strip()
        title = unescape(title)

        # Resolve DuckDuckGo redirect URL
        actual_url = raw_url
        if "uddg=" in raw_url:
            match = re.search(r'uddg=([^&]+)', raw_url)
            if match:
                actual_url = urllib.parse.unquote(match.group(1))

        # Get snippet if available
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            snippet = unescape(snippet)

        if title:
            results.append({
                "title": title,
                "url": actual_url,
                "snippet": snippet,
            })

    return results
