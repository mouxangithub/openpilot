"""Compatibility shim — use sp_settings for openpilot catalog."""

from ai.tools.domains.tune.sp_settings import list_dp_settings, list_sp_settings

__all__ = ["list_dp_settings", "list_sp_settings"]
