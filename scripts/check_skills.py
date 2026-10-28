#!/usr/bin/env python3
"""Validate skills and project agents.

Checks, without third-party dependencies:

- every skills/<id>/SKILL.md has frontmatter with a name equal to <id> and a
  non-empty description;
- every .opencode/agents/*.md has a description, a valid mode and complete
  permission rules;
- every relative markdown link resolves to a file;
- every skill is linked from .opencode/skills, .agents/skills and
  .claude/skills, and no link is broken.

Run from anywhere: python3 scripts/check_skills.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
AGENTS_DIR = ROOT / ".opencode" / "agents"
HARNESSES = (
    ROOT / ".opencode" / "skills",
    ROOT / ".agents" / "skills",
    ROOT / ".claude" / "skills",
)
MODES = {"primary", "subagent", "all"}
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
KEY = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        fail(f"{path.relative_to(ROOT)}: missing frontmatter")
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        fail(f"{path.relative_to(ROOT)}: unclosed frontmatter")
        return {}

    lines = text[4:end].splitlines()
    data: dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = KEY.match(lines[index])
        if not match:
            index += 1
            continue
        key, value = match.group(1), match.group(2).strip()
        if value in {">", ">-", "|", "|-"}:
            buffered: list[str] = []
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index].startswith(("  ", "\t"))):
                buffered.append(lines[index].strip())
                index += 1
            value = " ".join(part for part in buffered if part)
        else:
            index += 1
        data[key] = value
    return data


def check_links(path: Path) -> None:
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        target = target.strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        file_part = target.split("#", 1)[0]
        if not file_part:
            continue
        resolved = (path.parent / file_part).resolve()
        if not resolved.exists():
            fail(f"{path.relative_to(ROOT)}: broken link {target}")


def check_permissions(path: Path, text: str) -> None:
    if "permissions:" not in text:
        return
    block = text.split("permissions:", 1)[1]
    block = block.split("\n---", 1)[0]
    rules = [chunk for chunk in re.split(r"^\s*-\s+action:", block, flags=re.MULTILINE)[1:]]
    if not rules:
        fail(f"{path.relative_to(ROOT)}: permissions without rules")
    for rule in rules:
        for field in ("resource:", "effect:"):
            if field not in rule:
                fail(f"{path.relative_to(ROOT)}: permission rule without {field[:-1]}")


def main() -> int:
    skills = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    if not skills:
        fail("skills/: no SKILL.md found")

    for skill in skills:
        folder = skill.parent.name
        meta = parse_frontmatter(skill)
        if meta.get("name") != folder:
            fail(f"{skill.relative_to(ROOT)}: name {meta.get('name')!r} does not match folder {folder!r}")
        if not meta.get("description"):
            fail(f"{skill.relative_to(ROOT)}: empty description")
        check_links(skill)
        for extra in skill.parent.rglob("*.md"):
            if extra != skill:
                check_links(extra)

    for harness in HARNESSES:
        if not harness.is_dir():
            fail(f"{harness.relative_to(ROOT)}: missing harness directory")
            continue
        for link in sorted(harness.iterdir()):
            if not link.is_symlink():
                fail(f"{link.relative_to(ROOT)}: not a symlink")
                continue
            if not link.exists():
                fail(f"{link.relative_to(ROOT)}: broken symlink")
                continue
            if link.resolve().parent != SKILLS_DIR:
                fail(f"{link.relative_to(ROOT)}: points outside skills/")
        for skill in skills:
            link = harness / skill.parent.name
            if not link.is_symlink() or link.resolve() != skill.parent.resolve():
                fail(f"{link.relative_to(ROOT)}: missing or wrong symlink")

    if AGENTS_DIR.is_dir():
        for agent in sorted(AGENTS_DIR.glob("*.md")):
            meta = parse_frontmatter(agent)
            if not meta.get("description"):
                fail(f"{agent.relative_to(ROOT)}: empty description")
            mode = meta.get("mode")
            if mode and mode not in MODES:
                fail(f"{agent.relative_to(ROOT)}: invalid mode {mode!r}")
            check_permissions(agent, agent.read_text(encoding="utf-8"))

    if errors:
        print("skills check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        f"skills check ok: {len(skills)} skills, "
        f"{len(list(AGENTS_DIR.glob('*.md'))) if AGENTS_DIR.is_dir() else 0} agents, "
        f"{len(HARNESSES)} harnesses"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
