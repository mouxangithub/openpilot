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

"""REST endpoint functions + the route table.

Each *_api function takes a Request and returns a Response (or raises HTTPError).
build_routes() maps HTTP method + path to these functions; the server calls it
once at startup and holds the result."""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import quote

from dragonpilot.settings import SETTINGS

from .cache import AppCache
from .config import ACCEL_EQ_CONFIG, DEFAULT_DIR, WEB_DIST_PATH, logger
from .habit import _habit_bands, _habit_grid, _habit_points, _read_accel_log
from .http import HTTPError, api_handler, get_safe_path, json_response, route_regex, text_response
from .i18n import _build_i18n_map, _sync_language, base_multilang
from .params_util import _PARAM_SETTINGS, _get_param_value, _get_setting_value, _param_allowed, _save_param, eval_condition, resolve_value


# --- API Endpoints ---
@api_handler
def init_api(request):
  """Provide initial data to the client."""
  cache: AppCache = request.app['cache']
  _sync_language(cache.params)
  return json_response(
    {
      'dp_dev_dashy': cache.get_bool_safe("dp_dev_dashy", True),
      'isOffroad': cache.get_bool_safe("IsOffroad", False),
      # Translation map for the web UI's tr() — shipped at boot so strings are
      # localized before the settings panel can open.
      'i18n': _build_i18n_map(),
    }
  )


@api_handler
def list_files_api(request):
  """List files and folders."""
  path_param = request.query.get('path', '/')
  safe_path = get_safe_path(path_param)

  if not safe_path or not os.path.isdir(safe_path):
    return json_response({'error': 'Invalid or Not Found Path'}, status=404)

  items = []
  for entry in os.listdir(safe_path):
    full_path = os.path.join(safe_path, entry)
    # Skip entries whose real target escapes DEFAULT_DIR (e.g., symlinks).
    # get_safe_path only validates the requested directory itself; each
    # child has to be re-checked to prevent listing files outside the tree.
    real_full = os.path.realpath(full_path)
    if os.path.commonpath((real_full, DEFAULT_DIR)) != DEFAULT_DIR:
      continue
    try:
      stat = os.stat(full_path)
      is_dir = os.path.isdir(full_path)
      items.append(
        {'name': entry, 'is_dir': is_dir, 'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'), 'size': stat.st_size if not is_dir else 0}
      )
    except FileNotFoundError:
      continue

  # Sort: directories first (by mtime desc), then files (by mtime desc)
  dirs = sorted([i for i in items if i['is_dir']], key=lambda x: x['mtime'], reverse=True)
  files = sorted([i for i in items if not i['is_dir']], key=lambda x: x['mtime'], reverse=True)

  relative_path = os.path.relpath(safe_path, DEFAULT_DIR)
  return json_response({'path': '' if relative_path == '.' else relative_path, 'files': dirs + files})


@api_handler
def serve_player_api(request):
  """Serve the HLS player page."""
  file_path = request.query.get('file')
  if not file_path:
    return text_response("File parameter is required.", status=400)
  if get_safe_path(file_path) is None:
    return text_response("Invalid file path.", status=400)

  player_html_path = os.path.join(WEB_DIST_PATH, 'pages', 'player.html')
  try:
    with open(player_html_path, 'r') as f:
      html_template = f.read()
  except FileNotFoundError:
    return text_response("Player HTML not found.", status=500)

  html = html_template.replace('{{FILE_PATH}}', quote(file_path, safe=''))
  return text_response(html, content_type='text/html')


@api_handler
def serve_manifest_api(request):
  """Dynamically generate m3u8 playlist."""
  file_path = request.query.get('file', '').lstrip('/')
  if not file_path:
    return text_response("File parameter is required.", status=400)
  if get_safe_path(file_path) is None:
    return text_response("Invalid file path.", status=400)

  encoded_path = quote(file_path)
  manifest = f"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:60\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:60.0,\n/media/{encoded_path}\n#EXT-X-ENDLIST\n"
  return text_response(manifest, content_type='application/vnd.apple.mpegurl')


