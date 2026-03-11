"""
AgentForge - SkillLoader for MMORPG-style skill system.

3-tier priority: workspace > user config > builtin
Dynamic activation/deactivation of skills and their tools.
Generates status panel for system prompt.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None

# Skill name validation: allow alphanumeric, spaces, hyphens, underscores
# Must NOT contain XML-dangerous chars (<, >, &, ", ')
_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*$")
_SKILL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
_MAX_SKILL_NAME_LEN = 64
_MAX_SKILL_DESC_LEN = 1024


def _escape_xml(s: str) -> str:
    """Escape XML special characters."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass
class SkillInfo:
    """Metadata about a discovered skill."""

    skill_id: str
    name: str
    description: str
    skill_file: str  # absolute path to SKILL.md
    folder: str  # skill folder name
    tools: List[str]  # tool names listed in frontmatter
    module: str = ""  # Python module path (e.g. "builtin_tools.file_ops")
    active: bool = False
    source: str = ""  # "workspace", "user", or "builtin"


class SkillLoader:
    """Discovers and manages skills with 3-tier priority."""

    def __init__(self, workspace_dir: str, user_config_dir: str = "", builtin_dir: str = ""):
        self._workspace_dir = Path(workspace_dir)
        self._user_config_dir = Path(user_config_dir) if user_config_dir else None
        self._builtin_dir = Path(builtin_dir) if builtin_dir else None
        self._skills: Dict[str, SkillInfo] = {}
        self._active_skills: set = set()

    def discover(self) -> Dict[str, SkillInfo]:
        """Discover all available skills from all tiers."""
        self._skills.clear()
        self._active_skills.clear()

        if self._builtin_dir and self._builtin_dir.exists():
            self._scan_dir(self._builtin_dir, "builtin")

        if self._user_config_dir and self._user_config_dir.exists():
            self._scan_dir(self._user_config_dir, "user")

        skills_dir = self._workspace_dir / "skills"
        if skills_dir.exists():
            self._scan_dir(skills_dir, "workspace")

        return self._skills

    def get_skill(self, skill_ref: str) -> Optional[SkillInfo]:
        """Get a skill by canonical id or display name (case-insensitive)."""
        query = str(skill_ref or "").strip()
        if not query:
            return None

        direct = self._skills.get(query)
        if direct:
            return direct

        query_lower = query.lower()
        for skill_id, skill in self._skills.items():
            if skill_id.lower() == query_lower or skill.name.lower() == query_lower:
                return skill
        return None

    def activate(self, skill_ref: str) -> Optional[SkillInfo]:
        """Mark a skill as active."""
        skill = self.get_skill(skill_ref)
        if skill:
            skill.active = True
            self._active_skills.add(skill.skill_id)
        return skill

    def deactivate(self, skill_ref: str) -> Optional[SkillInfo]:
        """Mark a skill as inactive."""
        skill = self.get_skill(skill_ref)
        if skill:
            skill.active = False
            self._active_skills.discard(skill.skill_id)
        return skill

    def get_active_skills(self) -> List[SkillInfo]:
        """Get all active skills."""
        return [s for s in self._skills.values() if s.active]

    def get_all_skills(self) -> List[SkillInfo]:
        """Get all discovered skills."""
        return list(self._skills.values())

    def build_skills_xml(self) -> str:
        """Generate XML skills summary for the system prompt."""
        if not self._skills:
            return ""

        lines = ["<available_skills>"]
        for skill in self._skills.values():
            lines.append("  <skill>")
            lines.append(f"    <id>{_escape_xml(skill.skill_id)}</id>")
            lines.append(f"    <name>{_escape_xml(skill.name)}</name>")
            lines.append(f"    <description>{_escape_xml(skill.description)}</description>")
            lines.append(f"    <location>{_escape_xml(skill.skill_file)}</location>")
            if skill.active:
                lines.append(f"    <tools>{_escape_xml(', '.join(skill.tools))}</tools>")
                lines.append("    <status>ACTIVE</status>")
            else:
                lines.append("    <status>LOCKED</status>")
            lines.append("  </skill>")

        lines.append("</available_skills>")
        return "\n".join(lines)

    def build_status_panel(self) -> str:
        """Backward-compatible alias for build_skills_xml()."""
        return self.build_skills_xml()

    def find_skill_by_file(self, file_path: str) -> Optional[SkillInfo]:
        """Find which skill a SKILL.md file belongs to."""
        file_path = str(Path(file_path).resolve())
        for skill in self._skills.values():
            if str(Path(skill.skill_file).resolve()) == file_path:
                return skill
        return None

    def _scan_dir(self, skills_dir: Path, source: str) -> None:
        """Scan a directory for skill folders containing SKILL.md files."""
        if not skills_dir.is_dir():
            return

        for child in skills_dir.iterdir():
            if not child.is_dir():
                continue

            skill_path = child / "SKILL.md"
            if not skill_path.is_file():
                continue

            skill_info = self._parse_skill_file(skill_path, child.name, source)
            if skill_info:
                self._skills[skill_info.skill_id] = skill_info

    def _parse_skill_file(self, path: Path, folder: str, source: str) -> Optional[SkillInfo]:
        """Parse a SKILL.md file to extract metadata."""
        if yaml is None:
            logger.warning("PyYAML is not installed; cannot parse skill metadata: %s", path)
            return None
        try:
            content = path.read_text(encoding="utf-8")
            match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if not match:
                return None

            frontmatter = yaml.safe_load(match.group(1))
            if not frontmatter:
                return None

            skill_id = str(folder).strip()
            if not _SKILL_ID_RE.match(skill_id):
                logger.warning("Invalid skill id (folder name): %s", skill_id)
                return None

            name = str(frontmatter.get("name", skill_id)).strip() or skill_id
            description = str(frontmatter.get("description", ""))
            tools = [str(t) for t in frontmatter.get("tools", []) if isinstance(t, str)]
            module = str(frontmatter.get("module", "")).strip()

            if not _SKILL_NAME_RE.match(name):
                return None
            if len(name) > _MAX_SKILL_NAME_LEN:
                return None
            if len(description) > _MAX_SKILL_DESC_LEN:
                description = description[:_MAX_SKILL_DESC_LEN]

            if name.lower() != skill_id.lower():
                logger.warning(
                    "Skill name/id mismatch: id='%s' name='%s'. Using folder id as canonical.",
                    skill_id,
                    name,
                )

            return SkillInfo(
                skill_id=skill_id,
                name=name,
                description=description,
                skill_file=str(path.resolve()),
                folder=skill_id,
                tools=tools,
                module=module,
                source=source,
            )
        except (OSError, UnicodeDecodeError, ValueError, TypeError):
            return None
