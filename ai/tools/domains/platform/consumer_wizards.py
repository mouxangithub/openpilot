"""Owner-facing guided workflows for OP Agent (maps to internal workflows)."""

from __future__ import annotations

from typing import Any

CONSUMER_WIZARDS: list[dict[str, Any]] = [
  {
    "id": "adapt_new_car",
    "name": "适配新车",
    "icon": "🚗",
    "description": "认车、指纹、CAN 信号，生成适配草稿（不需懂编程）",
    "workflow_id": "vehicle_adaptation",
    "slash": ["/适配新车", "/adapt", "/新车"],
    "starter_prompt": "我想适配一辆新车，请用通俗中文一步步带我完成认车和指纹检查。",
    "consumer_mode": True,
  },
  {
    "id": "tune_feel",
    "name": "调驾驶手感",
    "icon": "🎛️",
    "description": "跟车距离、变道风格、加减速舒适度",
    "workflow_id": "tune_session",
    "slash": ["/调手感", "/tune", "/调优"],
    "starter_prompt": "帮我调一下驾驶手感：先了解我现在的设置，再建议最小改动。用大白话解释每一项。",
    "consumer_mode": True,
  },
  {
    "id": "cant_engage",
    "name": "开不起来排查",
    "icon": "🚦",
    "description": "无法 Engage、SecOC、指纹、摄像头等常见原因",
    "workflow_id": "engage_triage",
    "slash": ["/开不起来", "/engage", "/排查"],
    "starter_prompt": "我的车开不起来（无法 engage），请按检查表帮我排查，用我能听懂的话说明原因和下一步。",
    "consumer_mode": True,
  },
  {
    "id": "review_trip",
    "name": "复盘上一趟",
    "icon": "📝",
    "description": "停车后总结本趟表现并给出调优建议",
    "workflow_id": "post_drive_review",
    "slash": ["/复盘", "/trip", "/上一趟"],
    "starter_prompt": "帮我复盘最近一趟路，总结表现并给出是否需要调参的建议。",
    "consumer_mode": True,
  },
]


def list_consumer_wizards() -> list[dict[str, Any]]:
  return [dict(w) for w in CONSUMER_WIZARDS]


def get_consumer_wizard(wizard_id: str) -> dict[str, Any] | None:
  for w in CONSUMER_WIZARDS:
    if w.get("id") == wizard_id:
      return dict(w)
  return None


def resolve_wizard_by_slash(text: str) -> dict[str, Any] | None:
  raw = (text or "").strip().split()[0] if text else ""
  if not raw.startswith("/"):
    return None
  needle = raw.lower()
  for w in CONSUMER_WIZARDS:
    for alias in w.get("slash") or []:
      if alias.lower() == needle or alias.lower().lstrip("/") == needle.lstrip("/"):
        return dict(w)
  return None