@api_handler
def get_settings_config_api(request):
  """Get the settings configuration from settings.py."""
  cache: AppCache = request.app['cache']

  # Return cached settings if fresh (2 second TTL)
  now = time.time()
  if cache._settings_cache is not None and (now - cache._settings_cache_time) < 2:
    return json_response(cache._settings_cache)

  params = cache.params

  # Apply the current LanguageSetting (the switch only writes the param).
  _sync_language(params)

  context = cache.get_settings_context()
  settings_with_values = []

  for section in SETTINGS:
    if not eval_condition(section.get('condition'), context):
      continue

    section_copy = section.copy()
    settings_list = []

    for setting in section.get('settings', []):
      if not eval_condition(setting.get('condition'), context):
        continue

      setting_copy = setting.copy()

      # Resolve callable values
      for field in ['title', 'description', 'suffix', 'special_value_text']:
        if field in setting_copy:
          setting_copy[field] = resolve_value(setting_copy[field])
      if 'options' in setting_copy:
        setting_copy['options'] = [resolve_value(opt) for opt in setting_copy['options']]

      # Get current value based on type
      setting_copy['current_value'] = _get_setting_value(params, setting)
      settings_list.append(setting_copy)

    if settings_list:
      section_copy['settings'] = settings_list
      settings_with_values.append(section_copy)

  # Language switcher metadata rides along with the settings (it's settings-
  # adjacent and the UI already fetches this). The list comes from the device's
  # translation catalog, not a param; the switch itself writes the
  # LanguageSetting param via the generic /api/settings/params endpoint.
  # Offered only where lang_switch_available() (not comma 3/3x).
  # Labels mirror openpilot's raylib device UI (tr("Change Language") /
  # tr("Select a language")) and are translated by the same catalog.
  languages = (
    {
      'available': True,
      'current': base_multilang.language,
      'list': base_multilang.languages,
      'title': base_multilang.tr('Change Language'),
      'dialog': base_multilang.tr('Select a language'),
    }
    if cache.lang_switch_available()
    else {'available': False}
  )

  # Refresh the web UI's translation map too, so switching language updates
  # dashy's own strings (not just the SETTINGS labels) without a reload.
  response_data = {'settings': settings_with_values, 'languages': languages, 'i18n': _build_i18n_map()}
  cache._settings_cache = response_data
  cache._settings_cache_time = now
  return json_response(response_data)


@api_handler
def save_param_api(request):
  """Save a single param value.

  Usage: POST /api/settings/params/{name}
  Body: { "value": <value> }
  """
  param_name = request.match_info.get('param_name')
  if not param_name:
    return json_response({'error': 'param_name is required'}, status=400)
  if not _param_allowed(param_name):
    return json_response({'error': 'Unknown param'}, status=403)

  setting = _PARAM_SETTINGS.get(param_name)
  if setting is not None and setting.get('type') == 'text_display_item':
    return json_response({'error': 'Read-only param'}, status=403)

  cache: AppCache = request.app['cache']
  params = cache.params
  data = request.json()

  if 'value' not in data:
    return json_response({'error': 'value is required in body'}, status=400)

  try:
    _save_param(params, param_name, data['value'])
  except ValueError as e:
    # malformed JSON / un-coercible INT|FLOAT body — a client error, not a 500
    return json_response({'error': f'Invalid value for {param_name}: {e}'}, status=400)

  # Mirror upstream openpilot's TogglesLayout: a needs_restart param also
  # requests an onroad cycle so the change takes effect (openpilot restarts
  # when the car is powered on). The web UI blocks these toggles while engaged
  # so this can't fire mid-drive.
  if setting is not None and setting.get('needs_restart'):
    params.put_bool("OnroadCycleRequested", True)

  cache.invalidate()
  logger.info(f"Param saved: {param_name}={data['value']}")

  return json_response({'status': 'success', 'key': param_name, 'value': data['value']})


@api_handler
def get_accel_eq_config_api(request):
  """Serve the planner's accel-eq contract constants (the single source of
  truth in accel_eq.py) so the web model can't drift from the planner.
  404 when unavailable — the web UI uses this to gate the whole Accel tab.

  "Available" means ALL of: the planner lib imported (constants known), the
  dp_lon_accel_profiles param is registered on this build (so saves work), and
  the current car runs openpilot longitudinal control (the curve only shapes
  accel when openpilot owns longitudinal — on stock-long cars it does nothing).
  Standalone/dev dashy → 404 → tab hidden, web model keeps built-in defaults."""
  cache: AppCache = request.app['cache']
  if ACCEL_EQ_CONFIG is None:
    return json_response({'error': 'accel-eq config unavailable'}, status=404)
  try:
    cache.params.check_key('dp_lon_accel_profiles')  # raises if not in the params manifest
  except Exception:
    return json_response({'error': 'accel-eq param unavailable'}, status=404)
  # Only meaningful when openpilot controls longitudinal on this car. Uses
  # CarParamsPersistent so it still resolves while parked/offroad.
  if not cache.get_car_params().get('openpilot_longitudinal_control'):
    return json_response({'error': 'openpilot longitudinal not available on this car'}, status=404)
  return json_response(ACCEL_EQ_CONFIG)


