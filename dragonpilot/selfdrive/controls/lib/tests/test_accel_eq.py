from dragonpilot.selfdrive.controls.lib.accel_eq import _validate_curve, MAX_ACCEL_CEIL, _select_active, MAX_PTS

def test_valid_curve_passes_through_sorted():
    bp, v = _validate_curve({"bp": [0, 10, 25, 40], "v": [1.6, 1.2, 0.8, 0.6]}, MAX_ACCEL_CEIL)
    assert bp == [0.0, 10.0, 25.0, 40.0]
    assert v == [1.6, 1.2, 0.8, 0.6]

def test_unsorted_speeds_are_sorted_together():
    bp, v = _validate_curve({"bp": [40, 0, 10], "v": [0.6, 1.6, 1.2]}, MAX_ACCEL_CEIL)
    assert bp == [0.0, 10.0, 40.0]
    assert v == [1.6, 1.2, 0.6]

def test_value_clamped_to_ceiling():
    _, v = _validate_curve({"bp": [0, 20], "v": [99.0, -5.0]}, MAX_ACCEL_CEIL)
    assert v == [MAX_ACCEL_CEIL, 0.0]

def test_too_few_points_rejected():
    assert _validate_curve({"bp": [0], "v": [1.6]}, MAX_ACCEL_CEIL) is None

def test_too_many_points_rejected():
    n = MAX_PTS + 1
    assert _validate_curve({"bp": list(range(n)), "v": [1.0] * n}, MAX_ACCEL_CEIL) is None

def test_mismatched_lengths_rejected():
    assert _validate_curve({"bp": [0, 10], "v": [1.6]}, MAX_ACCEL_CEIL) is None

def test_duplicate_speeds_rejected():
    assert _validate_curve({"bp": [10, 10], "v": [1.0, 0.9]}, MAX_ACCEL_CEIL) is None

def test_non_numeric_rejected():
    assert _validate_curve({"bp": [0, "x"], "v": [1.6, 1.2]}, MAX_ACCEL_CEIL) is None

def test_non_finite_rejected():
    assert _validate_curve({"bp": [0, float("inf")], "v": [1.6, 1.2]}, MAX_ACCEL_CEIL) is None

def test_none_and_non_dict_rejected():
    assert _validate_curve(None, MAX_ACCEL_CEIL) is None
    assert _validate_curve([1, 2], MAX_ACCEL_CEIL) is None


DATA = {"profiles": [
    {"name": "Eco", "max": {"bp": [0, 20], "v": [1.0, 0.8]}},
    {"name": "Sport", "max": {"bp": [0, 20], "v": [2.0, 1.6]}},
]}

def test_select_named_profile():
    assert _select_active(DATA, "Sport")["name"] == "Sport"

def test_unknown_name_returns_none():
    assert _select_active(DATA, "Nope") is None   # no first-profile fallback

def test_empty_name_returns_none():
    assert _select_active(DATA, "") is None

def test_no_profiles_returns_none():
    assert _select_active({"profiles": []}, "x") is None
    assert _select_active({}, "x") is None
    assert _select_active(None, "x") is None

def test_unnamed_profiles_ignored():
    bad = {"profiles": [{"max": {}}, {"name": 5}]}
    assert _select_active(bad, "x") is None


import numpy as np
from openpilot.common.params import Params
from dragonpilot.selfdrive.controls.lib.accel_eq import AccelEq, PROFILES_KEY
# Stock fallback is the planner's A_CRUISE_MAX table, injected into AccelEq.
from openpilot.selfdrive.controls.lib.longitudinal_planner import (
    A_CRUISE_MAX_BP as STOCK_MAX_BP, A_CRUISE_MAX_VALS as STOCK_MAX_V,
)

def test_unset_uses_stock():
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, Params())
    for v in (0., 5., 10., 25., 40., 55.):
        assert c.max_accel(v) == float(np.interp(v, STOCK_MAX_BP, STOCK_MAX_V))

