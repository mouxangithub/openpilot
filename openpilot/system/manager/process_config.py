import os
import platform

from opendbc.car.structs import car
from openpilot.cereal import custom
from openpilot.common.params import Params
from openpilot.common.hardware import PC, COMMA_HARDWARE, HARDWARE
from openpilot.system.manager.process import PythonProcess, NativeProcess, DaemonProcess
from openpilot.common.hardware.hw import Paths

from openpilot.common.dm import is_dm_disabled
from openpilot.sunnypilot.mapd.mapd_manager import MAPD_PATH

from openpilot.sunnypilot.models.helpers import get_active_model_runner
from openpilot.sunnypilot.sunnylink.utils import sunnylink_need_register, sunnylink_ready, use_sunnylink_uploader

WEBCAM = os.getenv("USE_WEBCAM") is not None
LITE = os.getenv("LITE") is not None
# Lets an external launcher own the carrot API/web stack, matching CarrotPilot's
# `enabled=not CARROT_WEB_EXTERNAL` gate on carrot_server.
CARROT_WEB_EXTERNAL = os.getenv("CARROT_WEB_EXTERNAL") == "1"

def driverview(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started or params.get_bool("IsDriverViewEnabled")

def dm_process(started: bool, params: Params, CP: car.CarParams) -> bool:
  return driverview(started, params, CP) and not is_dm_disabled(params)

def notcar(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and CP.notCar

def iscar(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and not CP.notCar

def logging(started: bool, params: Params, CP: car.CarParams) -> bool:
  run = (not CP.notCar) or not params.get_bool("DisableLogging")
  return started and run

def ublox_available() -> bool:
  return os.path.exists('/dev/ttyHS0') and not os.path.exists('/persist/comma/use-quectel-gps')

def ublox(started: bool, params: Params, CP: car.CarParams) -> bool:
  use_ublox = ublox_available()
  if use_ublox != params.get_bool("UbloxAvailable"):
    params.put_bool("UbloxAvailable", use_ublox, block=True)
  return started and use_ublox

def joystick(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and params.get_bool("JoystickDebugMode")

def not_joystick(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and not params.get_bool("JoystickDebugMode")

def long_maneuver(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and params.get_bool("LongitudinalManeuverMode")

def lat_maneuver(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and params.get_bool("LateralManeuverMode")

def not_long_maneuver(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and not params.get_bool("LongitudinalManeuverMode")

def qcomgps(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and not ublox_available()

def beep(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and params.get_bool("SpDevBeep")

def always_run(started: bool, params: Params, CP: car.CarParams) -> bool:
  return True

def builtin_display(started: bool, params: Params, CP: car.CarParams) -> bool:
  return HARDWARE.has_builtin_display()

def only_onroad(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started

def only_offroad(started: bool, params: Params, CP: car.CarParams) -> bool:
  return not started

def livestream(started: bool, params: Params, CP: car.CarParams) -> bool:
  return params.get_bool("IsLiveStreaming")

def onroad_preview(started: bool, params: Params, CP: car.CarParams) -> bool:
  return params.get_bool("IsOnroadPreview")

def use_copyparty(started, params, CP: car.CarParams) -> bool:
  return bool(params.get_bool("EnableCopyparty"))

def sunnylink_ready_shim(started, params, CP: car.CarParams) -> bool:
  """Shim for sunnylink_ready to match the process manager signature."""
  return sunnylink_ready(params)

def sunnylink_need_register_shim(started, params, CP: car.CarParams) -> bool:
  """Shim for sunnylink_need_register to match the process manager signature."""
  return sunnylink_need_register(params)

def use_sunnylink_uploader_shim(started, params, CP: car.CarParams) -> bool:
  """Shim for use_sunnylink_uploader to match the process manager signature."""
  return use_sunnylink_uploader(params)

def is_tinygrad_model(started, params, CP: car.CarParams) -> bool:
  """Check if the active model runner is tinygrad."""
  return bool(get_active_model_runner(params, not started) == custom.ModelManagerSP.Runner.tinygrad)

def is_stock_model(started, params, CP: car.CarParams) -> bool:
  """Check if the active model runner is stock."""
  return bool(get_active_model_runner(params, not started) == custom.ModelManagerSP.Runner.stock)

def imu_calibration_enabled(started: bool, params: Params, CP: car.CarParams) -> bool:
  return params.get_bool("ImuCalibrationEnabled")

def imu_calibration_disabled(started: bool, params: Params, CP: car.CarParams) -> bool:
  return not params.get_bool("ImuCalibrationEnabled")

def carrot_enabled(started: bool, params: Params, CP: car.CarParams) -> bool:
  # run even offroad: web panel (8088) / UDP / FTP must work while parked;
  # carrot_man gates its own behaviour with the IsOnroad param
  return params.get_bool("CarrotEnabled")

def mapd_ready(started: bool, params: Params, CP: car.CarParams) -> bool:
  return bool(os.path.exists(Paths.mapd_root()))

def uploader_ready(started: bool, params: Params, CP: car.CarParams) -> bool:
  if not params.get_bool("OnroadUploads"):
    return only_offroad(started, params, CP)

  return always_run(started, params, CP)

def or_(*fns):
  return lambda *args: any(fn(*args) for fn in fns)

def and_(*fns):
  return lambda *args: all(fn(*args) for fn in fns)

procs = [
  DaemonProcess("manage_athenad", "openpilot.system.athena.manage_athenad", "AthenadPid"),

  NativeProcess("loggerd", "openpilot/system/loggerd", ["./loggerd"], logging),
  NativeProcess("encoderd", "openpilot/system/loggerd", ["./encoderd"], only_onroad),
  NativeProcess("stream_encoderd", "openpilot/system/loggerd", ["./encoderd", "--stream"], or_(livestream, notcar)),
  PythonProcess("logmessaged", "openpilot.system.logmessaged", always_run),

  NativeProcess("camerad", "openpilot/system/camerad", ["./camerad"], or_(driverview, livestream, onroad_preview), enabled=not WEBCAM),
  PythonProcess("webcamerad", "openpilot.system.camerad.webcam.camerad", driverview, enabled=WEBCAM),
  PythonProcess("proclogd", "openpilot.system.proclogd", only_onroad, enabled=platform.system() != "Darwin"),
  PythonProcess("journald", "openpilot.system.journald", only_onroad, platform.system() != "Darwin"),
  PythonProcess("micd", "openpilot.system.micd", iscar, enabled=not LITE),
  PythonProcess("timed", "openpilot.system.timed", always_run, enabled=not PC),

  PythonProcess("modeld", "openpilot.selfdrive.modeld.modeld", and_(or_(only_onroad, onroad_preview), is_stock_model)),
  PythonProcess("dmonitoringmodeld", "openpilot.selfdrive.modeld.dmonitoringmodeld", dm_process, enabled=(WEBCAM or not PC) and not LITE),

  PythonProcess("sensord", "openpilot.system.sensord.sensord", only_onroad, enabled=not PC),
  PythonProcess("ui", "openpilot.selfdrive.ui.ui", and_(always_run, builtin_display), restart_if_crash=True),
  PythonProcess("soundd", "openpilot.selfdrive.ui.soundd", driverview, enabled=not LITE),
  PythonProcess("beepd", "openpilot.sunnypilot.selfdrive.ui.beepd", beep, enabled=LITE),
  PythonProcess("locationd", "openpilot.selfdrive.locationd.locationd", only_onroad),
  NativeProcess("_pandad", "openpilot/selfdrive/pandad", ["./pandad"], always_run, enabled=False),
  PythonProcess("calibrationd", "openpilot.selfdrive.locationd.calibrationd", and_(only_onroad, imu_calibration_disabled)),
  PythonProcess("imu_calibrationd", "openpilot.selfdrive.locationd.imu_calibrationd", and_(only_onroad, imu_calibration_enabled)),
  PythonProcess("torqued", "openpilot.selfdrive.locationd.torqued", only_onroad),
  PythonProcess("controlsd", "openpilot.selfdrive.controls.controlsd", and_(not_joystick, iscar)),
  PythonProcess("joystickd", "openpilot.tools.joystick.joystickd", or_(joystick, notcar)),
  PythonProcess("selfdrived", "openpilot.selfdrive.selfdrived.selfdrived", only_onroad),
  PythonProcess("card", "openpilot.selfdrive.car.card", only_onroad),
  PythonProcess("deleter", "openpilot.system.loggerd.deleter", always_run),
  PythonProcess("dmonitoringd", "openpilot.selfdrive.monitoring.dmonitoringd", dm_process, enabled=(WEBCAM or not PC) and not LITE),
  PythonProcess("qcomgpsd", "openpilot.system.qcomgpsd.qcomgpsd", qcomgps, enabled=COMMA_HARDWARE),
  PythonProcess("pandad", "openpilot.selfdrive.pandad.pandad", always_run),
  PythonProcess("paramsd", "openpilot.selfdrive.locationd.paramsd", only_onroad),
  PythonProcess("lagd", "openpilot.selfdrive.locationd.lagd", only_onroad),
  PythonProcess("ubloxd", "openpilot.system.ubloxd.ubloxd", ublox, enabled=COMMA_HARDWARE),
  PythonProcess("pigeond", "openpilot.system.ubloxd.pigeond", ublox, enabled=COMMA_HARDWARE),
  PythonProcess("plannerd", "openpilot.selfdrive.controls.plannerd", not_long_maneuver),
  PythonProcess("maneuversd", "openpilot.tools.longitudinal_maneuvers.maneuversd", long_maneuver),
  PythonProcess("lateral_maneuversd", "openpilot.tools.lateral_maneuvers.lateral_maneuversd", lat_maneuver),
  PythonProcess("radard", "openpilot.selfdrive.controls.radard", only_onroad),
  PythonProcess("hardwared", "openpilot.system.hardware.hardwared", always_run),
  PythonProcess("modem", "openpilot.common.hardware.comma.modem", always_run, enabled=COMMA_HARDWARE and not LITE),
  PythonProcess("tombstoned", "openpilot.system.tombstoned", always_run, enabled=not PC),
  PythonProcess("updated", "openpilot.system.updated.updated", only_offroad, enabled=not PC),
  PythonProcess("uploader", "openpilot.system.loggerd.uploader", uploader_ready),
  PythonProcess("statsd", "openpilot.sunnypilot.system.statsd", always_run),

  # debug procs
  NativeProcess("bridge", "openpilot/cereal/messaging", ["./bridge"], notcar),
  PythonProcess("webrtcd", "openpilot.system.webrtc.webrtcd", or_(livestream, notcar)),
  PythonProcess("joystick", "openpilot.tools.joystick.joystick_control", and_(joystick, iscar)),

  # sunnylink <3
  DaemonProcess("manage_sunnylinkd", "openpilot.sunnypilot.sunnylink.athena.manage_sunnylinkd", "SunnylinkdPid"),
  PythonProcess("sunnylink_registration_manager", "openpilot.sunnypilot.sunnylink.registration_manager", sunnylink_need_register_shim),
  PythonProcess("statsd_sp", "openpilot.sunnypilot.sunnylink.statsd", and_(always_run, sunnylink_ready_shim)),
]

# sunnypilot
procs += [
  # Models
  PythonProcess("models_manager", "openpilot.sunnypilot.models.manager", only_offroad),
  NativeProcess("modeld_tinygrad", "openpilot/sunnypilot/modeld_v2", ["./modeld"], and_(or_(only_onroad, onroad_preview), is_tinygrad_model)),

  # Backup
  PythonProcess("backup_manager", "openpilot.sunnypilot.sunnylink.backups.manager", and_(only_offroad, sunnylink_ready_shim)),

  # mapd
  NativeProcess("mapd", Paths.mapd_root(), ["bash", "-c", f"{MAPD_PATH} > /dev/null 2>&1"], mapd_ready),
  PythonProcess("mapd_manager", "openpilot.sunnypilot.mapd.mapd_manager", always_run),

  # Carrot
  # amapNaviSP and AmapMapData (Web API) removed: carrot_man now only produces
  # carrotManSP / navInstructionCarrotSP. OSM remains the map-data provider.
  #
  # always_run, NOT carrot_enabled: carrot_man is the UDP 7705 discovery
  # advertiser and the 7706 listener on this fork, and the phone app must find
  # the unit on 7705 before it can enable anything. CarrotEnabled defaults to
  # "0", so gating the process on it made every default device invisible to the
  # app ("7705 未激活"). CarrotPilot runs every carrot_* process with
  # always_run for the same reason; carrot_man still gates its own rich navi /
  # publish / web work on CarrotEnabled inside tick(), so only the listener and
  # the beacon stay live on a device with the feature switched off.
  #
  # restart_if_crash=True for both: they are the discovery + navi backbone.
  # Without it a crash leaves the unit unfindable until a manual reboot; the
  # manager must auto-relaunch them (mirrors CarrotPilot).
  #
  # carrot_navi (TCP 7714 v2) is always_run exactly like CarrotPilot: it owns
  # 7714 for the lifetime of the unit and only speaks when the app connects.
  # Whether the data it produces reaches the driving stack is a *behaviour*
  # switch (`CarrotNaviV2Enabled`, read by card.py), not a process gate - a
  # gated process cannot come up on demand, because the manager only re-evaluates
  # its gates on its own cycle, so the link would stay dead until a manager pass.
  PythonProcess("carrot_man", "openpilot.sunnypilot.carrot.carrot_man", always_run, restart_if_crash=True),
  PythonProcess("carrot_navi", "openpilot.sunnypilot.carrot.carrot_navi", always_run, restart_if_crash=True),
  # CarrotPilot-compatible API server on port 7000: the parameter REST API plus, as they
  # are ported, the /ws raw and camera streams. The companion app (navipilot / CP 搭子)
  # treats 7000 as its main channel, so without it the app reports "设备未连接" and its
  # conditional-experiment mode cannot switch. always_run like CarrotPilot's; the gate only
  # exists so an external launcher can take the stack over.
  # restart_if_crash: the app's main channel must come back on its own. Without it the
  # manager leaves the port dead until the next ignition cycle, which the app reports as
  # "设备未连接" with nothing on the device to explain why.
  PythonProcess("carrot_server", "openpilot.sunnypilot.carrot.carrot_server", always_run,
                enabled=not CARROT_WEB_EXTERNAL, restart_if_crash=True),

  # Xiaoge ONNX BSD/Lane detection
  # Reads VisionIPC camera buffers, runs ONNX inference, publishes to customReservedRawData0.
  # card.py merges results into carState (blindspot) and carStateSP (lane lines).
  # restart_if_crash=True: xiaoge_data can crash on startup if cameras are temporarily
  # unavailable (e.g. camera stream not yet stable when entering the car). Without this
  # flag the manager waits for the next ensure_running cycle before restarting, causing a
  # spurious "进程未运行" alert to appear briefly.
  PythonProcess("xiaoge_data", "openpilot.sunnypilot.carrot.xiaoge_data", carrot_enabled, restart_if_crash=True),

  # Bluetooth HID remote daemon
  # Reads evdev input events from paired Bluetooth HID remotes (e.g. Yiser J6).
  # Publishes cruise/lane commands to /dev/shm/carrot-bluetooth/{cruise,lane}.json.
  # CommandReader in cruise.py / desire_helper.py consumes these commands.
  #
  # always_run + enabled=COMMA_HARDWARE mirrors CarrotPilot's
  # `always_run, enabled=TICI`: Bluetooth HID remotes only exist on comma
  # hardware (AGNOS exposes the evdev nodes), and the old gate on CarrotEnabled
  # meant a unit with the master switch off could not pair its remote. This fork
  # has no `TICI` symbol - `COMMA_HARDWARE` (AGNOS present) is its equivalent.
  PythonProcess("carrot_bluetooth", "openpilot.sunnypilot.carrot.bluetooth.daemon", always_run, enabled=COMMA_HARDWARE, restart_if_crash=True),

  # locationd
  NativeProcess("locationd_llk", "openpilot/sunnypilot/selfdrive/locationd", ["./locationd"], only_onroad),
]

if os.path.exists("../../sunnypilot/sunnylink/uploader.py"):
  procs += [PythonProcess("sunnylink_uploader", "openpilot.sunnypilot.sunnylink.uploader", use_sunnylink_uploader_shim)]

if os.path.exists("../../third_party/copyparty/copyparty-sfx.py"):
  sunnypilot_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
  copyparty_args = [f"-v{Paths.crash_log_root()}:/swaglogs:r"]
  copyparty_args += [f"-v{Paths.log_root()}:/routes:r"]
  copyparty_args += [f"-v{Paths.model_root()}:/models:rw"]
  copyparty_args += [f"-v{sunnypilot_root}:/sunnypilot:rw"]
  copyparty_args += ["-p8080"]
  copyparty_args += ["-z"]
  copyparty_args += ["-q"]
  procs += [NativeProcess("copyparty-sfx", "openpilot/third_party/copyparty", ["./copyparty-sfx.py", *copyparty_args], and_(only_offroad, use_copyparty))]

managed_processes = {p.name: p for p in procs}
