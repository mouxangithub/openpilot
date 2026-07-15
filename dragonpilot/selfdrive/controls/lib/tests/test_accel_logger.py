from types import SimpleNamespace
import pytest
from cereal import car
from dragonpilot.selfdrive.controls.lib.accel_logger import _should_log, AccelLogger, LOG_HEADER

def _clean(**over):
    args = dict(gas=True, brake=False, blinker=False,
                in_drive=True, moving=True, a_ego=0.8, lead_ttc=9.9, lat_accel=0.2)
    args.update(over)
    return _should_log(**args)

def test_clean_sample_logs():
    assert _clean() is True

def test_each_condition_blocks():
    assert _clean(gas=False) is False
    assert _clean(a_ego=0.0) is False
    assert _clean(brake=True) is False
    assert _clean(blinker=True) is False
    assert _clean(in_drive=False) is False
    assert _clean(moving=False) is False
    assert _clean(lead_ttc=0.5) is False      # < TTC_MIN (1.0)
    assert _clean(lat_accel=5.0) is False

DRIVE = car.CarState.GearShifter.drive
CP = SimpleNamespace(steerRatio=15.0, wheelbase=2.7, openpilotLongitudinalControl=True)

def _sm(**over):
    cs = dict(vEgo=10.0, aEgo=0.8, gasPressed=True, brakePressed=False,
              leftBlinker=False, rightBlinker=False, standstill=False,
              gearShifter=DRIVE, steeringAngleDeg=0.0)
    cs.update(over)
    return {
        'carState': SimpleNamespace(**cs),
        'radarState': SimpleNamespace(leadOne=SimpleNamespace(status=False, dRel=0.0)),
    }

def test_gas_demand_buffers(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    log.update(_sm(), 0.0)                          # driver on gas (manual or override)
    assert log._buf == [(10.0, 0.8)]

def test_no_gas_not_logged(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    log.update(_sm(gasPressed=False), 0.0)          # OP cruising, no gas -> not logged
    assert log._buf == []

def test_grade_correction_applied(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    log.update(_sm(aEgo=0.8), 0.3)                          # a_flat = 0.5
    assert log._buf == [(10.0, pytest.approx(0.5))]

def test_grade_none_not_logged(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    log.update(_sm(), None)
    assert log._buf == []

def test_no_op_long_disables_logging(tmp_path):
    stock = SimpleNamespace(steerRatio=15.0, wheelbase=2.7, openpilotLongitudinalControl=False)
    log = AccelLogger(stock, path=str(tmp_path / "h.csv"))
    log.update(_sm(), 0.0)
    assert log._buf == []

def test_update_never_raises(tmp_path):
    log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
    log.update({}, 0.0)
    assert log._buf == []

def test_flush_writes_after_header(tmp_path):
    p = tmp_path / "h.csv"
    log = AccelLogger(CP, path=str(p))
    log.update(_sm(vEgo=10.0, aEgo=0.8), 0.0)
    log.update(_sm(vEgo=12.0, aEgo=0.5), 0.0)
    log._flush()
    lines = p.read_text().splitlines()
    assert lines[0] == LOG_HEADER
    assert lines[1:] == ["10.000,0.800", "12.000,0.500"]

def test_header_written_fresh(tmp_path):
    p = tmp_path / "h.csv"
    AccelLogger(CP, path=str(p))
    assert p.read_text().splitlines()[0] == LOG_HEADER

def test_header_migrates_old(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("10.000,0.800\n")                          # old format, no v3 header
    AccelLogger(CP, path=str(p))
    assert (tmp_path / "h.pre_v3.csv").exists()
    assert p.read_text().splitlines()[0] == LOG_HEADER

def test_header_match_appends(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text(LOG_HEADER + "\n7.000,1.200\n")
    AccelLogger(CP, path=str(p))
    assert not (tmp_path / "h.pre_v3.csv").exists()
    assert p.read_text().splitlines() == [LOG_HEADER, "7.000,1.200"]
