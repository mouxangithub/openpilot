"""
Safety policy for the AI agent.

Default (admin) mode: all actions allowed except direct vehicle control.
Legacy mode (ai_admin_mode=0): stationary-only writes and driving blocks.
"""

from dataclasses import dataclass
from enum import Enum

from ai.selfdrive.state import VehicleState

# The only action that is never allowed — no tool exists for this path.
_DIRECT_CONTROL_ACTIONS = frozenset({"control_actuator"})


class ActionCategory(str, Enum):
  READ_ONLY = "read_only"       # Always allowed (queries, analysis, chat).
  CONFIG_WRITE = "config_write" # Allowed only when stationary / offroad.
  SERVICE_CONTROL = "service_control"  # Allowed only when stationary / offroad.
  SHELL_READ = "shell_read"     # Allowed only when stationary / offroad.
  FORBIDDEN = "forbidden"       # Never allowed (direct actuator control only).


@dataclass(frozen=True)
class ActionRule:
  category: ActionCategory
  description: str


# Examples of user-facing actions the agent may be asked to perform.
ACTION_RULES: dict[str, ActionRule] = {
  # Chat / read-only
  "chat": ActionRule(ActionCategory.READ_ONLY, "General chat or analysis"),
  "explain": ActionRule(ActionCategory.READ_ONLY, "Explain a status or error"),
  "status": ActionRule(ActionCategory.READ_ONLY, "Report openpilot / vehicle status"),
  "read_params": ActionRule(ActionCategory.READ_ONLY, "Read Params"),
  "read_can": ActionRule(ActionCategory.READ_ONLY, "Read CAN messages"),
  "cabana_analyze": ActionRule(ActionCategory.READ_ONLY, "Analyze CAN data with AI"),

  # Config writes (stationary only)
  "write_ai_config": ActionRule(ActionCategory.CONFIG_WRITE, "Update AI agent settings"),
  "write_param": ActionRule(ActionCategory.CONFIG_WRITE, "Write a non-safety-critical Param"),

  # Service control (stationary only)
  "restart_service": ActionRule(ActionCategory.SERVICE_CONTROL, "Restart a software service"),
  "restart_ui": ActionRule(ActionCategory.SERVICE_CONTROL, "Restart the UI"),

  # Shell
  "shell": ActionRule(ActionCategory.SHELL_READ, "Run a shell command"),

  # Service / power (allowed in open mode)
  "reboot_now": ActionRule(ActionCategory.SERVICE_CONTROL, "Reboot the device"),
  "shutdown_now": ActionRule(ActionCategory.SERVICE_CONTROL, "Shut down the device"),

  # Direct vehicle control — permanently forbidden
  "control_actuator": ActionRule(ActionCategory.FORBIDDEN, "Send actuator / steering / brake commands"),
}


def is_action_allowed(action: str, state: VehicleState, *, admin: bool = False) -> tuple[bool, str]:
  """Return (allowed, reason). Open mode: only direct vehicle control is blocked."""
  if admin:
    if action in _DIRECT_CONTROL_ACTIONS:
      return False, "Direct vehicle control (steering/brake/throttle) is permanently forbidden."
    return True, ""

  rule = ACTION_RULES.get(action)
  if rule is None:
    return False, f"Unknown action '{action}'. Refusing for safety."

  if rule.category == ActionCategory.READ_ONLY:
    return True, ""

  if rule.category == ActionCategory.FORBIDDEN:
    return False, f"Action '{action}' is permanently forbidden: {rule.description}."

  if getattr(state, "reader_unavailable", False):
    return False, "Vehicle state unavailable; refusing action for safety."

  if state.is_driving:
    return False, (
      f"Action '{action}' ({rule.description}) is blocked while driving "
      f"(vEgo={state.v_ego:.2f} m/s, enabled={state.enabled}, started={state.started}, "
      f"ignition={state.ignition}). Stop the vehicle first."
    )

  return True, ""


def require_stationary(state: VehicleState) -> None:
  """Raise if the vehicle appears to be driving."""
  if state.is_driving:
    raise RuntimeError(
      f"Refused: vehicle is driving (vEgo={state.v_ego:.2f} m/s, enabled={state.enabled})."
    )
