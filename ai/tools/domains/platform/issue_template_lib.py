"""Built-in issue templates and lightweight GitHub template YAML parsing."""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
  "bug": {
    "id": "bug",
    "name": "Bug report",
    "description": "软件缺陷报告",
    "labels": ["bug"],
    "fields": [
      {"id": "description", "label": "Describe the bug", "type": "textarea", "required": True},
      {"id": "repro", "label": "Steps to reproduce", "type": "textarea", "required": False},
      {"id": "expected", "label": "Expected behavior", "type": "textarea", "required": False},
      {"id": "actual", "label": "Actual behavior", "type": "textarea", "required": False},
      {"id": "route", "label": "Route (if applicable)", "type": "input", "required": False},
      {"id": "version", "label": "Version / commit", "type": "input", "required": False},
      {"id": "extra", "label": "Additional info", "type": "textarea", "required": False},
    ],
  },
  "feature": {
    "id": "feature",
    "name": "Feature request",
    "description": "功能建议",
    "labels": ["enhancement"],
    "fields": [
      {"id": "problem", "label": "Problem / use case", "type": "textarea", "required": True},
      {"id": "proposal", "label": "Proposed solution", "type": "textarea", "required": True},
      {"id": "alternatives", "label": "Alternatives considered", "type": "textarea", "required": False},
      {"id": "extra", "label": "Additional context", "type": "textarea", "required": False},
    ],
  },
  "assistant": {
    "id": "assistant",
    "name": "op助手 issue",
    "description": "op助手 Web / AI 相关问题",
    "labels": ["ai-assistant", "bug"],
    "fields": [
      {"id": "page", "label": "Page / feature", "type": "input", "required": True},
      {"id": "description", "label": "Description", "type": "textarea", "required": True},
      {"id": "repro", "label": "Reproduction steps", "type": "textarea", "required": False},
      {"id": "expected", "label": "Expected", "type": "textarea", "required": False},
      {"id": "actual", "label": "Actual", "type": "textarea", "required": False},
      {"id": "extra", "label": "Additional info", "type": "textarea", "required": False},
    ],
  },
  "suggestion": {
    "id": "suggestion",
    "name": "Suggestion",
    "description": "体验反馈与改进建议",
    "labels": ["enhancement"],
    "fields": [
      {"id": "summary", "label": "Summary", "type": "textarea", "required": True},
      {"id": "benefit", "label": "Expected benefit", "type": "textarea", "required": False},
      {"id": "extra", "label": "Additional context", "type": "textarea", "required": False},
    ],
  },
  "tuning": {
    "id": "tuning",
    "name": "Tuning help",
    "description": "驾驶手感 / 调参",
    "labels": ["tuning", "ai-assistant"],
    "fields": [
      {"id": "vehicle", "label": "Vehicle", "type": "input", "required": True},
      {"id": "feel", "label": "Current driving feel", "type": "textarea", "required": True},
      {"id": "goal", "label": "Desired change", "type": "textarea", "required": False},
      {"id": "route", "label": "Route name", "type": "input", "required": False},
    ],
  },
  "adaptation": {
    "id": "adaptation",
    "name": "Vehicle adaptation",
    "description": "新车适配",
    "labels": ["vehicle-adaptation", "ai-assistant"],
    "fields": [
      {"id": "vehicle", "label": "Vehicle", "type": "input", "required": True},
      {"id": "fork", "label": "Fork", "type": "input", "required": False},
      {"id": "description", "label": "Details", "type": "textarea", "required": True},
    ],
  },
  "openpilot_pc": {
    "id": "openpilot_pc",
    "name": "PC bug report",
    "description": "PC 端 openpilot 问题",
    "labels": ["PC", "bug"],
    "fields": [
      {"id": "description", "label": "Describe the bug", "type": "textarea", "required": True},
      {"id": "os", "label": "OS Version", "type": "input", "required": True},
      {"id": "version", "label": "openpilot version or commit", "type": "input", "required": False},
      {"id": "extra", "label": "Additional info", "type": "textarea", "required": False},
    ],
  },
}


