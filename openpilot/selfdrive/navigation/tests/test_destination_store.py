# Favorite/recent destination store tests.
# Run on a PC only (device has no pytest): python -m pytest openpilot/selfdrive/navigation/tests/test_destination_store.py -q --noconftest
import json

from openpilot.selfdrive.navigation.destination_store import (
  FAVORITE_DESTINATIONS_KEY,
  NAVIGATION_DESTINATION_KEY,
  RECENT_DESTINATIONS_KEY,
  NavigationDestinationStore,
  favorite_destination_id,
  load_favorite_destinations,
  normalize_destination_payload,
  normalize_favorite_destination,
  ordered_favorite_destinations,
  routing_configured,
  same_destination,
  set_navigation_destination,
  update_recent_destinations,
)


def test_normalize_destination_payload_requires_name_and_coordinates():
  payload = {
    "name": "123 Main St",
    "latitude": "41.881832",
    "longitude": "-87.623177",
  }

  assert normalize_destination_payload(payload) == {
    "name": "123 Main St",
    "place_name": "123 Main St",
    "latitude": 41.881832,
    "longitude": -87.623177,
  }
  assert normalize_destination_payload({"name": "Missing coords"}) is None


def test_recent_destinations_dedupe_and_cap():
  existing = json.dumps([
    {"place_name": "Old 1"},
    {"place_name": "Old 2"},
    {"place_name": "Home"},
    {"place_name": "Old 3"},
    {"place_name": "Old 4"},
    {"place_name": "Old 5"},
    {"place_name": "Old 6"},
    {"place_name": "Old 7"},
    {"place_name": "Old 8"},
    {"place_name": "Old 9"},
  ])

  updated = update_recent_destinations(existing, {
    "name": "Home",
    "latitude": 1.0,
    "longitude": 2.0,
  })

  assert updated[0]["place_name"] == "Home"
  assert len(updated) == 10
  assert [entry["place_name"] for entry in updated].count("Home") == 1
  assert updated[-1]["place_name"] == "Old 9"


def test_recent_destinations_retain_coordinates_for_saved_name():
  updated = update_recent_destinations("[]", {
    "name": "Renamed favorite",
    "latitude": 41.881832,
    "longitude": -87.623177,
  })

  assert updated[0] == {
    "place_name": "Renamed favorite",
    "name": "Renamed favorite",
    "latitude": 41.881832,
    "longitude": -87.623177,
  }


def test_favorite_normalization_rejects_malformed_and_non_finite_values():
  assert normalize_favorite_destination({"name": "Missing coordinates"}) is None
  assert normalize_favorite_destination({"name": "Bad", "latitude": "nan", "longitude": 2}) is None
  assert normalize_favorite_destination({"name": "Bad", "latitude": 1, "longitude": "inf"}) is None

  normalized = normalize_favorite_destination({"place_name": "Home", "latitude": "1", "longitude": "2"})
  assert normalized is not None
  assert normalized["name"] == "Home"
  assert normalized["latitude"] == 1.0
  assert normalized["longitude"] == 2.0


def test_load_favorites_is_safe_for_malformed_json_and_filters_invalid_entries():
  raw = json.dumps([
    {"name": "Valid", "latitude": 1, "longitude": 2},
    {"name": "Missing longitude", "latitude": 1},
    {"name": "Overflow", "latitude": 10 ** 1000, "longitude": 2},
    "not a favorite",
  ])

  assert [favorite["name"] for favorite in load_favorite_destinations(raw)] == ["Valid"]
  assert load_favorite_destinations("not json") == []
  assert load_favorite_destinations(json.dumps({"name": "not a list"})) == []


def test_ordered_favorites_put_home_then_work_then_remaining_alphabetically():
  favorites = [
    {"name": "zulu", "latitude": 1, "longitude": 1},
    {"name": "Work", "latitude": 2, "longitude": 2, "is_work": True},
    {"name": "bravo", "latitude": 3, "longitude": 3},
    {"name": "Home", "latitude": 4, "longitude": 4, "is_home": True},
    {"name": "alpha", "latitude": 5, "longitude": 5},
  ]

  ordered = ordered_favorite_destinations(favorites)

  assert [favorite["name"] for favorite in ordered] == ["Home", "Work", "alpha", "bravo", "zulu"]
  assert [favorite["name"] for favorite in ordered_favorite_destinations(favorites, limit=3)] == ["Home", "Work", "alpha"]


