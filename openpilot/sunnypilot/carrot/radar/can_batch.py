"""Join independent CAN/carState streams without changing radar input batches."""
from collections import deque
from dataclasses import dataclass
from typing import Any


MAX_INPUT_AGE_NS = 100_000_000
MAX_CAN_PACKETS = 512
MAX_STATE_PACKETS = 32

# The join watchdog's first seconds of a drive see ignition CAN floods, card's
# first radarInput batches and scheduler jitter from every process warming up;
# those transient stateOverflow / staleEgoState / processingTimeout trips are
# normal and self-heal. Publishing them as errors.canError made selfdrived
# raise a SOFT_DISABLE "CAN bus error" at every drive start (2026-10-31 route
# 58 seg 0: 407 alert frames within ~20 s of drive start). radarcan holds the
# fault publication for this long after process start; trips inside the window
# still rebuild the interface but feed radard healthy-empty liveTracks frames.
MAX_STARTUP_GRACE_NS = 20_000_000_000


def in_startup_grace(start_ns: int, now_ns: int, grace_ns: int) -> bool:
  """True while now is inside the startup window; grace_ns <= 0 disables."""
  return grace_ns > 0 and 0 <= now_ns - start_ns < grace_ns


@dataclass(frozen=True)
class RadarEgoSample:
  first_can_ns: int
  last_can_ns: int
  packet_count: int
  receive_ns: int
  v_ego: float
  a_ego: float

  @classmethod
  def from_car_state(cls, cs: Any) -> 'RadarEgoSample':
    batch = cs.radarInput
    return cls(int(batch.firstCanMonoTime), int(batch.lastCanMonoTime),
               int(batch.canPacketCount), int(batch.receiveMonoTime),
               float(cs.vEgo), float(cs.aEgo))


class RadarCanBatches:
  def __init__(self):
    self.can = deque(maxlen=MAX_CAN_PACKETS)
    self.states: deque[RadarEgoSample] = deque()
    self.overflowed = False

  def add_can(self, packets):
    self.can.extend(packets)

  def add_state(self, state: RadarEgoSample):
    if len(self.states) >= MAX_STATE_PACKETS:
      self.states.clear()
      self.overflowed = True
    self.states.append(state)

  def take(self, now_ns: int):
    """Return (ego state, CAN batch, error), or None until both inputs arrive.

    Socket order is independent, but each individual stream stays ordered.
    A missing packet or stale input invalidates the result instead of pairing
    radar measurements with an unrelated ego state or silently catching up.
    """
    if not self.states:
      return None
    state = self.states[0]
    if self.overflowed:
      self.overflowed = False
      self.states.popleft()
      return state, [], 'stateOverflow'
    if state.receive_ns <= 0:
      self.states.popleft()
      return state, [], 'missingBatchMetadata'
    if now_ns - state.receive_ns > MAX_INPUT_AGE_NS:
      self.states.popleft()
      return state, [], 'staleEgoState'
    if state.packet_count == 0:
      self.states.popleft()
      error = 'invalidEmptyBatch' if state.first_can_ns or state.last_can_ns else None
      return state, [], error
    if (state.packet_count > MAX_CAN_PACKETS or state.first_can_ns <= 0
        or state.last_can_ns < state.first_can_ns):
      self.states.popleft()
      return state, [], 'invalidBatchMetadata'
    while self.can and self.can[0][0] < state.first_can_ns:
      self.can.popleft()
    if not self.can or self.can[-1][0] < state.last_can_ns:
      return None
    packets = []
    while self.can and self.can[0][0] <= state.last_can_ns:
      packets.append(self.can.popleft())
    self.states.popleft()
    if (len(packets) != state.packet_count or not packets
        or packets[0][0] != state.first_can_ns or packets[-1][0] != state.last_can_ns):
      return state, [], 'missingCanPacket'
    return state, packets, None
