"""PC dev machine tools (Ubuntu 24.04 / macOS / WSL). Only active when host_env.is_pc_dev()."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ai.system.host_env import get_host_environment, is_pc_dev
from ai.system.paths import openpilot_root as _OPENPILOT_ROOT
from ai.system.pc_tool_sessions import (
  capture_route_context,
  create_session,
  get_session,
  list_sessions,
)
from ai.tools.op_run import resolve_route_ref, validate_route_ref


def _require_pc() -> dict[str, Any] | None:
  if not is_pc_dev():
    return {
      "ok": False,
      "error": "This tool is only available on PC dev hosts (not comma TICI/AGNOS).",
      "host": get_host_environment(),
    }
  return None


def _launch_detached(
  cmd: list[str],
  *,
  cwd: Path | None = None,
  tool: str,
  launch_params: dict[str, Any],
  route: str | None = None,
  capture_data: bool = True,
  extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
  env = os.environ.copy()
  env.setdefault("PYTHONPATH", str(_OPENPILOT_ROOT))
  if str(_OPENPILOT_ROOT) not in env["PYTHONPATH"].split(os.pathsep):
    env["PYTHONPATH"] = str(_OPENPILOT_ROOT) + os.pathsep + env["PYTHONPATH"]
  if extra_env:
    env.update(extra_env)
  try:
    kwargs: dict[str, Any] = {
      "cwd": str(cwd or _OPENPILOT_ROOT),
      "env": env,
      "stdout": subprocess.DEVNULL,
      "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
      kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    else:
      kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    session = create_session(
      tool=tool,
      launch_params=launch_params,
      command=cmd,
      pid=proc.pid,
      route=route,
      capture_data=capture_data,
    )
    return {
      "ok": True,
      "pid": proc.pid,
      "command": cmd,
      "session_id": session["session_id"],
      "launch_params": launch_params,
      "data_snapshot": session.get("data_snapshot"),
      "hint": "Use pc_get_tool_session(session_id) to re-read launch params and route data.",
    }
  except Exception as e:
    return {"ok": False, "error": str(e), "command": cmd}


def pc_capture_route_context(
  route: str,
  *,
  include_signal_summary: bool = True,
  include_topics: bool = True,
) -> dict[str, Any]:
  """Programmatic snapshot of what PlotJuggler/Replay/Cabana would load (no GUI)."""
  err = _require_pc()
  if err:
    return err
  verr = validate_route_ref(route)
  if verr:
    return {"ok": False, "error": verr}
  return capture_route_context(
    route,
    include_signal_summary=include_signal_summary,
    include_topics=include_topics,
  )


def pc_list_tool_sessions(*, limit: int = 20) -> dict[str, Any]:
  err = _require_pc()
  if err:
    return err
  return list_sessions(limit=limit)


def pc_get_tool_session(
  session_id: str,
  *,
  refresh_process: bool = True,
  refresh_data: bool = False,
) -> dict[str, Any]:
  err = _require_pc()
  if err:
    return err
  if not session_id:
    return {"ok": False, "error": "session_id required"}
  return get_session(session_id, refresh_process=refresh_process, refresh_data=refresh_data)


def pc_launch_plotjuggler(
  route: str | None = None,
  *,
  layout: str | None = None,
  parse_can: bool = False,
  demo: bool = False,
  capture_data: bool = True,
) -> dict[str, Any]:
  err = _require_pc()
  if err:
    return err
  script = _OPENPILOT_ROOT / "tools" / "plotjuggler" / "juggle.py"
  if not script.is_file():
    return {"ok": False, "error": f"Missing {script}"}

  launch_params: dict[str, Any] = {
    "route": route,
    "layout": layout,
    "parse_can": parse_can,
    "demo": demo,
    "capture_data": capture_data,
  }
  resolved_route: str | None = None

  cmd = [sys.executable, str(script)]
  if demo:
    cmd.append("--demo")
    resolved_route = "5beb9b58bd12b691/0000010a--a51155e496"
  elif route:
    resolved_route = resolve_route_ref(route)
    cmd.append(resolved_route)
  else:
    return {"ok": False, "error": "route or demo=true required"}
  if layout:
    cmd.extend(["--layout", layout])
  if parse_can:
    cmd.append("--can")

  res = _launch_detached(
    cmd,
    cwd=script.parent,
    tool="pc_launch_plotjuggler",
    launch_params=launch_params,
    route=resolved_route,
    capture_data=capture_data,
  )
  return {
    **res,
    "tool": "tools/plotjuggler/juggle.py",
    "hint": "data_snapshot has car_params, topics, signal_summary. GUI opens separately.",
  }


def pc_launch_replay(
  route: str | None = None,
  *,
  demo: bool = False,
  data_dir: str | None = None,
  speed: float | None = None,
  capture_data: bool = True,
) -> dict[str, Any]:
  err = _require_pc()
  if err:
    return err
  binary = _OPENPILOT_ROOT / "tools" / "replay" / "replay"
  if not binary.is_file():
    return {
      "ok": False,
      "error": f"replay binary not built. Run: scons -u (expected {binary})",
      "build_hint": "tools/replay/README.md",
    }

  launch_params: dict[str, Any] = {
    "route": route,
    "demo": demo,
    "data_dir": data_dir,
    "speed": speed,
    "capture_data": capture_data,
  }
  resolved_route: str | None = None

  cmd = [str(binary)]
  if demo:
    cmd.append("--demo")
  elif route:
    resolved_route = resolve_route_ref(route)
    cmd.append(resolved_route)
  else:
    return {"ok": False, "error": "route or demo=true required"}
  if data_dir:
    cmd.extend(["--data_dir", data_dir])
  if speed is not None:
    cmd.extend(["-x", str(speed)])

  res = _launch_detached(
    cmd,
    cwd=binary.parent,
    tool="pc_launch_replay",
    launch_params=launch_params,
    route=resolved_route,
    capture_data=capture_data,
  )
  return {**res, "tool": "tools/replay/replay"}


def pc_launch_cabana(
  route: str | None = None,
  *,
  demo: bool = False,
  data_dir: str | None = None,
  capture_data: bool = True,
) -> dict[str, Any]:
  err = _require_pc()
  if err:
    return err
  binary = _OPENPILOT_ROOT / "tools" / "cabana" / "cabana"
  if not binary.is_file():
    return {
      "ok": False,
      "error": f"cabana binary not built. Run: scons -u (expected {binary})",
      "build_hint": "tools/cabana/README.md",
    }

  launch_params: dict[str, Any] = {
    "route": route,
    "demo": demo,
    "data_dir": data_dir,
    "capture_data": capture_data,
  }
  resolved_route: str | None = None

  cmd = [str(binary)]
  if demo:
    cmd.append("--demo")
  elif route:
    resolved_route = resolve_route_ref(route)
    cmd.append(resolved_route)
  if data_dir:
    cmd.extend(["--data_dir", data_dir])

  res = _launch_detached(
    cmd,
    cwd=binary.parent,
    tool="pc_launch_cabana",
    launch_params=launch_params,
    route=resolved_route,
    capture_data=capture_data and bool(resolved_route),
  )
  return {**res, "tool": "tools/cabana/cabana"}


def pc_launch_sim_bridge(*, joystick: bool = False, capture_data: bool = False) -> dict[str, Any]:
  err = _require_pc()
  if err:
    return err
  script = _OPENPILOT_ROOT / "tools" / "sim" / "run_bridge.py"
  if not script.is_file():
    return {"ok": False, "error": f"Missing {script}"}
  cmd = [sys.executable, str(script)]
  if joystick:
    cmd.append("--joystick")
  launch_params = {"joystick": joystick, "capture_data": capture_data}
  res = _launch_detached(
    cmd,
    tool="pc_launch_sim_bridge",
    launch_params=launch_params,
    route=None,
    capture_data=False,
  )
  return {
    **res,
    "tool": "tools/sim/run_bridge.py",
    "hint": "MetaDrive sim only — do not use with a real vehicle connected.",
  }


def pc_auth_login_hint() -> dict[str, Any]:
  err = _require_pc()
  if err:
    return err
  script = _OPENPILOT_ROOT / "tools" / "lib" / "auth.py"
  return {
    "ok": True,
    "script": str(script),
    "command": f"{sys.executable} {script}",
    "hint": "Run in a terminal on this PC; browser OAuth completes login. Then comma_auth_status should show authenticated.",
  }


def pc_launch_jotpluggler(
  route: str | None = None,
  *,
  layout: str | None = None,
  demo: bool = False,
  data_dir: str | None = None,
  capture_data: bool = True,
) -> dict[str, Any]:
  """Launch tools/jotpluggler/jotpluggler (PlotJuggler successor) for a route."""
  err = _require_pc()
  if err:
    return err
  binary = _OPENPILOT_ROOT / "tools" / "jotpluggler" / "jotpluggler"
  if not binary.is_file():
    return {
      "ok": False,
      "error": f"jotpluggler binary not built. Run: scons -u (expected {binary})",
      "build_hint": "tools/jotpluggler/",
    }

  launch_params: dict[str, Any] = {
    "route": route,
    "layout": layout,
    "demo": demo,
    "data_dir": data_dir,
    "capture_data": capture_data,
  }
  resolved_route: str | None = None

  cmd = [str(binary), "--show"]
  if demo:
    cmd.append("--demo")
    resolved_route = "5beb9b58bd12b691/0000010a--a51155e496"
  elif route:
    resolved_route = resolve_route_ref(route)
    cmd.append(resolved_route)
  else:
    return {"ok": False, "error": "route or demo=true required"}
  if layout:
    cmd.extend(["--layout", layout])
  if data_dir:
    cmd.extend(["--data-dir", data_dir])

  res = _launch_detached(
    cmd,
    cwd=binary.parent,
    tool="pc_launch_jotpluggler",
    launch_params=launch_params,
    route=resolved_route,
    capture_data=capture_data,
  )
  return {
    **res,
    "tool": "tools/jotpluggler/jotpluggler",
    "hint": "JotPluggler replaces PlotJuggler; data_snapshot has route context for AI.",
  }


def pc_launch_replay_stream(
  route: str | None = None,
  *,
  demo: bool = False,
  data_dir: str | None = None,
  speed: float | None = None,
  capture_data: bool = True,
) -> dict[str, Any]:
  """PC: replay route via ZMQ (background publisher for stream viz tools)."""
  err = _require_pc()
  if err:
    return err
  binary = _OPENPILOT_ROOT / "tools" / "replay" / "replay"
  if not binary.is_file():
    return {
      "ok": False,
      "error": f"replay binary not built. Run: scons -u (expected {binary})",
    }

  launch_params: dict[str, Any] = {
    "route": route,
    "demo": demo,
    "data_dir": data_dir,
    "speed": speed,
    "stream": True,
    "capture_data": capture_data,
  }
  resolved_route: str | None = None

  cmd = [str(binary)]
  if demo:
    cmd.append("--demo")
  elif route:
    resolved_route = resolve_route_ref(route)
    cmd.append(resolved_route)
  else:
    return {"ok": False, "error": "route or demo=true required"}
  if data_dir:
    cmd.extend(["--data_dir", data_dir])
  if speed is not None:
    cmd.extend(["-x", str(speed)])

  res = _launch_detached(
    cmd,
    cwd=binary.parent,
    tool="pc_launch_replay_stream",
    launch_params=launch_params,
    route=resolved_route,
    capture_data=capture_data,
    extra_env={"ZMQ": "1"},
  )
  return {
    **res,
    "tool": "tools/replay/replay",
    "zmq": True,
    "hint": "Pair with pc_launch_plotjuggler_stream or pc_launch_replay_viz_stream.",
  }


def pc_launch_plotjuggler_stream(*, layout: str | None = None) -> dict[str, Any]:
  """PC: PlotJuggler cereal subscriber (ZMQ). Start replay stream first."""
  err = _require_pc()
  if err:
    return err
  script = _OPENPILOT_ROOT / "tools" / "plotjuggler" / "juggle.py"
  if not script.is_file():
    return {"ok": False, "error": f"Missing {script}"}

  launch_params: dict[str, Any] = {"layout": layout, "stream": True}
  cmd = [sys.executable, str(script), "--stream"]
  if layout:
    cmd.extend(["--layout", layout])

  res = _launch_detached(
    cmd,
    cwd=script.parent,
    tool="pc_launch_plotjuggler_stream",
    launch_params=launch_params,
    route=None,
    capture_data=False,
    extra_env={"ZMQ": "1"},
  )
  return {
    **res,
    "tool": "tools/plotjuggler/juggle.py",
    "zmq": True,
    "hint": "In PlotJuggler: Streaming → Cereal Subscriber → Start. Requires ZMQ replay or device bridge.",
  }


def pc_launch_jotpluggler_stream(
  *,
  address: str | None = None,
  buffer_seconds: float | None = None,
) -> dict[str, Any]:
  """PC: JotPluggler live stream mode (ZMQ). Mutually exclusive with route file mode."""
  err = _require_pc()
  if err:
    return err
  binary = _OPENPILOT_ROOT / "tools" / "jotpluggler" / "jotpluggler"
  if not binary.is_file():
    return {
      "ok": False,
      "error": f"jotpluggler binary not built. Run: scons -u (expected {binary})",
    }

  launch_params: dict[str, Any] = {
    "stream": True,
    "address": address,
    "buffer_seconds": buffer_seconds,
  }
  cmd = [str(binary), "--stream", "--show"]
  if address:
    cmd.extend(["--address", address])
  if buffer_seconds is not None:
    cmd.extend(["--buffer-seconds", str(buffer_seconds)])

  res = _launch_detached(
    cmd,
    cwd=binary.parent,
    tool="pc_launch_jotpluggler_stream",
    launch_params=launch_params,
    route=None,
    capture_data=False,
    extra_env={"ZMQ": "1"},
  )
  return {
    **res,
    "tool": "tools/jotpluggler/jotpluggler",
    "zmq": True,
    "hint": "Use after pc_launch_replay_stream or comma device messaging bridge.",
  }


def pc_launch_replay_viz_stream(
  route: str | None = None,
  *,
  demo: bool = False,
  viz: str = "plotjuggler",
  layout: str | None = None,
  speed: float | None = None,
  data_dir: str | None = None,
  capture_data: bool = True,
) -> dict[str, Any]:
  """PC: start ZMQ replay + stream viz (plotjuggler or jotpluggler) together."""
  err = _require_pc()
  if err:
    return err
  viz_norm = (viz or "plotjuggler").strip().lower()
  if viz_norm not in ("plotjuggler", "jotpluggler"):
    return {"ok": False, "error": "viz must be plotjuggler or jotpluggler"}

  replay_res = pc_launch_replay_stream(
    route,
    demo=demo,
    data_dir=data_dir,
    speed=speed,
    capture_data=capture_data,
  )
  if not replay_res.get("ok"):
    return replay_res

  if viz_norm == "plotjuggler":
    viz_res = pc_launch_plotjuggler_stream(layout=layout)
  else:
    viz_res = pc_launch_jotpluggler_stream()

  if not viz_res.get("ok"):
    return {
      "ok": False,
      "error": "Replay started but viz failed to launch",
      "replay": replay_res,
      "viz": viz_res,
    }

  return {
    "ok": True,
    "viz": viz_norm,
    "replay_session_id": replay_res.get("session_id"),
    "viz_session_id": viz_res.get("session_id"),
    "replay_pid": replay_res.get("pid"),
    "viz_pid": viz_res.get("pid"),
    "data_snapshot": replay_res.get("data_snapshot"),
    "launch_params": {
      "route": route,
      "demo": demo,
      "layout": layout,
      "speed": speed,
      "data_dir": data_dir,
      "viz": viz_norm,
    },
    "hint": (
      "Replay publishes ZMQ cereal; open viz GUI and start stream/subscriber. "
      "Use pc_get_tool_session on session ids for params and route data."
    ),
  }


def pc_launch_replay_ui(*, address: str = "127.0.0.1") -> dict[str, Any]:
  """PC: tools/replay/ui.py ZMQ debug UI (pair with replay stream)."""
  err = _require_pc()
  if err:
    return err
  script = _OPENPILOT_ROOT / "tools" / "replay" / "ui.py"
  if not script.is_file():
    return {"ok": False, "error": f"Missing {script}"}

  launch_params = {"address": address}
  extra_env = {"ZMQ": "1"} if address not in ("127.0.0.1", "localhost") else {"ZMQ": "1"}
  cmd = [sys.executable, str(script), address]
  res = _launch_detached(
    cmd,
    tool="pc_launch_replay_ui",
    launch_params=launch_params,
    route=None,
    capture_data=False,
    extra_env=extra_env,
  )
  return {
    **res,
    "tool": "tools/replay/ui.py",
    "hint": "Start pc_launch_replay_stream first on same ZMQ address.",
  }


def pc_launch_camerastream(
  device_addr: str,
  *,
  cams: str = "0,1,2",
  nvidia: bool = False,
) -> dict[str, Any]:
  """PC: decode remote camera streams (tools/camerastream/compressed_vipc.py)."""
  err = _require_pc()
  if err:
    return err
  addr = (device_addr or "").strip()
  if not addr:
    return {"ok": False, "error": "device_addr required (comma device IP)"}

  script = _OPENPILOT_ROOT / "tools" / "camerastream" / "compressed_vipc.py"
  if not script.is_file():
    return {"ok": False, "error": f"Missing {script}"}

  launch_params = {"device_addr": addr, "cams": cams, "nvidia": nvidia}
  cmd = [sys.executable, str(script), addr, "--cams", cams]
  if nvidia:
    cmd.append("--nvidia")

  res = _launch_detached(
    cmd,
    tool="pc_launch_camerastream",
    launch_params=launch_params,
    route=None,
    capture_data=False,
  )
  return {
    **res,
    "tool": "tools/camerastream/compressed_vipc.py",
    "hint": "On device run messaging bridge + camerad + encoderd (see tools/camerastream/README.md).",
  }