def test_destination_equality_uses_coordinate_tolerance():
  left = {"name": "A", "latitude": 1.0, "longitude": 2.0}
  almost_same = {"name": "B", "latitude": 1.0000005, "longitude": 1.9999995}
  different = {"name": "A", "latitude": 1.01, "longitude": 2.0}

  assert same_destination(left, almost_same)
  assert not same_destination(left, different)
  assert not same_destination(left, None)


class FakeParams:
  def __init__(self, values=None):
    self.values = dict(values or {})
    self.writes = []
    self.removed = []

  def get(self, key, encoding=None, default=None):
    value = self.values.get(key, default)
    if encoding == "utf-8" and isinstance(value, bytes):
      return value.decode("utf-8")
    return value

  def put(self, key, value):
    self.values[key] = value
    self.writes.append((key, value))

  def remove(self, key):
    self.values.pop(key, None)
    self.removed.append(key)


def test_destination_write_updates_active_destination_and_recents():
  params = FakeParams({RECENT_DESTINATIONS_KEY: "[]"})

  destination = set_navigation_destination(params, {"name": "Home", "latitude": 1, "longitude": 2})

  assert destination == {"name": "Home", "place_name": "Home", "latitude": 1.0, "longitude": 2.0}
  # NavDestination is a JSON-typed param: Params.put receives the dict directly.
  assert params.values[NAVIGATION_DESTINATION_KEY] == destination
  # ApiCache_NavDestinations is a STRING-typed param: stored as a JSON string.
  assert json.loads(params.values[RECENT_DESTINATIONS_KEY])[0]["place_name"] == "Home"


def test_same_destination_write_is_idempotent_and_does_not_touch_recents():
  params = FakeParams({
    NAVIGATION_DESTINATION_KEY: json.dumps({"name": "Home", "latitude": 1, "longitude": 2}),
    RECENT_DESTINATIONS_KEY: [{"place_name": "Existing"}],
  })

  result = set_navigation_destination(
    params,
    {"name": "Home", "latitude": 1.0000005, "longitude": 2},
    skip_if_same=True,
  )

  assert result is not None
  assert params.writes == []
  assert params.values[RECENT_DESTINATIONS_KEY] == [{"place_name": "Existing"}]

  settings_params = FakeParams(dict(params.values))
  set_navigation_destination(settings_params, {"name": "Home", "latitude": 1.0, "longitude": 2.0})
  assert [key for key, _value in settings_params.writes] == [NAVIGATION_DESTINATION_KEY, RECENT_DESTINATIONS_KEY]


def test_navigation_destination_store_keeps_settings_favorite_migration_and_mutations():
  params = FakeParams({
    FAVORITE_DESTINATIONS_KEY: json.dumps([{"name": "Home", "latitude": 1, "longitude": 2}]),
  })
  store = NavigationDestinationStore(params)

  favorites = store.favorite_destinations()
  assert favorites[0]["id"] == favorite_destination_id({"name": "Home", "latitude": 1, "longitude": 2})
  assert params.writes[0][0] == FAVORITE_DESTINATIONS_KEY

  added = store.add_favorite({"name": "Work", "latitude": 3, "longitude": 4})
  assert [favorite["name"] for favorite in added] == ["Home", "Work"]
  assert store.update_favorite(added[1], is_work=True)[1]["is_work"] is True
  assert [favorite["name"] for favorite in store.remove_favorite(added[0])] == ["Work"]


def test_routing_configured_only_requires_a_non_empty_secret_key():
  assert not routing_configured(FakeParams())
  assert not routing_configured(FakeParams({"MapboxSecretKey": "  "}))
  assert routing_configured(FakeParams({"MapboxSecretKey": "secret"}))
