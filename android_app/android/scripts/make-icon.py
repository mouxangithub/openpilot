#!/usr/bin/env python3
"""Makes the Android app's icons from the iPhone app's.

    python3 android/scripts/make-icon.py

The icon is macos/scripts/make-icon.swift's picture: a green J on a dark
plate whose background runs from #181C23 at the top to #0C0D11 at the bottom.
Android's adaptive icon is two layers, so this takes the plate's background
out of the iPhone icon (a pixel's alpha is how far it stands from the
background at its height), keeping the J and its glow as the foreground,
and ic_launcher_background.xml draws the gradient. The same mask, in white,
is the monochrome layer and the notification icon.

The outputs are committed, so this runs once, with Pillow.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'ios/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png'
RES = ROOT / 'android/app/src/main/res'

TOP = (24, 28, 35)
BOTTOM = (12, 13, 17)
# The 824 px plate inside Apple's 1024 px template.
PLATE = (100, 100, 924, 924)
DENSITIES = {'mdpi': 1, 'hdpi': 1.5, 'xhdpi': 2, 'xxhdpi': 3, 'xxxhdpi': 4}


def background(y: int, height: int) -> tuple:
  t = y / max(1, height - 1)
  return tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM, strict=True))


def extract(plate: Image.Image) -> Image.Image:
  """The J over a transparent background."""
  width, height = plate.size
  out = Image.new('RGBA', plate.size)
  source = plate.load()
  target = out.load()
  for y in range(height):
    bg = background(y, height)
    for x in range(width):
      r, g, b, _ = source[x, y]
      diff = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
      alpha = min(1.0, max(0.0, (diff - 6) / 60))
      if alpha <= 0:
        continue
      # the colour that, over the background at this alpha, gives this pixel
      color = tuple(max(0, min(255, round((c - k * (1 - alpha)) / alpha))) for c, k in zip((r, g, b), bg, strict=True))
      target[x, y] = (*color, round(alpha * 255))
  return out


def main() -> None:
  icon = Image.open(SOURCE).convert('RGBA')
  plate = icon.crop(PLATE)
  art = extract(plate)
  box = art.getbbox()
  art = art.crop(box)

  # 108 dp layers; everything inside the 66 dp circle the masks keep.
  layer = 432
  fit = 0.56 * layer
  scale = fit / max(art.size)
  art = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
  foreground = Image.new('RGBA', (layer, layer))
  foreground.alpha_composite(art, ((layer - art.width) // 2, (layer - art.height) // 2))
  mask = foreground.getchannel('A')
  monochrome = Image.new('RGBA', (layer, layer), (255, 255, 255, 0))
  monochrome.putalpha(mask)

  for density, factor in DENSITIES.items():
    size = round(108 * factor)
    folder = RES / f'mipmap-{density}'
    folder.mkdir(parents=True, exist_ok=True)
    foreground.resize((size, size), Image.LANCZOS).save(folder / 'ic_launcher_foreground.png', optimize=True)
    monochrome.resize((size, size), Image.LANCZOS).save(folder / 'ic_launcher_monochrome.png', optimize=True)

    # Notification: 24 dp, the J filling the middle 20 dp, white on nothing.
    note = round(24 * factor)
    silhouette = Image.new('RGBA', art.size, (255, 255, 255, 0))
    silhouette.putalpha(art.getchannel('A').point(lambda a: 255 if a > 90 else 0))
    inner = round(20 * factor)
    s = inner / max(silhouette.size)
    silhouette = silhouette.resize((max(1, round(silhouette.width * s)), max(1, round(silhouette.height * s))), Image.LANCZOS)
    canvas = Image.new('RGBA', (note, note), (255, 255, 255, 0))
    canvas.alpha_composite(silhouette, ((note - silhouette.width) // 2, (note - silhouette.height) // 2))
    folder = RES / f'drawable-{density}'
    folder.mkdir(parents=True, exist_ok=True)
    canvas.save(folder / 'ic_notification.png', optimize=True)


if __name__ == '__main__':
  main()
