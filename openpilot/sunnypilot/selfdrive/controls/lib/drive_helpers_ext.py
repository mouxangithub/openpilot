from opendbc.car.volkswagen.values import VolkswagenFlags


def is_volkswagen_meb(CP) -> bool:
  """Return True if the platform is a Volkswagen MEB (ID./Enyaq) EV."""
  return CP.brand == "volkswagen" and bool(CP.flags & VolkswagenFlags.MEB)
