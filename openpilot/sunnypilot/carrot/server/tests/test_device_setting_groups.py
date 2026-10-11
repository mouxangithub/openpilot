from openpilot.sunnypilot.carrot.server.services import device_info


def test_defaults_are_derived_from_the_groups_not_restated():
  from_groups = {name: default for _group, entries in device_info.DEVICE_SETTING_GROUPS for name, default in entries}
  assert device_info.DEVICE_SETTING_DEFAULTS == from_groups


def test_no_parameter_appears_in_two_groups():
  names = [name for _group, entries in device_info.DEVICE_SETTING_GROUPS for name, _default in entries]
  assert len(names) == len(set(names))


def test_every_default_belongs_to_exactly_one_group():
  grouped = device_info.get_device_setting_group_names()
  flattened = [name for names in grouped.values() for name in names]
  assert sorted(flattened) == sorted(device_info.DEVICE_SETTING_DEFAULTS)


def test_the_group_mapping_keeps_declaration_order():
  grouped = device_info.get_device_setting_group_names()
  base_groups = [group for group, _entries in device_info.DEVICE_SETTING_GROUPS]
  assert list(grouped)[:len(base_groups)] == base_groups
  assert grouped["Device"][0] == "DeviceType"
  assert grouped["Toggles"][0] == "OpenpilotEnabledToggle"


def test_the_base_groups_the_web_renders_are_all_present():
  grouped = device_info.get_device_setting_group_names()
  # Network is read-only and has no parameters, so it is intentionally absent.
  assert {"Device", "Software", "Toggles", "Developer"} <= set(grouped)


def test_sunnypilot_sections_follow_the_catalog_menu():
  grouped = device_info.get_device_setting_group_names()
  sp = device_info._sp_device_setting_groups()
  expected = {gid for gid, names in sp.items() if names}
  assert expected <= set(grouped)
  # sidebar order matches SP_DEVICE_MENU_GROUPS and every name is a string
  order = [gid for gid, _menu in device_info.SP_DEVICE_MENU_GROUPS if gid in grouped]
  assert order == [gid for gid, _menu in device_info.SP_DEVICE_MENU_GROUPS if gid in expected]
  for names in sp.values():
    assert all(isinstance(name, str) and name for name in names)


def test_sunnypilot_sections_do_not_overlap_the_base_groups():
  grouped = device_info.get_device_setting_group_names()
  base = {name for group, entries in device_info.DEVICE_SETTING_GROUPS for name, _default in entries}
  for group_id in device_info.SP_DEVICE_MENU_GROUPS:
    for name in grouped.get(group_id[0], []):
      assert name not in base, f"{name} appears in both {group_id[0]} and a base group"


def test_sunnypilot_sections_degrade_to_empty_without_a_catalog(monkeypatch, tmp_path):
  from openpilot.sunnypilot.carrot.server import config
  monkeypatch.setattr(config, "DEFAULT_SETTINGS_PATH", str(tmp_path / "missing.json"))
  monkeypatch.setattr(device_info, "_sp_device_groups_cache", None)
  try:
    assert device_info._sp_device_setting_groups() == {}
  finally:
    monkeypatch.setattr(device_info, "_sp_device_groups_cache", None)


def test_parameters_the_ui_depends_on_are_not_dropped():
  grouped = device_info.get_device_setting_group_names()
  # Each of these drives a specific control; losing one silently blanks it.
  assert "LongitudinalPersonality" in grouped["Toggles"]
  assert "ExperimentalModeConfirmed" in grouped["Toggles"]
  assert "SoftwareMenu" in grouped["Device"]
  assert {"GithubUsername", "GithubSshKeys"} <= set(grouped["Developer"])


def test_the_mapping_is_a_copy_callers_cannot_corrupt():
  first = device_info.get_device_setting_group_names()
  first["Device"].append("Injected")
  assert "Injected" not in device_info.get_device_setting_group_names()["Device"]
