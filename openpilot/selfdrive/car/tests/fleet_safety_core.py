"""Offline emitted-CAN audit primitives; not a vehicle or selfdrived acceptance test.

Ported from StarPilot (MIT). Adapted for this tree: CarParamsSP carries no
safetyConfigs (CP-only config), libsafety has no get_aol_allowed, and the
fork's lateral-keep feature is MADS rather than AOL.
"""

from collections import Counter
from dataclasses import dataclass


def _integer(value, name, low, high):
  if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
    raise ValueError(f"{name} must be an integer in [{low}, {high}]")
  return value


@dataclass(frozen=True)
class EffectiveSafetyConfig:
  panda_index: int
  safety_model: int
  safety_param: int
  alternative_experience: int

  def __post_init__(self):
    _integer(self.panda_index, "panda_index", 0, 63)
    for name in ("safety_model", "safety_param", "alternative_experience"):
      _integer(getattr(self, name), name, 0, 65535)

  def local_bus(self, global_bus):
    """Match pandad's bus-offset routing, without modulo aliasing another panda."""
    _integer(global_bus, "global_bus", 0, 255)
    offset = self.panda_index * 4
    if not offset <= global_bus < offset + 4:
      raise ValueError(f"global bus {global_bus} does not belong to panda {self.panda_index}")
    return global_bus - offset


def effective_safety_configs(CP, CP_SP=None, *, panda_count=None):
  """Mirror PandaSafety::setSafetyMode; pass the actual panda count when known.

  Without that count, represent all configured pandas (at least one).
  CarParamsSP carries no safetyConfigs in this fork, so only CP contributes.
  """
  configs = tuple(CP.safetyConfigs)
  count = max(len(configs), 1) if panda_count is None else panda_count
  _integer(count, "panda_count", 0, 64)
  # Both capnp fields are Int16, assigned/ORed into a uint16_t in pandad.
  alternative = _integer(CP.alternativeExperience, "CP.alternativeExperience", -32768, 32767) & 65535
  result = []
  for i in range(count):
    model, param = 0, 0  # cereal::CarParams::SafetyModel::SILENT
    if i < len(configs):
      model = getattr(configs[i].safetyModel, "raw", configs[i].safetyModel)
      param = _integer(configs[i].safetyParam, "CP.safetyParam", 0, 65535)
    result.append(EffectiveSafetyConfig(i, model, param, alternative))
  return tuple(result)


@dataclass(frozen=True)
class Permissions:
  controls_allowed: bool
  aol_allowed: bool
  longitudinal_allowed: bool

  @property
  def active(self):
    return self.controls_allowed or self.aol_allowed or self.longitudinal_allowed

  @property
  def label(self):
    return "+".join(name for name, value in (("controls", self.controls_allowed), ("aol", self.aol_allowed),
                                           ("long", self.longitudinal_allowed)) if value) or "inactive"


@dataclass(frozen=True)
class TxRecord:
  addr: int
  bus: int
  local_bus: int
  data: bytes
  timestamp_ns: int
  scenario: str
  permissions: Permissions
  requested_lat_active: bool | None
  requested_long_active: bool | None
  accepted: bool | None
  expected_block_reason: str | None
  failure: str | None

  @property
  def requested_mode(self):
    # Retain partially unknown states; do not turn unknown into inactive.
    values = {True: "active", False: "inactive", None: "unknown"}
    return f"lat:{values[self.requested_lat_active]},long:{values[self.requested_long_active]}"

  @property
  def requested_active(self):
    return self.requested_lat_active is True or self.requested_long_active is True


