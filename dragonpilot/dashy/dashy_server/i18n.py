# Copyright (c) 2026, Rick Lan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, and/or sublicense,
# for non-commercial purposes only, subject to the following conditions:
#
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
# - Commercial use (e.g. use in a product, service, or activity intended to
#   generate revenue) is prohibited without explicit written permission from
#   the copyright holder.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Language sync + translation-map building for the web UI's tr()."""

from openpilot.system.ui.lib.multilang import multilang as base_multilang

# dragonpilot's translation catalog (.mo) is where dashy's JS strings are merged
# by update_translations.py; used to build the web UI's translation map. Falls
# back to base multilang if the dragonpilot wrapper isn't importable.
try:
  from dragonpilot.system.ui.lib.multilang import multilang as dp_multilang
except Exception:
  dp_multilang = base_multilang


def _sync_language(params):
  """Apply the current LanguageSetting param to multilang.

  The language switch only writes the param; this makes the translation
  catalog reflect it (so served strings / the i18n map use the right language)."""
  current_lang = params.get("LanguageSetting")
  if not current_lang:
    return
  lang_str = current_lang.decode() if isinstance(current_lang, bytes) else str(current_lang)
  lang_str = lang_str.removeprefix("main_")
  if lang_str != base_multilang.language and lang_str in base_multilang.languages.values():
    base_multilang._language = lang_str
    base_multilang.setup()


def _build_i18n_map():
  """Translation map {english: translated} for the active language, consumed
  by the web UI's tr(). Sourced from the dragonpilot .mo catalog, where dashy's
  JS strings are merged by update_translations.py. Empty for English / when no
  catalog is loaded → the web tr() falls back to the original English text."""
  try:
    dp_multilang._ensure_loaded()
    catalog = getattr(dp_multilang._dragon_translation, '_catalog', None)
  except Exception:
    catalog = None
  if not catalog:
    return {}
  # GNUTranslations._catalog keys are msgid strings; skip the "" header entry
  # and the '\x00'-joined plural keys, and drop empty translations.
  return {k: v for k, v in catalog.items() if isinstance(k, str) and k and '\x00' not in k and v}
