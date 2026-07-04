from types import SimpleNamespace
from cereal import car
from openpilot.selfdrive.controls.lib.longcontrol import LongCtrlState
from dragonpilot.selfdrive.controls.lib.accel_logger import _should_log, AccelLogger


def _clean(**over):
    args = dict(long_off=True, gas=True, brake=False, blinker=False,
                in_drive=True, moving=True, a_ego=0.8, lead_ttc=9.9, lat_accel=0.2)
    args.update(over)
    return _should_log(**args)

def test_clean_sample_logs():
    assert _clean() is True

def test_each_condition_blocks():
    assert _clean(long_off=False) is False   # op long active
    assert _clean(gas=False) is False
    assert _clean(a_ego=0.0) is False         # not accelerating
    assert _clean(brake=True) is False
    assert _clean(blinker=True) is False
    assert _clean(in_drive=False) is False
    assert _clean(moving=False) is False
    assert _clean(lead_ttc=1.0) is False      # lead too close
    assert _clean(lat_accel=5.0) is False      # in a curve


DRIVE = car.CarState.GearShifter.drive
CP = SimpleNamespace(steerRatio=15.0, wheelbase=2.7, openpilotLongitudinalControl=True)

def _sm(**over):
    cs = dict(vEgo=10.0, aEgo=0.8, gasPressed=True, brakePressed=False,
              steeringPressed=False, leftBlinker=False, rightBlinker=False,
              standstill=False, gearShifter=DRIVE, steeringAngleDeg=0.0)
    cs.update(over)
    return {
        'carState': SimpleNamespace(**cs),
        'controlsState': SimpleNamespace(longControlState=LongCtrlState.off),
        'radarState': SimpleNamespace(leadOne=SimpleNamespace(status=False, dRel=0.0)),
    }

def test_clean_sample_buffers(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    log.update(_sm(vEgo=10.0, aEgo=0.8))
    assert log._buf == [(10.0, 0.8)]

def test_gate_blocks_dirty_sample(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    sm = _sm()
    sm['controlsState'] = SimpleNamespace(longControlState=LongCtrlState.pid)  # op long active
    log.update(sm)
    assert log._buf == []

def test_no_op_long_disables_logging(tmp_path):
    # stock-long car: accel-eq is inert, so the logger must not run at all
    stock_cp = SimpleNamespace(steerRatio=15.0, wheelbase=2.7, openpilotLongitudinalControl=False)
    log = AccelLogger(stock_cp, path=str(tmp_path / "h.csv"))
    log.update(_sm(vEgo=10.0, aEgo=0.8))  # would be a clean sample under OP long
    assert log._buf == []

def test_in_curve_sample_rejected_end_to_end(tmp_path):
    # large steering -> lateral accel exceeds LAT_ACCEL_MAX -> not buffered
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    log.update(_sm(vEgo=10.0, aEgo=0.8, steeringAngleDeg=45.0))
    assert log._buf == []

def test_flush_appends_and_clears(tmp_path):
    p = tmp_path / "h.csv"
    log = AccelLogger(CP, path=str(p))
    log.update(_sm(vEgo=10.0, aEgo=0.8))
    log.update(_sm(vEgo=12.0, aEgo=0.5))
    log._flush()
    assert log._buf == []
    assert p.read_text().splitlines() == ["10.000,0.800", "12.000,0.500"]
    # second flush appends (does not truncate)
    log.update(_sm(vEgo=5.0, aEgo=1.0))
    log._flush()
    assert p.read_text().splitlines()[-1] == "5.000,1.000"

def test_auto_flush_on_cadence(tmp_path):
    p = tmp_path / "h.csv"
    log = AccelLogger(CP, path=str(p))
    log._flush_every = 1  # flush every frame
    log.update(_sm(vEgo=10.0, aEgo=0.8))
    assert p.read_text().splitlines() == ["10.000,0.800"]
    assert log._buf == []

def test_flush_failure_drops_rows_no_raise(tmp_path):
    # parent dir does not exist -> open() fails -> rows dropped, no raise, RAM bounded
    log = AccelLogger(CP, path=str(tmp_path / "missing" / "h.csv"))
    log.update(_sm())
    log._flush()
    assert log._buf == []

def test_update_never_raises(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    log.update({})  # missing keys -> swallowed
    assert log._buf == []

def test_logger_is_pure_observation(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    assert log.update(_sm()) is None
