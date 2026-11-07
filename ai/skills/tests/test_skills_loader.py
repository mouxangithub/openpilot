"""Tests for ai.skills.loader frontmatter parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai.skills.loader import (
  SkillFrontmatter,
  _parse_frontmatter,
  load_skill_body_by_id,
  parse_skill_frontmatter,
)


SAMPLE_SKILL = """---
name: Test Skill
version: 1.2.3
scope: test
trust: high
triggers:
  - test
  - demo
---

# Body

Some skill content.
"""


def test_parse_frontmatter():
  frontmatter, body = _parse_frontmatter(SAMPLE_SKILL)
  assert frontmatter.name == "Test Skill"
  assert frontmatter.version == "1.2.3"
  assert frontmatter.scope == "test"
  assert frontmatter.trust == "high"
  assert frontmatter.triggers == ["test", "demo"]
  assert "# Body" in body


def test_parse_no_frontmatter():
  text = "# Just body\n\ncontent"
  frontmatter, body = _parse_frontmatter(text)
  assert frontmatter.name == ""
  assert body == text


def test_frontmatter_defaults():
  fm = SkillFrontmatter()
  assert fm.trust == "normal"
  assert fm.triggers == []


def test_load_skill_body_by_id_unknown():
  result = load_skill_body_by_id("definitely-not-a-real-skill-id")
  assert result["ok"] is False