def list_builtin_templates() -> list[dict[str, Any]]:
  return [dict(t) for t in BUILTIN_TEMPLATES.values()]


def get_builtin_template(template_id: str) -> dict[str, Any] | None:
  t = BUILTIN_TEMPLATES.get((template_id or "").strip().lower())
  return dict(t) if t else None


def _parse_github_issue_yaml(text: str, filename: str = "") -> dict[str, Any] | None:
  """Minimal parser for GitHub issue form YAML (no PyYAML dependency)."""
  name_m = re.search(r"^name:\s*(.+)$", text, re.M)
  desc_m = re.search(r"^description:\s*(.+)$", text, re.M)
  if not name_m:
    return None
  labels: list[str] = []
  for lm in re.finditer(r'labels:\s*\[(.*?)\]', text, re.S):
    inner = lm.group(1)
    labels.extend(re.findall(r'"([^"]+)"|\'([^\']+)\'|(\w[\w-]*)', inner))
    labels = [x for tup in labels for x in tup if x]
  fields: list[dict[str, Any]] = []
  blocks = re.split(r"\n\s*-\s+type:\s*", text)
  for block in blocks[1:]:
    ftype_m = re.match(r"(\w+)", block)
    ftype = ftype_m.group(1) if ftype_m else "textarea"
    if ftype == "markdown":
      continue
    id_m = re.search(r"\n\s*id:\s*(\S+)", block)
    label_m = re.search(r"\n\s*label:\s*(.+)", block)
    req_m = re.search(r"required:\s*true", block, re.I)
    fields.append({
      "id": id_m.group(1) if id_m else f"field_{len(fields)}",
      "label": (label_m.group(1).strip() if label_m else "Field"),
      "type": "input" if ftype == "input" else "textarea",
      "required": bool(req_m),
    })
  tid = Path(filename).stem if filename else re.sub(r"[^a-z0-9]+", "_", name_m.group(1).lower()).strip("_")
  return {
    "id": tid,
    "name": name_m.group(1).strip().strip('"').strip("'"),
    "description": (desc_m.group(1).strip().strip('"').strip("'") if desc_m else ""),
    "labels": labels or ["bug"],
    "fields": fields or [{"id": "description", "label": "Description", "type": "textarea", "required": True}],
    "source": "repo",
  }


def load_local_repo_templates(git_root: Path) -> list[dict[str, Any]]:
  out: list[dict[str, Any]] = []
  for sub in (".github/ISSUE_TEMPLATE", ".gitee/ISSUE_TEMPLATE"):
    base = git_root / sub
    if not base.is_dir():
      continue
    for path in sorted(base.glob("*.yml")) + sorted(base.glob("*.yaml")):
      try:
        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = _parse_github_issue_yaml(text, path.name)
        if parsed:
          parsed["path"] = str(path.relative_to(git_root)).replace("\\", "/")
          out.append(parsed)
      except OSError:
        continue
  return out


def render_issue_body(template: dict[str, Any], fields: dict[str, str], *, footer: str = "") -> str:
  lines: list[str] = []
  for spec in template.get("fields") or []:
    fid = spec.get("id") or ""
    label = spec.get("label") or fid
    val = (fields.get(fid) or fields.get(label) or "").strip()
    if not val:
      continue
    lines.append(f"### {label}")
    lines.append("")
    lines.append(val)
    lines.append("")
  if footer.strip():
    lines.append("---")
    lines.append("")
    lines.append(footer.strip())
  return "\n".join(lines).strip()


def decode_github_content(data: dict[str, Any]) -> str:
  if data.get("encoding") == "base64" and data.get("content"):
    raw = data["content"].replace("\n", "")
    return base64.b64decode(raw).decode("utf-8", errors="replace")
  return str(data.get("content") or "")