@api_handler
def get_accel_eq_habit_api(request):
  """Logged (speed, accel) samples + smoothed percentile reference lines for the
  Accel-EQ habit overlay, from accel_log.csv in the data dir. ?meta=1 returns a
  {count, bands} availability probe without shipping the dataset."""
  samples = _read_accel_log(os.path.join(DEFAULT_DIR, 'accel_log.csv'))
  grid = _habit_grid(samples)
  if request.query.get('meta'):
    return json_response({'count': len(samples), 'bands': len(grid)})
  return json_response({'points': _habit_points(samples), 'envelope': _habit_bands(grid)})


@api_handler
def reset_accel_eq_habit_api(request):
  """Archive accel_log.csv (rename -> accel_log.pre_grade.csv) so the habit
  reference rebuilds from clean, grade-corrected data. Non-destructive; the
  rename overwrites any prior archive; idempotent if no log exists yet.
  Filesystem errors propagate to @api_handler (HTTP 500). Returns {count: 0}."""
  src = os.path.join(DEFAULT_DIR, 'accel_log.csv')
  dst = os.path.join(DEFAULT_DIR, 'accel_log.pre_grade.csv')
  try:
    os.replace(src, dst)   # atomic rename; overwrites an existing archive
  except FileNotFoundError:
    pass                    # nothing logged yet -> idempotent success
  return json_response({'count': 0})


@api_handler
def get_param_api(request):
  """Get a single param value."""
  param_name = request.match_info.get('param_name')
  if not param_name:
    return json_response({'error': 'param_name is required'}, status=400)
  if not _param_allowed(param_name):
    return json_response({'error': 'Unknown param'}, status=403)

  cache: AppCache = request.app['cache']
  try:
    value = _get_param_value(cache.params, param_name)
  except Exception:
    value = None

  return json_response({'key': param_name, 'value': value})


# --- Action endpoints ---
# Named side-effectful operations declared by settings items via the
# `action` field (text_input_item / action_item). Each handler receives
# the parsed JSON body and the AppCache; it returns a dict that is
# serialized as the JSON response. Errors should be raised — the wrapper
# converts them to 502/500 responses.
SSH_KEY_FETCH_TIMEOUT_S = 10
SSH_KEY_MAX_BYTES = 16 * 1024  # plenty for any realistic ~/.ssh/authorized_keys
GITHUB_USERNAME_MAX_LEN = 39  # github's own limit


def _validate_github_username(username):
  """GitHub username: 1-39 chars, alnum or single hyphen, no leading/trailing hyphen."""
  if not username or len(username) > GITHUB_USERNAME_MAX_LEN:
    return False
  if username.startswith('-') or username.endswith('-'):
    return False
  if '--' in username:
    return False
  return all(c.isalnum() or c == '-' for c in username)


def _fetch_github_ssh_keys(username):
  """Fetch https://github.com/{username}.keys. Returns the body text on
  HTTP 200; raises HTTPError with an upstream-derived status on failure so
  the action endpoint surfaces the real reason."""
  url = f"https://github.com/{quote(username, safe='')}.keys"
  req = urllib.request.Request(url, headers={'User-Agent': 'dashy'})
  try:
    with urllib.request.urlopen(req, timeout=SSH_KEY_FETCH_TIMEOUT_S) as resp:
      body = resp.read(SSH_KEY_MAX_BYTES + 1)
  except urllib.error.HTTPError as e:
    if e.code == 404:
      raise HTTPError(404, f"GitHub user '{username}' not found")
    raise HTTPError(502, f"github.com returned HTTP {e.code}")
  except urllib.error.URLError as e:
    raise HTTPError(502, f"Could not reach github.com: {e.reason}")
  if len(body) > SSH_KEY_MAX_BYTES:
    raise HTTPError(502, "SSH key response too large")
  return body.decode('utf-8', errors='replace')