class TxAudit:
  """One safety instance per panda. Caller supplies recorded RX and clock updates.

  check() records rejected packets instead of raising so every emitted packet can
  be audited. The caller must consume summary()['status']; 'uncovered' is not a
  pass. Hook/factory exceptions are recorded and re-raised. Expected negative
  cases require a reason on each packet and fail if the hook accepts that packet.
  """

  def __init__(self, safety, packet_factory, *, config):
    self.safety, self.packet_factory, self.config = safety, packet_factory, config
    self._records = []

  @property
  def records(self):
    return tuple(self._records)

  def check(self, addr, bus, data, timestamp_ns, scenario, *, expected_block_reason=None,
            requested_lat_active=None, requested_long_active=None):
    _integer(addr, "addr", 0, 0x1FFFFFFF)
    _integer(timestamp_ns, "timestamp_ns", 0, 2**64 - 1)
    local_bus = self.config.local_bus(bus)
    if not isinstance(scenario, str) or not scenario.strip():
      raise ValueError("scenario must be nonempty")
    if expected_block_reason is not None and (not isinstance(expected_block_reason, str) or not expected_block_reason.strip()):
      raise ValueError("expected_block_reason must be a nonempty per-packet reason")
    for value in (requested_lat_active, requested_long_active):
      if value is not None and type(value) is not bool:
        raise ValueError("requested activity must be bool or None")
    if not isinstance(data, (bytes, bytearray, memoryview)):
      raise ValueError("data must be bytes-like")
    payload = bytes(data)
    get_aol_allowed = getattr(self.safety, "get_aol_allowed", lambda: False)
    permissions = Permissions(bool(self.safety.get_controls_allowed()), bool(get_aol_allowed()),
                              bool(self.safety.get_longitudinal_allowed()))
    accepted, failure = None, None
    try:
      accepted = bool(self.safety.safety_tx_hook(self.packet_factory(addr, local_bus, payload)))
      if expected_block_reason is None and not accepted:
        failure = "unexpected rejection"
      elif expected_block_reason is not None and accepted:
        failure = "expected block was accepted"
    except Exception as exc:
      failure = f"hook/factory error: {type(exc).__name__}: {exc}"
      raise
    finally:
      self._records.append(TxRecord(addr, bus, local_bus, payload, timestamp_ns, scenario, permissions,
                                   requested_lat_active, requested_long_active, accepted, expected_block_reason, failure))
    return self._records[-1]

  def summary(self, *, failure_limit=20):
    _integer(failure_limit, "failure_limit", 0, 2**31 - 1)
    records = self._records
    active = sum(r.permissions.active for r in records)
    requested_active = sum(r.requested_active for r in records)
    accepted_active = sum(r.accepted is True and r.permissions.active and r.requested_active for r in records)
    missing = []
    if not records:
      missing.append("no emitted TX")
    if not active:
      missing.append("no TX with active safety permission")
    if not requested_active:
      missing.append("no TX with explicitly active command request")
    if not accepted_active:
      missing.append("no accepted TX with active command request and safety permission")
    failure_count = sum(r.failure is not None for r in records)
    failures = []
    for i, r in enumerate(records):
      if r.failure and len(failures) < failure_limit:
        failures.append({"index": i, "addr": r.addr, "bus": r.bus, "data_hex": r.data.hex(), "timestamp_ns": r.timestamp_ns,
                         "scenario": r.scenario, "reason": r.failure,
                         "permissions": r.permissions.label, "requested_mode": r.requested_mode})
    permissions = [r.permissions.label for r in records]
    requested = [r.requested_mode for r in records]

    def transitions(states):
      return dict(Counter(f"{a} -> {b}" for a, b in zip(states, states[1:], strict=False) if a != b))

    return {
      "status": "failed" if failure_count else "uncovered" if missing else "pass",
      "tx_total": len(records), "tx_accepted": sum(r.accepted is True for r in records),
      "tx_rejected": sum(r.accepted is False for r in records),
      "expected_blocks": sum(r.accepted is False and r.expected_block_reason is not None for r in records),
      "unexpected_rejections": sum(r.accepted is False and r.expected_block_reason is None for r in records),
      "unexpected_acceptances": sum(r.accepted is True and r.expected_block_reason is not None for r in records),
      "hook_errors": sum(r.accepted is None for r in records),
      "active_tx": active, "inactive_tx": len(records) - active,
      "accepted_active_tx": accepted_active,
      "aol_only_tx": sum(r.permissions.aol_allowed and not r.permissions.controls_allowed for r in records),
      "requested_active_tx": requested_active,
      "requested_inactive_tx": sum(r.requested_lat_active is False and r.requested_long_active is False for r in records),
      "requested_unknown_tx": sum(r.requested_lat_active is None or r.requested_long_active is None for r in records),
      "requested_aol_only_tx": sum(r.requested_lat_active is True and r.permissions.aol_allowed and
                                   not r.permissions.controls_allowed for r in records),
      "permission_states": dict(Counter(permissions)), "requested_states": dict(Counter(requested)),
      "permission_transitions": transitions(permissions), "requested_transitions": transitions(requested),
      "uncovered_reasons": missing, "failure_count": failure_count, "failures": failures,
      "failures_truncated": failure_count - len(failures),
    }
