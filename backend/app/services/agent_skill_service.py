"""读取 backend/app/agent_skills/*/SKILL.md（YAML frontmatter + 正文）。

frontmatter 用极简正则解析单行 `key: value`（约束只写 name/description 单行值），
避免引入 PyYAML 依赖。name 白名单校验防路径穿越。
"""

import re
from pathlib import Path

AGENT_SKILLS_DIR = Path(__file__).resolve().parent.parent / "agent_skills"
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """解析 `---\nkey: value\n---\n正文`，返回 (meta, body)。"""
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", text, re.DOTALL)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip("'\"")
    return meta, m.group(2)


def list_skills() -> list[dict]:
    """遍历 */SKILL.md，按 name 排序返回摘要 [{name, description}]。"""
    if not AGENT_SKILLS_DIR.exists():
        return []
    skills = []
    for skill_md in sorted(AGENT_SKILLS_DIR.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, _ = _parse_frontmatter(text)
        skills.append({
            "name": meta.get("name", skill_md.parent.name),
            "description": meta.get("description", ""),
        })
    return sorted(skills, key=lambda s: s["name"])


def get_install_info() -> dict:
    """Skills 安装信息：源目录 + 各客户端安装命令。

    Claude Code 与 Trae CLI 的 Skill 格式一致（<name>/SKILL.md），
    安装即把源目录下各 skill 目录复制到对应 skills 目录。
    """
    src = str(AGENT_SKILLS_DIR)
    return {
        "source_dir": src,
        "clients": [
            {
                "client": "Claude Code",
                "user_dir": "~/.claude/skills",
                "project_dir": ".claude/skills",
                "command": f"mkdir -p ~/.claude/skills && cp -R {src}/* ~/.claude/skills/",
            },
            {
                "client": "Trae CLI",
                "user_dir": "~/.agents/skills",
                "project_dir": ".agents/skills",
                "command": f"mkdir -p ~/.agents/skills && cp -R {src}/* ~/.agents/skills/",
            },
        ],
    }


def get_skill(name: str) -> dict:
    """按 name 返回 {name, description, content}。不存在或非法抛 KeyError。"""
    if not _NAME_RE.match(name):
        raise KeyError(name)
    skill_md = AGENT_SKILLS_DIR / name / "SKILL.md"
    if not skill_md.is_file():
        raise KeyError(name)
    text = skill_md.read_text(encoding="utf-8")
    meta, _ = _parse_frontmatter(text)
    return {
        "name": meta.get("name", name),
        "description": meta.get("description", ""),
        "content": text,
    }
