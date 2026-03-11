"""
AgentForge — ContextBuilder for dynamic system prompt assembly.

DESIGN PRINCIPLE: This file contains ONLY dynamic/programmatic content.
All static instructions live in workspace .md files (IDENTITY, SOUL, AGENT, USER).

Dynamic sections assembled here:
1. Runtime header (time, OS, workspace paths)
2. Available Tools (from ToolRegistry)
3. Skills XML (from SkillLoader)
4. Bootstrap files (read from workspace .md)
"""

import platform
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .__init__ import __version__

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Builds dynamic system prompts from workspace files and runtime state.

    Static content lives in .md files. This class only handles:
    - Runtime info (time, OS, paths)
    - Tool list (from ToolRegistry)
    - Skills XML (from SkillLoader)
    - Loading .md files
    """

    BOOTSTRAP_FILES = [
        "IDENTITY.md",
        "SOUL.md",
        "AGENT.md",
        "USER.md",
    ]

    def __init__(self, workspace_dir: str):
        self._workspace = Path(workspace_dir)
        self._load_errors: list[str] = []

    @property
    def load_errors(self) -> list[str]:
        """Return non-fatal file-loading errors from the latest build."""
        return list(self._load_errors)

    def build_system_prompt(
        self,
        skills_xml: str = "",
        tool_summaries: Optional[list] = None,
    ) -> str:
        """Assemble the full system prompt.

        Args:
            skills_xml: XML block from SkillLoader.build_skills_xml()
            tool_summaries: List of (name, description) tuples from ToolRegistry
        """
        sections = []

        # 1. Runtime header (programmatic — cannot live in .md)
        sections.append(self._build_runtime_header())

        # 2. Available Tools (dynamic — from ToolRegistry)
        sections.append(self._build_tools_list(tool_summaries or []))

        # 3. Skills XML (dynamic — from SkillLoader)
        if skills_xml:
            sections.append("## Available Skills\n\n" + skills_xml)

        # 4. Bootstrap files (static content from .md files)
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            sections.append(bootstrap)

        return "\n\n---\n\n".join(s for s in sections if s.strip())

    def _build_runtime_header(self) -> str:
        """Runtime info that can only be generated programmatically."""
        workspace_path = str(self._workspace.resolve())
        runtime = f"{platform.system()} {platform.machine()}, Python {sys.version.split()[0]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        return f"""## Runtime
- Agent: Agent-02 v{__version__}
- Workspace: {workspace_path}
- System: {runtime}
- Time: {now}"""

    def _build_tools_list(self, tool_summaries: list) -> str:
        """Dynamic tool list from ToolRegistry."""
        lines = ["## Available Tools", ""]

        if tool_summaries:
            for name, desc in tool_summaries:
                lines.append(f"- `{name}` - {desc}")
        else:
            lines.append("- `read_file` - Read file contents (bootstrap tool)")

        return "\n".join(lines)

    def _load_bootstrap_files(self) -> str:
        """Load workspace .md files — all static content lives here."""
        self._load_errors.clear()
        parts = []
        for filename in self.BOOTSTRAP_FILES:
            content = self._read_file(filename)
            if content:
                parts.append(content)

        return "\n\n---\n\n".join(parts) if parts else ""

    def _read_file(self, filename: str) -> str:
        """Read a file from the workspace directory."""
        path = self._workspace / filename
        if path.exists():
            try:
                return path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeDecodeError) as exc:
                msg = f"Failed to read bootstrap file '{path}': {exc}"
                self._load_errors.append(msg)
                logger.warning(msg)
                return ""
        return ""
