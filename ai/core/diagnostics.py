"""G12 startup dependency diagnostics with stable error-code aggregation.

Runs a set of cheap, dependency-agnostic startup checks and returns a structured
report. Each check yields ``{ok, name, severity, message, error_code}``. The
aggregate returns ``{ok, startupDiag}`` where ``ok`` is True unless a ``fatal``
check failed. ``run_startup_diagnostics()`` NEVER raises, so ``aid.py`` can call
it unconditionally at boot.
"""
from __future__ import annotations

import importlib
from typing import Any

from ai.core.errors import ERR_STARTUP_DIAG


class DiagnosticsResult:
  def __init__(self, checks: list[dict[str, Any]]) -> None:
    self.checks = checks

  @property
  def ok(self) -> bool:
    return not any(c["severity"] == "fatal" and not c["ok"] for c in self.checks)

  def to_dict(self) -> dict[str, Any]:
    return {"ok": self.ok, "checks": list(self.checks)}


def _check_import(module: str, *, fatal: bool = True) -> dict[str, Any]:
  try:
    importlib.import_module(module)
    return {"name": f"import:{module}", "ok": True, "severity": "fatal" if fatal else "warning",
            "message": "ok", "error_code": ""}
  except Exception as e:
    return {"name": f"import:{module}", "ok": False, "severity": "fatal" if fatal else "warning",
            "message": str(e), "error_code": ERR_STARTUP_DIAG}


def run_checks(params: Any = None) -> list[dict[str, Any]]:
  checks: list[dict[str, Any]] = []
  # Core modules that must resolve for the assistant to serve requests.
  for mod in ("ai.core.session.log", "ai.core.errors", "ai.config", "ai.core.agent.state"):
    checks.append(_check_import(mod, fatal=True))
  # Optional/hardware-gated modules degrade gracefully (non-fatal).
  for mod in (
    "ai.core.llm.model_router",
    "ai.tools.harness_tools",
    "ai.tools.agent_tools",
    "ai.mcp.host",
    "ai.bundle.store",
    "ai.tools.domains.platform.workflow_graph",
  ):
    checks.append(_check_import(mod, fatal=False))
  if params is not None:
    try:
      params.keys()
      checks.append({"name": "params", "ok": True, "severity": "fatal", "message": "ok", "error_code": ""})
    except Exception as e:
      checks.append({"name": "params", "ok": False, "severity": "fatal", "message": str(e), "error_code": ERR_STARTUP_DIAG})
  return checks


def run_startup_diagnostics(params: Any = None) -> DiagnosticsResult:
  """Run startup checks, never raising. Safe to call at boot."""
  try:
    return DiagnosticsResult(run_checks(params=params))
  except Exception as e:  # pragma: no cover - defensive; never propagate
    return DiagnosticsResult([{
      "name": "startup", "ok": False, "severity": "fatal",
      "message": str(e), "error_code": ERR_STARTUP_DIAG,
    }])
