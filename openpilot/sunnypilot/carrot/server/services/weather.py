"""Run the Open-Meteo poller beside the settings server.

`openpilot.sunnypilot.carrot.weather` decides what the weather is and when to
ask again; this module is the part that owns a clock and a parameter store.

It lives in the settings server rather than in plannerd for one reason: a
weather query is a 10 s socket stall, and plannerd's loop has a 20 ms budget.
This process is already the fork's network-facing daemon - it holds the shared
`ClientSession` for the asset mirror, the popular-value upload and the tunnel -
so one more outbound request changes nothing about its shape.

The loop is a plain `while True` with a 30 s sleep. `WeatherPoller` holds the
real schedule (15 min, or a minute after a failure, or immediately after a
25 km drive), so waking up often is free: a wake-up that is not due does no I/O
at all.

Off by default, in two places at once:

  * `WeatherOffsetsEnabled` gates the whole feature, and the offsets it
    applies all default to zero;
  * `WeatherAutoDetect` gates this loop specifically, so a user who would
    rather type the weather in by hand does not get a network request either.

With either one off, nothing here touches the network.
"""
import asyncio
import logging
import time

from openpilot.sunnypilot.carrot.weather import WeatherPoller, position_from_raw
from openpilot.sunnypilot.common.param_read import read_bool

from .params import HAS_PARAMS, Params

logger = logging.getLogger("openpilot.carrot.server.weather")

# Where mapd publishes the fused position (see mapd/live_map_data/osm_map_data.py).
MEMORY_PARAMS_PATH = "/dev/shm/params"
TICK_INTERVAL_S = 30.0
WEATHER_KEY = "WeatherState"


def read_position(params) -> tuple[float, float] | None:
  """The last position mapd wrote, or None while there is not one yet."""
  try:
    return position_from_raw(params.get("LastGPSPosition"))
  except Exception:
    return None


def _default_on(params, key: str) -> bool:
  """A switch whose registered default is 1, read so that default applies.

  `Params.get_bool` is `get(key) == "1"`, so a key that was never written reads
  False - it does not consult the registered default at all. `param_read.read_bool`
  is built on that getter, which is right for feature switches (the safe default
  is off) and wrong here: auto-detect ships on, and reading "never written" as
  "off" means the feature is off until somebody opens the settings page and
  toggles it twice.
  """
  try:
    return params.get(key, return_default=True) in (True, "1", 1)
  except Exception:
    return True


def auto_detect_enabled(params) -> bool:
  """Whether this loop is allowed to make a request at all."""
  return read_bool(params, "WeatherOffsetsEnabled", False) and _default_on(params, "WeatherAutoDetect")


def _open_memory_params():
  """A handle on the tmpfs store mapd writes the position to, or None.

  Absent on a PC and on any device whose mapd has not started yet, which is
  the same case as "no fix": the loop simply does nothing.
  """
  try:
    memory = Params(MEMORY_PARAMS_PATH)
  except Exception:
    return None
  try:
    if not memory.get_param_path():
      return None
  except Exception:
    return None
  return memory


async def weather_loop(app) -> None:
  """Keep `WeatherState` in step with the weather. Never raises out of the loop."""
  if not HAS_PARAMS:
    return

  params = Params()
  poller = WeatherPoller()
  # Diagnostics for /api/health: what was last written, and where the answer
  # came from. The position matters more than the time - "rain" is only
  # interesting next to the coordinates it was reported for.
  app["weather"] = {"state": poller.state, "code": None, "latitude": None, "longitude": None}

  while True:
    try:
      await _tick_once(app, params, poller)
    except asyncio.CancelledError:
      raise
    except Exception:
      # A background task that dies takes the feature down silently, and the
      # only symptom would be weather that never changes. Log and keep going.
      logger.exception("carrot_server: weather tick failed")
    await asyncio.sleep(TICK_INTERVAL_S)


async def _tick_once(app, params, poller: WeatherPoller) -> None:
  if not auto_detect_enabled(params):
    return

  memory = app.get("weather_memory")
  if memory is None:
    memory = app["weather_memory"] = _open_memory_params()
  position = read_position(memory if memory is not None else params)
  if position is None:
    return

  # The poller blocks for as long as the request takes, which is exactly why
  # the event loop must not run it. Monotonic, because the schedule only ever
  # compares two readings and a wall clock can jump underneath it.
  reading = await asyncio.to_thread(poller.tick, time.monotonic(), position[0], position[1])
  if reading is None:
    return

  try:
    params.put(WEATHER_KEY, reading.state, block=True)
  except Exception:
    # Most likely an unregistered key on a build older than this feature.
    # Nothing else in this loop can recover from that, so report it once per
    # tick and let the next one try again.
    logger.warning("carrot_server: cannot write %s (is params_c.so up to date?)", WEATHER_KEY, exc_info=True)
    return

  app["weather"] = {"state": reading.state, "code": reading.code,
                    "latitude": reading.latitude, "longitude": reading.longitude}
  logger.info("carrot_server: weather is %s (WMO %d) at %.4f,%.4f",
              reading.state, reading.code, reading.latitude, reading.longitude)
