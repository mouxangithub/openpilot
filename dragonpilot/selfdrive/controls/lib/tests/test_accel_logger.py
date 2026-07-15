from types import SimpleNamespace
import pytest
from cereal import car
from openpilot.selfdrive.controls.lib.longcontrol import LongCtrlState
from dragonpilot.selfdrive.controls.lib.accel_logger import (
    _is_clean, AccelLogger, LOG_HEADER, WARM_N,
)

def _clean(**over):
    args = dict(long_off=True, gas=True, brake=False, blinker=False,
                in_drive=True, moving=True, lead_ttc=9.9, lat_accel=0.2, grade_ok=True)
    args.update(over)
    return _is_clean(**args)

def test_is_clean_true_for_clean():
    assert _clean() is True

def test_each_condition_blocks():
    assert _clean(long_off=False) is False
    assert _clean(gas=False) is False
    assert _clean(brake=True) is False
    assert _clean(blinker=True) is False
    assert _clean(in_drive=False) is False
    assert _clean(moving=False) is False
    assert _clean(lead_ttc=0.5) is False      # < TTC_MIN (1.0)
    assert _clean(lat_accel=5.0) is False      # in a curve
    assert _clean(grade_ok=False) is False     # no pitch -> fail closed

DRIVE = car.CarState.GearShifter.drive
CP = SimpleNamespace(steerRatio=15.0, wheelbase=2.7, openpilotLongitudinalControl=True)

def _sm(**over):
    cs = dict(vEgo=10.0, aEgo=1.5, gasPressed=True, brakePressed=False,
              leftBlinker=False, rightBlinker=False, standstill=False,
              gearShifter=DRIVE, steeringAngleDeg=0.0)
    cs.update(over)
    return {
        'carState': SimpleNamespace(**cs),
        'controlsState': SimpleNamespace(longControlState=LongCtrlState.off),
        'radarState': SimpleNamespace(leadOne=SimpleNamespace(status=False, dRel=0.0)),
    }

def _feed(log, n, grade=0.0, **over):
    for _ in range(n):
        log.update(_sm(**over), grade)

def test_steady_hold_logs_after_warmup(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    _feed(log, WARM_N + 5, aEgo=1.5)          # constant a_flat = 1.5
    assert len(log._buf) == 5 + 1             # logs from frame WARM_N onward
    assert all(v == 10.0 and a == pytest.approx(1.5, abs=1e-6) for v, a in log._buf)

def test_ramp_rejected(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    for i in range(WARM_N + 10):
        log.update(_sm(aEgo=1.0 + 0.1 * i), 0.0)   # rising -> jerk >> JERK_EPS
    assert log._buf == []

def test_below_min_accel_rejected(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    _feed(log, WARM_N + 5, aEgo=0.2)          # steady but < MIN_ACCEL
    assert log._buf == []

def test_non_clean_resets_warmup(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    _feed(log, WARM_N + 3, aEgo=1.5)          # warmed, logging
    n_before = len(log._buf)
    log.update(_sm(aEgo=1.5, brakePressed=True), 0.0)  # non-clean -> reset
    _feed(log, WARM_N - 1, aEgo=1.5)          # not yet re-warmed
    assert len(log._buf) == n_before          # nothing logged during re-warm

def test_grade_none_not_logged(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    _feed(log, WARM_N + 5, grade=None, aEgo=1.5)   # no pitch -> not clean
    assert log._buf == []

def test_no_op_long_disables_logging(tmp_path):
    stock = SimpleNamespace(steerRatio=15.0, wheelbase=2.7, openpilotLongitudinalControl=False)
    log = AccelLogger(stock, path=str(tmp_path / "h.csv"))
    _feed(log, WARM_N + 5, aEgo=1.5)
    assert log._buf == []

def test_update_never_raises(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    log.update({}, 0.0)                        # missing keys -> swallowed
    assert log._buf == []

def test_flush_writes_after_header(tmp_path):
    p = tmp_path / "h.csv"
    log = AccelLogger(CP, path=str(p))
    _feed(log, WARM_N + 2, aEgo=1.5)
    log._flush()
    lines = p.read_text().splitlines()
    assert lines[0] == LOG_HEADER
    assert lines[1].startswith("10.000,1.500")

def test_header_written_fresh(tmp_path):
    p = tmp_path / "h.csv"
    AccelLogger(CP, path=str(p))
    assert p.read_text().splitlines()[0] == LOG_HEADER

def test_header_migrates_v1(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("10.000,0.800\n12.000,0.500\n")   # v1-style, no header
    AccelLogger(CP, path=str(p))
    assert (tmp_path / "h.pre_v2.csv").exists()     # old data archived
    assert p.read_text().splitlines()[0] == LOG_HEADER

def test_header_match_appends(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text(LOG_HEADER + "\n7.000,1.200\n")
    AccelLogger(CP, path=str(p))
    assert not (tmp_path / "h.pre_v2.csv").exists()  # not archived
    assert p.read_text().splitlines() == [LOG_HEADER, "7.000,1.200"]
