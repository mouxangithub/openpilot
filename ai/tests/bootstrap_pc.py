"""Install PC openpilot mocks before importing ai modules in unit tests."""

from __future__ import annotations

from ai.dev.run_pc import _install_openpilot_mocks

_install_openpilot_mocks()
