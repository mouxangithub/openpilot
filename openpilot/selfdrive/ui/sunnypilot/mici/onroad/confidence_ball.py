"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from importlib.resources import as_file

import pyray as rl

from openpilot.selfdrive.ui.onroad.augmented_road_view import BORDER_COLORS
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.system.ui.lib.application import ASSETS_DIR, gui_app

EXP_ICON = "../../sunnypilot/selfdrive/assets/icons/experimental_white.png"  # upstream retired its copy with chill
EXP_ICON_NUCLEUS = (0.479, 0.514, 0.125)  # nucleus centre and clear radius, as fractions of the icon width
EXP_ORBITS_SIZE = 40  # orbit tips reach 0.56 of this from the nucleus (~22.5 px), just inside the 24 px dot


class ConfidenceBallSP:
  def __init__(self):
    self._exp_orbits = self._load_exp_orbits()

  @staticmethod
  def get_animate_status_probs():
    if ui_state.status == UIStatus.LAT_ONLY:
      return ui_state.sm['modelV2'].meta.disengagePredictions.steerOverrideProbs

    # UIStatus.LONG_ONLY
    return ui_state.sm['modelV2'].meta.disengagePredictions.brakeDisengageProbs

  @staticmethod
  def get_lat_long_dot_color():
    if ui_state.status == UIStatus.LAT_ONLY:
      return BORDER_COLORS[UIStatus.LAT_ONLY]

    # UIStatus.LONG_ONLY
    return BORDER_COLORS[UIStatus.LONG_ONLY]

  @staticmethod
  def _load_exp_orbits() -> rl.Texture:
    cache_key = f"exp_orbits:{EXP_ICON}_{EXP_ORBITS_SIZE}"
    if cache_key in gui_app._textures:
      return gui_app._textures[cache_key]

    # orbits only: the nucleus is left as a hole so the dot's gradient shows through it
    with as_file(ASSETS_DIR.joinpath(EXP_ICON)) as path:
      image = gui_app._load_image_from_path(path.as_posix())
    cx, cy, r = (round(f * image.width) for f in EXP_ICON_NUCLEUS)
    rl.image_draw_circle(image, cx, cy, r, rl.BLANK)
    px = round(EXP_ORBITS_SIZE * gui_app._scale)
    rl.image_resize(image, px, px)
    texture = gui_app._load_texture_from_image(image)
    texture.width = texture.height = EXP_ORBITS_SIZE  # logical size, as texture() sets it

    gui_app._textures[cache_key] = texture
    return texture

  def draw_experimental_knockout(self, center_x: float, center_y: float) -> None:
    if not ui_state.experimental_mode:
      return

    # centre the nucleus, not the icon, on the dot
    pos = rl.Vector2(round(center_x - EXP_ICON_NUCLEUS[0] * EXP_ORBITS_SIZE), round(center_y - EXP_ICON_NUCLEUS[1] * EXP_ORBITS_SIZE))
    rl.draw_texture_ex(self._exp_orbits, pos, 0.0, 1.0, rl.BLACK)
