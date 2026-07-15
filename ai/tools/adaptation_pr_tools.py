"""Generate adaptation PR draft markdown (no git push)."""

from __future__ import annotations

from typing import Any

from ai.system.paths import openpilot_root
from ai.tools.git_tools import git_diff, git_status


def generate_adaptation_pr_draft(
  *,
  project_name: str = "",
  draft_id: str = "",
  summary: str = "",
) -> dict[str, Any]:
  """Build PR description from adaptation draft + current git diff."""
  name = (project_name or draft_id or "vehicle-adaptation").strip()
  status = git_status()
  diff_stat = git_diff(stat=True)

  body_parts = [
    f"## {name}",
    "",
    "### Summary",
    (summary or "New vehicle adaptation draft from op助手.").strip(),
    "",
    "### Git status",
    f"- Branch: `{status.get('branch')}` @ `{status.get('head')}`",
    f"- Dirty files: {status.get('dirty_count', 0)}",
    "",
    "### Diff stat",
    "```",
    (diff_stat.get("stdout") or "(no diff)")[:4000],
    "```",
    "",
    "### Checklist",
    "- [ ] Fingerprint verified on closed course",
    "- [ ] car_porting_test_interfaces passed",
    "- [ ] car_porting_steering_accuracy reviewed",
    "- [ ] No direct opendbc production edits without review",
    "",
    f"Root: `{openpilot_root()}`",
  ]

  if draft_id:
    body_parts.insert(4, f"- Draft ID: `{draft_id}`")

  markdown = "\n".join(body_parts)
  return {
    "ok": True,
    "title": f"feat(car): adapt {name}",
    "markdown": markdown,
    "branch": status.get("branch"),
    "hint": "Review markdown, then git_commit locally. No auto push.",
  }
