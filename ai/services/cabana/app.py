"""Cabana backend facade — re-exports for tools and server registration."""

from ai.services.cabana.routes import register_routes
from ai.services.cabana.dbc import (
  _list_dbc_names,
  _load_dbc_content,
  _parse_dbc_signals,
)
from ai.services.cabana.handlers import warm_dbc_catalog
from ai.services.cabana.live import LIVE_CAN, LiveCanBroadcaster, ws_live
from ai.services.cabana.ai_explain import cabana_analyze_tool, cabana_explain_signal_tool
from ai.services.cabana.replay import (
  _find_qlogs,
  _find_rlogs,
  _get_routes_dir,
  _list_route_media,
  _list_routes,
  _replay_log_paths,
  _route_date_label,
  _route_dir,
)

# Public alias used by tools
_pick_can_log_paths = _replay_log_paths

__all__ = [
  "register_routes",
  "warm_dbc_catalog",
  "LIVE_CAN",
  "LiveCanBroadcaster",
  "cabana_analyze_tool",
  "cabana_explain_signal_tool",
]
