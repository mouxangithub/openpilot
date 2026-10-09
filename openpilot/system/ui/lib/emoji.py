import io
import re
import functools
from importlib.resources import as_file

from PIL import Image, ImageDraw, ImageFont
import pyray as rl

from openpilot.system.ui.lib.application import FONT_DIR

_cache: dict[str, rl.Texture] = {}

EMOJI_REGEX = re.compile(
"""[\U0001F600-\U0001F64F
\U0001F300-\U0001F5FF
\U0001F680-\U0001F6FF
\U0001F1E0-\U0001F1FF
\U00002700-\U000027BF
\U0001F900-\U0001F9FF
\U00002600-\U000026FF
\U00002300-\U000023FF
\U00002B00-\U00002BFF
\U0001FA70-\U0001FAFF
\U0001F700-\U0001F77F
\u2640-\u2642
\u2600-\u2B55
\u200d
\u23cf
\u23e9
\u231a
\ufe0f
\u3030
]+""".replace("\n", ""),
  flags=re.UNICODE
)

@functools.cache
def _load_emoji_font() -> ImageFont.FreeTypeFont:
  with as_file(FONT_DIR.joinpath("NotoColorEmoji.ttf")) as font_path:
    return ImageFont.truetype(io.BytesIO(font_path.read_bytes()), 109)

def find_emoji(text):
  return [(m.start(), m.end(), m.group()) for m in EMOJI_REGEX.finditer(text)]

def emoji_tex(emoji):
  if emoji not in _cache:
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((0, 0), emoji, font=_load_emoji_font(), embedded_color=True)
    with io.BytesIO() as buffer:
      img.save(buffer, format="PNG")
      l = buffer.tell()
      buffer.seek(0)
      _cache[emoji] = rl.load_texture_from_image(rl.load_image_from_memory(".png", buffer.getvalue(), l))
  return _cache[emoji]


def draw_text_with_emojis(font: rl.Font, text: str, pos: rl.Vector2, font_size: int,
                          spacing: float, color: rl.Color) -> None:
  """Draw text that may contain emoji characters.

  Emojis are rendered from a separate color font atlas; normal text is drawn
  with the provided font. Measurements must already account for emoji width via
  measure_text_cached.
  """
  from openpilot.system.ui.lib.text_measure import measure_text_cached
  from openpilot.system.ui.lib.application import FONT_SCALE

  emojis = find_emoji(text)
  if not emojis:
    rl._orig_draw_text_ex(font, text, pos, font_size * FONT_SCALE, spacing, color)
    return

  cursor = rl.Vector2(pos.x, pos.y)
  prev_index = 0
  for start, end, emoji in emojis:
    text_before = text[prev_index:start]
    if text_before:
      rl._orig_draw_text_ex(font, text_before, cursor, font_size * FONT_SCALE, spacing, color)
      cursor.x += measure_text_cached(font, text_before, font_size, spacing).x

    tex = emoji_tex(emoji)
    emoji_scale = font_size / tex.height * FONT_SCALE
    rl.draw_texture_ex(tex, cursor, 0.0, emoji_scale, color)
    cursor.x += font_size * FONT_SCALE
    prev_index = end

  text_after = text[prev_index:]
  if text_after:
    rl._orig_draw_text_ex(font, text_after, cursor, font_size * FONT_SCALE, spacing, color)
