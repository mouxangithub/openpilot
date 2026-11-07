"""API handlers — publish."""

from ai.server.handlers._api_common import *  # noqa: F403

async def api_publish(request: web.Request) -> web.Response:
  """Publish units, settings, forge tokens, and execute publish."""
  try:
    from ai.common.publish_config import save_publish_settings
    from ai.tools.forge import forge_auth_status, set_forge_token
    from ai.tools.publish_tools import publish_changes, publish_status, set_forge_token_tool
    from ai.tools.publish_units import discover_publish_units

    if request.method == "GET":
      view = request.query.get("view", "status")
      if view == "units":
        dirty_only = request.query.get("dirty", "0") in ("1", "true")
        return _json_response(discover_publish_units(include_clean=not dirty_only))
      return _json_response(publish_status())

    try:
      body = await request.json()
    except json.JSONDecodeError:
      return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    op = str(body.get("operation") or body.get("op") or "publish").strip().lower()

    if op in ("save_settings", "settings"):
      patch = body.get("settings") or body
      return _json_response(save_publish_settings(patch if isinstance(patch, dict) else {}))

    if op in ("set_forge_token", "forge_token"):
      return _json_response(set_forge_token_tool(
        forge=str(body.get("forge") or "github"),
        token=str(body.get("token") or ""),
        confirm=True,
      ))

    if op in ("verify_forge", "forge_verify"):
      forge = str(body.get("forge") or "github")
      token = str(body.get("token") or "").strip()
      if token:
        set_forge_token(forge, token)
      return _json_response(forge_auth_status(forge, repo_url=str(body.get("repo_url") or "")))

    if op == "publish":
      state = _get_state_reader().update(timeout=0)
      from ai.system.host_env import is_pc_dev

      def _run(*, confirm: bool) -> dict:
        if confirm:
          allowed, reason = is_action_allowed("write_param", state, admin=is_admin_mode(_PARAMS))
          if not allowed:
            return {"ok": False, "error": reason}
        return publish_changes(
          unit_id=str(body.get("unit_id") or "openpilot"),
          target_mode=str(body.get("target_mode") or ""),
          title=str(body.get("title") or ""),
          body=str(body.get("body") or ""),
          base_branch=str(body.get("base_branch") or ""),
          branch=str(body.get("branch") or ""),
          commit_message=str(body.get("commit_message") or ""),
          paths=body.get("paths"),
          draft=bool(body.get("draft")),
          remote=str(body.get("remote") or ""),
          repo_url=str(body.get("repo_url") or ""),
          severity=str(body.get("severity") or ""),
          confirm=confirm,
          params=_PARAMS,
        )

      if not body.get("confirm"):
        allowed, reason = is_action_allowed("write_param", state, admin=is_admin_mode(_PARAMS))
        if not allowed and not is_pc_dev():
          return _json_response({"ok": False, "error": reason}, status=403)
        return _json_response(_run(confirm=False))
      return _json_response(_run(confirm=True))

    return _json_response({"ok": False, "error": f"unknown operation: {op}"}, status=400)
  except Exception as e:
    cloudlog.error(f"aid: api_publish error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

async def api_issues(request: web.Request) -> web.Response:
  """Issue templates, settings, and create issue."""
  try:
    from ai.common.publish_config import save_publish_settings
    from ai.tools.issue_tools import (
      create_issue,
      discover_issue_templates,
      issue_status,
      report_issue,
    )

    if request.method == "GET":
      view = request.query.get("view", "status")
      unit_id = str(request.query.get("unit_id") or "assistant")
      if view == "templates":
        return _json_response(discover_issue_templates(unit_id=unit_id))
      return _json_response(issue_status())

    try:
      body = await request.json()
    except json.JSONDecodeError:
      return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    op = str(body.get("operation") or body.get("op") or "create").strip().lower()

    if op in ("save_settings", "settings"):
      patch = body.get("settings") or {}
      if isinstance(patch, dict) and patch.get("issue_publish"):
        return _json_response(save_publish_settings({"issue_publish": patch["issue_publish"]}))
      if isinstance(patch, dict):
        return _json_response(save_publish_settings(patch))
      return _json_response({"ok": False, "error": "invalid settings"}, status=400)

    if op == "create":
      state = _get_state_reader().update(timeout=0)
      from ai.system.host_env import is_pc_dev

      def _run(*, confirm: bool) -> dict:
        if confirm:
          allowed, reason = is_action_allowed("write_param", state, admin=is_admin_mode(_PARAMS))
          if not allowed:
            return {"ok": False, "error": reason}
        fields = body.get("fields")
        field_map = {str(k): str(v) for k, v in fields.items()} if isinstance(fields, dict) else None
        labels = body.get("labels")
        label_list = [str(x) for x in labels] if isinstance(labels, list) else None
        return create_issue(
          unit_id=str(body.get("unit_id") or "assistant"),
          target_mode=str(body.get("target_mode") or ""),
          repo_url=str(body.get("repo_url") or ""),
          template_id=str(body.get("template_id") or body.get("template") or "bug"),
          title=str(body.get("title") or ""),
          body=str(body.get("body") or ""),
          fields=field_map,
          labels=label_list,
          attach_audit=bool(body.get("attach_audit", True)),
          confirm=confirm,
          params=_PARAMS,
        )

      if not body.get("confirm"):
        allowed, reason = is_action_allowed("write_param", state, admin=is_admin_mode(_PARAMS))
        if not allowed and not is_pc_dev():
          return _json_response({"ok": False, "error": reason}, status=403)
        return _json_response(_run(confirm=False))
      return _json_response(_run(confirm=True))

    if op == "report":
      state = _get_state_reader().update(timeout=0)
      from ai.system.host_env import is_pc_dev

      def _report(*, confirm: bool) -> dict:
        if confirm:
          allowed, reason = is_action_allowed("write_param", state, admin=is_admin_mode(_PARAMS))
          if not allowed:
            return {"ok": False, "error": reason}
        return report_issue(
          kind=str(body.get("kind") or "bug"),
          unit_id=str(body.get("unit_id") or ""),
          title=str(body.get("title") or ""),
          repro_steps=str(body.get("repro_steps") or body.get("repro") or ""),
          expected=str(body.get("expected") or ""),
          actual=str(body.get("actual") or ""),
          summary=str(body.get("summary") or ""),
          proposal=str(body.get("proposal") or ""),
          severity=str(body.get("severity") or "ui"),
          attach_audit=bool(body.get("attach_audit", True)),
          confirm=confirm,
          params=_PARAMS,
        )

      if not body.get("confirm"):
        allowed, reason = is_action_allowed("write_param", state, admin=is_admin_mode(_PARAMS))
        if not allowed and not is_pc_dev():
          return _json_response({"ok": False, "error": reason}, status=403)
        return _json_response(_report(confirm=False))
      return _json_response(_report(confirm=True))

    return _json_response({"ok": False, "error": f"unknown operation: {op}"}, status=400)
  except Exception as e:
    cloudlog.error(f"aid: api_issues error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

async def api_package_version(request: web.Request) -> web.Response:
  try:
    from ai.infra.version import check_update

    fetch = request.query.get("fetch", "1") not in ("0", "false", "no")
    return _json_response(check_update(fetch_remote=fetch))
  except Exception as e:
    cloudlog.error(f"aid: api_package_version error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

async def api_package_update(request: web.Request) -> web.Response:
  try:
    from ai.system.host_env import is_pc_dev
    from ai.infra.version import run_package_update

    state = _get_state_reader().update(timeout=0)
    if state.is_driving and not is_pc_dev():
      return _json_response({"ok": False, "error": "行驶中无法更新 op助手，请停车后重试。"}, status=403)

    try:
      body = await request.json()
    except (json.JSONDecodeError, ValueError, aiohttp.ClientPayloadError):
      body = {}
    if not body.get("confirm"):
      from ai.infra.version import package_info
      pkg = package_info()
      hint = (
        "将执行 git pull 并重新集成 openpilot。请 POST confirm=true。"
        if pkg.get("is_git_install")
        else "将备份当前 ai/ 并重新克隆最新版本。请 POST confirm=true。"
      )
      return _json_response({
        "ok": True,
        "needs_confirmation": True,
        "hint": hint,
      })

    root = body.get("openpilot_root") or str(openpilot_root())
    result = run_package_update(openpilot_root=str(root))
    status = 200 if result.get("ok") else 500
    return _json_response(result, status=status)
  except Exception as e:
    cloudlog.error(f"aid: api_package_update error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)
