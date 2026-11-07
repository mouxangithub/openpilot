"""i18n — same .po translations as openpilot GUI (multilang)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# LanguageSetting param value → .po file suffix (app_{suffix}.po)
PO_LANG: dict[str, str] = {
  "main": "en",
  "en": "en",
  "zh": "zh-CHS",
  "zh-CHS": "zh-CHS",
  "zh-CHT": "zh-CHT",
  "de": "de",
  "es": "es",
  "fr": "fr",
  "ja": "ja",
  "ko": "ko",
  "pt": "pt-BR",
  "pt-BR": "pt-BR",
  "th": "th",
  "tr": "tr",
  "uk": "uk",
}


_STRINGS_CACHE: dict[str, dict[str, str]] = {}
_PO_MTIMES: dict[str, float] = {}


def _normalize_lang_setting(lang: str) -> str:
  lang = (lang or "en").strip().removeprefix("main_")
  aliases = {"main": "en", "zh": "zh-CHS", "pt": "pt-BR"}
  return aliases.get(lang, lang)


def _translations_dir() -> Path | None:
  candidates = [
    Path(__file__).resolve().parents[3] / "openpilot" / "selfdrive" / "ui" / "translations",
    Path(__file__).resolve().parents[4] / "openpilot" / "selfdrive" / "ui" / "translations",
  ]
  for c in candidates:
    if c.is_dir():
      return c
  return None


def _parse_quoted(s: str) -> str:
  s = s.strip()
  if not (s.startswith('"') and s.endswith('"')):
    return s
  s = s[1:-1]
  return (
    s.replace("\\n", "\n")
    .replace("\\t", "\t")
    .replace('\\"', '"')
    .replace("\\\\", "\\")
  )


def _parse_po_file(path: Path) -> dict[str, str]:
  """Minimal msgid/msgstr parser (PC dev fallback without openpilot.system)."""
  text = path.read_text(encoding="utf-8")
  translations: dict[str, str] = {}
  msgid = ""
  msgstr = ""
  state: str | None = None

  for raw in text.splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
      continue
    if line.startswith("msgid "):
      if state == "msgstr" and msgid:
        translations[msgid] = msgstr
      msgid = _parse_quoted(line[6:].strip())
      msgstr = ""
      state = "msgid"
      continue
    if line.startswith("msgstr "):
      msgstr = _parse_quoted(line[7:].strip())
      state = "msgstr"
      continue
    if line.startswith('"') and state == "msgid":
      msgid += _parse_quoted(line)
    elif line.startswith('"') and state == "msgstr":
      msgstr += _parse_quoted(line)

  if state == "msgstr" and msgid:
    translations[msgid] = msgstr
  return translations


def _load_strings(lang_setting: str) -> dict[str, str]:
  po_code = PO_LANG.get(lang_setting, PO_LANG.get(lang_setting.removeprefix("main_"), "en"))
  tdir = _translations_dir()
  if not tdir:
    return _STRINGS_CACHE.get(po_code, {})
  po_path = tdir / f"app_{po_code}.po"
  if not po_path.is_file():
    return {}

  mtime = po_path.stat().st_mtime
  cached = _STRINGS_CACHE.get(po_code)
  if cached is not None and _PO_MTIMES.get(po_code) == mtime:
    return cached

  try:
    from openpilot.system.ui.lib.multilang import load_translations
    translations, _plurals = load_translations(po_path)
  except Exception:
    translations = _parse_po_file(po_path)
  _STRINGS_CACHE[po_code] = translations
  _PO_MTIMES[po_code] = mtime
  return translations


def _current_language() -> str:
  try:
    from openpilot.common.params import Params
    return _normalize_lang_setting(str(Params().get("LanguageSetting") or "en"))
  except Exception:
    return "en"


def snapshot_i18n() -> dict[str, Any]:
  lang = _current_language()
  strings = _load_strings(lang)
  po_code = PO_LANG.get(lang, PO_LANG.get(lang.removeprefix("main_"), "en"))
  from webui.server.bridge.webui_i18n import webui_extra_strings
  extras = webui_extra_strings(po_code, strings)
  strings = {**strings, **extras}
  return {
    "ok": True,
    "language": lang,
    "po_code": po_code,
    "strings": strings,
    "sync_note": "Shares Params LanguageSetting with on-device GUI; changes apply to both after param write.",
  }
