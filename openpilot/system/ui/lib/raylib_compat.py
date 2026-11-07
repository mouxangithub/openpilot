"""pyray-era API shims on raylib_nb.

The zp develop migration moved the UI from pyray (cffi) to raylib_nb
(nanobind, a much smaller hand-picked API surface). Fork-specific files
still call a handful of pyray-style APIs; this module back-fills them so
every call site works unchanged. Import this module before any UI code
renders (application.py imports it first thing).
"""
import math

import raylib_nb as rl


def install() -> None:
  if not hasattr(rl, "color_to_int"):
    def color_to_int(c) -> int:
      return ((int(c.r) & 0xFF)
              | ((int(c.g) & 0xFF) << 8)
              | ((int(c.b) & 0xFF) << 16)
              | ((int(c.a) & 0xFF) << 24))
    rl.color_to_int = color_to_int

  if not hasattr(rl, "set_exit_key"):
    rl.set_exit_key = lambda *args, **kwargs: None

  if not hasattr(rl, "take_screenshot"):
    rl.take_screenshot = lambda *args, **kwargs: None

  if not hasattr(rl, "draw_circle_lines"):
    def draw_circle_lines(center_x, center_y, radius, color, segments=36):
      prev = None
      for i in range(segments + 1):
        a = 2.0 * math.pi * i / segments
        x = center_x + radius * math.cos(a)
        y = center_y + radius * math.sin(a)
        if prev is not None:
          rl.draw_line(int(prev[0]), int(prev[1]), int(x), int(y), color)
        prev = (x, y)
    rl.draw_circle_lines = draw_circle_lines

  if not hasattr(rl, "draw_poly"):
    def draw_poly(center, sides, radius, rotation, color):
      rot = math.radians(rotation)
      pts = [rl.Vector2(center.x, center.y)]
      for i in range(sides):
        a = rot + 2.0 * math.pi * i / sides
        pts.append(rl.Vector2(center.x + radius * math.cos(a), center.y + radius * math.sin(a)))
      rl.draw_triangle_fan(pts, len(pts), color)
    rl.draw_poly = draw_poly

  if not hasattr(rl, "draw_poly_lines"):
    def draw_poly_lines(center, sides, radius, rotation, color):
      rot = math.radians(rotation)
      prev = None
      for i in range(sides + 1):
        a = rot + 2.0 * math.pi * i / sides
        x = center.x + radius * math.cos(a)
        y = center.y + radius * math.sin(a)
        if prev is not None:
          rl.draw_line(int(prev[0]), int(prev[1]), int(x), int(y), color)
        prev = (x, y)
    rl.draw_poly_lines = draw_poly_lines

  if not hasattr(rl, "ffi"):
    class _FFI:
      """pyray's cffi shim: nanobind draw calls accept plain Python sequences,
      so new() builds a list, from_buffer()/cast() pass data through."""

      @staticmethod
      def new(type_spec, data=None):
        if data is None:
          return []
        return list(data)

      @staticmethod
      def from_buffer(value):
        return value

      @staticmethod
      def cast(type_spec, value):
        return value

    rl.ffi = _FFI

  if not hasattr(rl, "load_image_from_memory"):
    def load_image_from_memory(file_type, data, size=None):
      # Decode with PIL and hand the bytes to the native loader via a temp
      # file; the native API has no from-memory image loader.
      import io
      import os
      import tempfile
      from PIL import Image as PILImage
      pil = PILImage.open(io.BytesIO(bytes(data)))
      pil.load()
      with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        pil.save(f, format="PNG")
        path = f.name
      try:
        return rl.load_image(path)
      finally:
        try:
          os.unlink(path)
        except OSError:
          pass
    rl.load_image_from_memory = load_image_from_memory

  # startup_recovery debug previews only; the on-screen recovery flow does
  # not need them.
  if not hasattr(rl, "export_image"):
    rl.export_image = lambda *args, **kwargs: None

  if not hasattr(rl, "image_flip_vertical"):
    rl.image_flip_vertical = lambda *args, **kwargs: None


install()