def _action_ssh_key_set(request, payload, cache):
  """Fetch the user's GitHub SSH keys and write both params atomically.
  Body: { "value": "<github-username>" }. On success the device's
  sshd_config drop-in is updated by openpilot's own SSH manager."""
  username = (payload.get('value') or '').strip()
  if not _validate_github_username(username):
    raise HTTPError(400, "Invalid GitHub username")

  keys_body = _fetch_github_ssh_keys(username)
  if not keys_body.strip():
    raise HTTPError(400, f"GitHub user '{username}' has no public SSH keys")

  params = cache.params
  # Write keys first; only commit the username if keys were stored
  # successfully — keeps the two params consistent.
  params.put('GithubSshKeys', keys_body)
  params.put('GithubUsername', username)
  cache.invalidate()
  logger.info(f"SSH keys set from github.com/{username} ({len(keys_body)} bytes)")
  return {'status': 'ok', 'username': username, 'key_bytes': len(keys_body)}


def _action_ssh_key_clear(request, payload, cache):
  params = cache.params
  params.put('GithubSshKeys', '')
  params.put('GithubUsername', '')
  cache.invalidate()
  logger.info("SSH keys cleared")
  return {'status': 'ok'}


_ACTION_HANDLERS = {
  'ssh_key_set': _action_ssh_key_set,
  'ssh_key_clear': _action_ssh_key_clear,
}


@api_handler
def run_action_api(request):
  """Dispatch /api/action/{name} → registered handler."""
  name = request.match_info.get('name', '')
  handler = _ACTION_HANDLERS.get(name)
  if handler is None:
    return json_response({'error': f'Unknown action: {name}'}, status=404)

  try:
    payload = request.json()
  except Exception:
    payload = {}

  cache: AppCache = request.app['cache']
  result = handler(request, payload, cache)
  return json_response(result)


@api_handler
def get_model_list_api(request):
  """Get the model list and current selection."""
  cache: AppCache = request.app['cache']
  params = cache.params

  # Get model list. JSON-typed params come back already-parsed in
  # newer dragonpilot; older builds returned bytes/str — handle both.
  model_list = {}
  try:
    raw = params.get("dp_dev_model_list")
    if raw:
      if isinstance(raw, (bytes, str)):
        model_list = json.loads(raw)
      elif isinstance(raw, dict):
        model_list = raw
  except Exception as e:
    logger.debug(f"Could not parse dp_dev_model_list: {e}")

  # Get current selection
  selected_model = ""
  try:
    selected_raw = params.get("dp_dev_model_selected")
    if selected_raw:
      selected_model = selected_raw.decode('utf-8') if isinstance(selected_raw, bytes) else str(selected_raw)
  except Exception as e:
    logger.debug(f"Could not get dp_dev_model_selected: {e}")

  return json_response({'model_list': model_list, 'selected_model': selected_model})


@api_handler
def save_model_selection_api(request):
  """Save the selected model."""
  cache: AppCache = request.app['cache']
  params = cache.params
  data = request.json()

  selected_model = data.get('selected_model', '')

  if not selected_model or selected_model == "[AUTO]":
    params.put("dp_dev_model_selected", "")
    logger.info("Model selection cleared (AUTO mode)")
  else:
    params.put("dp_dev_model_selected", selected_model)
    logger.info(f"Model selection saved: {selected_model}")

  return json_response({'status': 'success'})


# --- Route table ---
def build_routes():
  """(method, compiled route, handler) list. Patterns are mutually exclusive;
  /api/stream is handled directly by the request handler (it streams, never
  returns a buffered Response)."""
  spec = [
    ('GET', '/api/init', init_api),
    ('GET', '/api/files', list_files_api),
    ('GET', '/api/play', serve_player_api),
    ('GET', '/api/manifest.m3u8', serve_manifest_api),
    ('GET', '/api/settings', get_settings_config_api),
    ('GET', '/api/accel_eq/config', get_accel_eq_config_api),
    ('GET', '/api/accel_eq/habit', get_accel_eq_habit_api),
    ('POST', '/api/accel_eq/habit/reset', reset_accel_eq_habit_api),
    ('GET', '/api/settings/params/{param_name}', get_param_api),
    ('POST', '/api/settings/params/{param_name}', save_param_api),
    ('GET', '/api/models', get_model_list_api),
    ('POST', '/api/models/select', save_model_selection_api),
    ('POST', '/api/action/{name}', run_action_api),
  ]
  return [(m, route_regex(p), fn) for m, p, fn in spec]