def test_active_profile_drives_curve():
    p = Params()
    p.put(PROFILES_KEY, {"active": "Sport", "profiles": [
        {"name": "Sport", "max": {"bp": [0, 40], "v": [2.0, 1.0]},
                          "turn": {"bp": [20, 40], "v": [1.7, 3.2]}},
    ]}, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    assert c.max_accel(0.) == 2.0
    assert c.max_accel(40.) == 1.0

def test_switching_active_changes_curve_on_refresh():
    p = Params()
    p.put(PROFILES_KEY, {"active": "Eco", "profiles": [
        {"name": "Eco",   "max": {"bp": [0, 40], "v": [1.0, 0.5]}},
        {"name": "Sport", "max": {"bp": [0, 40], "v": [2.0, 1.0]}},
    ]}, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    assert c.max_accel(0.) == 1.0
    p.put(PROFILES_KEY, {"active": "Sport", "profiles": [
        {"name": "Eco",   "max": {"bp": [0, 40], "v": [1.0, 0.5]}},
        {"name": "Sport", "max": {"bp": [0, 40], "v": [2.0, 1.0]}},
    ]}, block=True)
    c.maybe_refresh(1)
    assert c.max_accel(0.) == 2.0

def test_no_work_when_unchanged(monkeypatch):
    p = Params()
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    c.maybe_refresh(1)   # warm up: first call resolves the -1 sentinel to a real personality
    calls = []
    monkeypatch.setattr(c, "_reload_doc", lambda: calls.append("doc"))
    monkeypatch.setattr(c, "_resolve", lambda: calls.append("resolve"))
    c.maybe_refresh(1)
    c.maybe_refresh(1)
    assert calls == []  # mtime + personality unchanged → no read, no resolve

def test_personality_change_resolves_without_reread(monkeypatch):
    # A personality change must re-resolve from the cached doc, never re-read the param.
    p = Params()
    p.put(PROFILES_KEY, {
        "use_personality": True,
        "personality_map": {"0": "Sport", "1": "Stock", "2": "Eco"},
        "profiles": [
            {"name": "Stock", "max": {"bp": [0, 40], "v": [1.6, 0.6]}},
            {"name": "Sport", "max": {"bp": [0, 40], "v": [2.0, 1.0]}},
            {"name": "Eco",   "max": {"bp": [0, 40], "v": [1.0, 0.5]}},
        ],
    }, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    reads = []
    monkeypatch.setattr(c, "_reload_doc", lambda: reads.append(1))
    c.maybe_refresh(0)            # aggressive → Sport, resolved from cache
    assert c.max_accel(0.) == 2.0
    assert reads == []            # no JSON re-read on a personality change

def test_malformed_profiles_falls_back_to_stock():
    p = Params()
    # write raw invalid json bytes directly
    p.put(PROFILES_KEY, {"active": "Bad", "profiles": [{"name": "Bad", "max": {"bp": [0], "v": [9]}}]}, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    assert c.max_accel(0.) == float(np.interp(0., STOCK_MAX_BP, STOCK_MAX_V))

def test_deleted_after_set_reverts_to_stock():
    p = Params()
    p.put(PROFILES_KEY, {"active": "S", "profiles": [{"name": "S", "max": {"bp": [0, 40], "v": [2.0, 1.0]}}]}, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    assert c.max_accel(0.) == 2.0
    p.remove(PROFILES_KEY)
    c.maybe_refresh(1)
    assert c.max_accel(0.) == float(np.interp(0., STOCK_MAX_BP, STOCK_MAX_V))

def test_invalid_or_empty_doc_falls_back_to_stock_regardless_of_personality():
    # A doc that isn't a usable dict (non-dict, empty, or no profiles) → stock,
    # for every personality. Mirrors Params.get() returning None on bad/empty JSON.
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, Params())
    stock0 = float(np.interp(0., STOCK_MAX_BP, STOCK_MAX_V))
    for bad in (None, [1, 2, 3], {}, {"use_personality": True, "personality_map": {"0": "X"}}):
        c._doc = bad
        for pers in (0, 1, 2):
            c._personality = pers
            c._resolve()
            assert c.max_accel(0.) == stock0


from openpilot.selfdrive.controls.lib.longitudinal_planner import (
    get_max_accel, A_CRUISE_MAX_BP, A_CRUISE_MAX_VALS,
)

def test_accelcurves_matches_legacy_get_max_accel_when_unset():
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, Params())
    for v in (0., 7., 10., 18., 25., 33., 40., 50.):
        assert c.max_accel(v) == float(get_max_accel(v))
        assert get_max_accel(v) == float(np.interp(v, A_CRUISE_MAX_BP, A_CRUISE_MAX_VALS))


from dragonpilot.selfdrive.controls.lib.accel_eq import _resolve_active_name

PDATA = {"use_personality": True,
         "personality_map": {"0": "Sport", "1": "Stock", "2": "Eco"},
         "profiles": [{"name": "Stock"}, {"name": "Sport"}, {"name": "Eco"}]}

def test_personality_maps_to_profile():
    assert _resolve_active_name(PDATA, 0) == "Sport"
    assert _resolve_active_name(PDATA, 2) == "Eco"

def test_personality_off_uses_active():
    d = {"use_personality": False, "active": "Manual", "profiles": []}
    assert _resolve_active_name(d, 0) == "Manual"

def test_personality_off_no_active_returns_none():
    assert _resolve_active_name({"use_personality": False}, 0) is None   # → stock

def test_personality_unmapped_returns_none():
    d = {"use_personality": True, "personality_map": {"0": "Sport"}, "active": "Manual"}
    assert _resolve_active_name(d, 1) is None   # 1 unmapped → stock, not manual

def test_personality_missing_map_returns_none():
    assert _resolve_active_name({"use_personality": True}, 0) is None

def test_resolve_handles_non_dict():
    assert _resolve_active_name(None, 0) is None


def test_personality_selects_profile_in_accelcurves():
    p = Params()
    p.put(PROFILES_KEY, {
        "use_personality": True,
        "personality_map": {"0": "Sport", "1": "Stock", "2": "Eco"},
        "profiles": [
            {"name": "Stock", "max": {"bp": [0, 40], "v": [1.6, 0.6]}},
            {"name": "Sport", "max": {"bp": [0, 40], "v": [2.0, 1.0]}},
            {"name": "Eco",   "max": {"bp": [0, 40], "v": [1.0, 0.5]}},
        ],
    }, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    c.maybe_refresh(0)                   # aggressive (live personality from the planner)
    assert c.max_accel(0.) == 2.0       # Sport
    c.maybe_refresh(2)                   # relaxed
    assert c.max_accel(0.) == 1.0       # Eco

def test_personality_off_uses_manual_active_in_accelcurves():
    p = Params()
    p.put(PROFILES_KEY, {
        "active": "Stock",
        "use_personality": False,
        "personality_map": {"0": "Sport"},
        "profiles": [
            {"name": "Stock", "max": {"bp": [0, 40], "v": [1.6, 0.6]}},
            {"name": "Sport", "max": {"bp": [0, 40], "v": [2.0, 1.0]}},
        ],
    }, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    c.maybe_refresh(0)                  # personality 0 would map to Sport, but use_personality is off
    assert c.max_accel(0.) == 1.6       # manual "active": Stock wins → injected stock

def test_active_in_json_drives_curve_without_legacy_key():
    p = Params()
    p.put(PROFILES_KEY, {
        "active": "Sport",
        "profiles": [
            {"name": "Stock", "max": {"bp": [0, 40], "v": [1.6, 0.6]}},
            {"name": "Sport", "max": {"bp": [0, 40], "v": [2.0, 1.0]}},
        ],
    }, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    assert c.max_accel(0.) == 2.0

def test_no_active_falls_back_to_stock():
    # No "active" and personality off → injected stock, NOT the first profile.
    p = Params()
    p.put(PROFILES_KEY, {
        "profiles": [
            {"name": "Sport", "max": {"bp": [0, 40], "v": [2.0, 1.0]}},
            {"name": "Eco",   "max": {"bp": [0, 40], "v": [1.0, 0.5]}},
        ],
    }, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    assert c.max_accel(0.) == float(np.interp(0., STOCK_MAX_BP, STOCK_MAX_V))  # stock, not Sport
    assert c.max_accel(0.) != 2.0


def test_stock_profile_ignores_stored_curve():
    # A stale/legacy "Stock" with a stored curve must NOT override the injected
    # (live) stock table — Stock is a mirror, so a planner stock change wins.
    p = Params()
    p.put(PROFILES_KEY, {
        "active": "Stock",
        "profiles": [{"name": "Stock", "max": {"bp": [0, 40], "v": [0.1, 0.1]}}],
    }, block=True)
    c = AccelEq(STOCK_MAX_BP, STOCK_MAX_V, p)
    assert c.max_accel(0.) == float(np.interp(0., STOCK_MAX_BP, STOCK_MAX_V))
    assert c.max_accel(0.) != 0.1
