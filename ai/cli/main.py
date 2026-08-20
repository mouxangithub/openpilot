#!/usr/bin/env python3
"""OP Agent CLI — short command name: ``op``.

Talk to the running OP Agent service (default http://127.0.0.1:5090) or run
read-only checks locally on the device.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE = os.environ.get("OP_AGENT_URL", os.environ.get("OP_URL", "http://127.0.0.1:5090")).rstrip("/")

WIZARD_ALIASES = {
  "adapt": "adapt_new_car",
  "tune": "tune_feel",
  "doctor": "cant_engage",
  "engage": "cant_engage",
  "review": "review_trip",
  "trip": "review_trip",
}


def _request(method: str, path: str, body: dict[str, Any] | None = None, *, timeout: float = 120.0) -> dict[str, Any]:
  url = f"{DEFAULT_BASE}{path}"
  data = None
  headers = {"Accept": "application/json"}
  if body is not None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers["Content-Type"] = "application/json; charset=utf-8"
  req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      raw = resp.read().decode("utf-8", errors="replace")
      return json.loads(raw) if raw.strip() else {"ok": True}
  except urllib.error.HTTPError as e:
    try:
      payload = json.loads(e.read().decode("utf-8", errors="replace"))
    except Exception:
      payload = {"ok": False, "error": f"HTTP {e.code}"}
    return payload
  except urllib.error.URLError as e:
    return {"ok": False, "error": f"Cannot reach OP Agent at {DEFAULT_BASE}: {e.reason}"}


def _stream_chat(body: dict[str, Any]) -> int:
  from ai.cli.runner import stream_chat_http

  try:
    for event in stream_chat_http(body, base_url=DEFAULT_BASE):
      et = event.get("type")
      if et == "content" and event.get("content"):
        sys.stdout.write(event["content"])
        sys.stdout.flush()
      elif et == "error":
        print(f"\n[error] {event.get('error')}", file=sys.stderr)
        return 1
      elif et == "done" and event.get("ok") is False:
        print(f"\n[error] {event.get('error')}", file=sys.stderr)
        return 1
    print()
    return 0
  except Exception as e:
    print(f"Cannot reach OP Agent at {DEFAULT_BASE}: {e}", file=sys.stderr)
    return 2


def cmd_status(_args: argparse.Namespace) -> int:
  data = _request("GET", "/api/ai/status")
  if not data.get("ok"):
    print(data.get("error") or data, file=sys.stderr)
    return 1
  ai = data.get("ai") or {}
  driving = data.get("driving")
  print(f"OP Agent @ {DEFAULT_BASE}")
  print(f"  driving: {driving}")
  print(f"  configured: {ai.get('configured')}")
  print(f"  model: {ai.get('provider')} / {ai.get('model')}")
  return 0


def cmd_wizards(_args: argparse.Namespace) -> int:
  data = _request("GET", "/api/ai/consumer/wizards")
  if not data.get("ok"):
    print(data.get("error") or data, file=sys.stderr)
    return 1
  for w in data.get("wizards") or []:
    slash = ", ".join(w.get("slash") or [])
    print(f"{w.get('icon', '•')} {w.get('name')} ({w.get('id')})")
    print(f"   {w.get('description')}")
    if slash:
      print(f"   slash: {slash}")
  return 0


def _resolve_wizard(wizard_id: str) -> str:
  return WIZARD_ALIASES.get(wizard_id, wizard_id)


def cmd_wizard(args: argparse.Namespace) -> int:
  wid = _resolve_wizard(args.wizard)
  start = _request("GET", f"/api/ai/consumer/wizards/{wid}/start")
  if not start.get("ok"):
    print(start.get("error") or start, file=sys.stderr)
    return 1
  prompt = args.message or start.get("message") or ""
  workflow = start.get("workflow")
  body: dict[str, Any] = {
    "messages": [{"role": "user", "content": prompt}],
    "consumerMode": True,
  }
  if workflow:
    body["workflow"] = workflow
  return _stream_chat(body)


def cmd_chat(args: argparse.Namespace) -> int:
  if not args.message:
    print("Usage: op chat \"你的问题\"", file=sys.stderr)
    return 1
  body: dict[str, Any] = {"messages": [{"role": "user", "content": args.message}]}
  if args.workflow:
    body["workflow"] = args.workflow
  if args.consumer:
    body["consumerMode"] = True
  return _stream_chat(body)


def cmd_doctor(args: argparse.Namespace) -> int:
  args.wizard = "cant_engage"
  args.message = args.message or "车开不起来，请帮我排查。"
  return cmd_wizard(args)


def cmd_tune(args: argparse.Namespace) -> int:
  args.wizard = "tune_feel"
  args.message = args.message or "帮我调驾驶手感。"
  return cmd_wizard(args)


def cmd_adapt(args: argparse.Namespace) -> int:
  args.wizard = "adapt_new_car"
  args.message = args.message or "我要适配一辆新车。"
  return cmd_wizard(args)


def cmd_backup(args: argparse.Namespace) -> int:
  if args.action == "export":
    data = _request("GET", "/api/ai/platform/backup?operation=export")
    if not data.get("ok"):
      print(data.get("error") or data, file=sys.stderr)
      return 1
    out = args.out or "op-backup.json"
    with open(out, "w", encoding="utf-8") as f:
      json.dump(data.get("bundle") or data, f, ensure_ascii=False, indent=2)
    print(f"Exported to {out}")
    return 0
  if args.action == "restore":
    if not args.file:
      print("--file required for restore", file=sys.stderr)
      return 1
    with open(args.file, encoding="utf-8") as f:
      bundle = json.load(f)
    data = _request("POST", "/api/ai/platform/backup", {
      "operation": "restore",
      "bundle": bundle,
      "confirm": True,
      "mode": args.mode,
    })
    if not data.get("ok"):
      print(data.get("error") or data, file=sys.stderr)
      return 1
    print("Restore complete.")
    return 0
  print("Use: op backup export|restore", file=sys.stderr)
  return 1


def cmd_config(args: argparse.Namespace) -> int:
  data = _request("GET", "/api/ai/config")
  if not data.get("ok"):
    print(data.get("error") or data, file=sys.stderr)
    return 1
  if args.json:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0
  cfg = data.get("config") or data
  print(f"provider: {cfg.get('provider')}")
  print(f"model: {cfg.get('model')}")
  print(f"configured: {cfg.get('configured')}")
  return 0


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    prog="op",
    description="OP Agent — 车主向 AI 助手命令行",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=textwrap.dedent(f"""
    环境变量:
      OP_AGENT_URL / OP_URL   服务地址（默认 {DEFAULT_BASE}）

    示例:
      op status
      op chat "跟车太近怎么办"
      op tune
      op doctor
      op adapt
      op backup export -o backup.json
      ssh comma 'op chat "帮我复盘上一趟"'
    """),
  )
  parser.add_argument("--url", default=DEFAULT_BASE, help="OP Agent base URL")
  sub = parser.add_subparsers(dest="command", required=True)

  sub.add_parser("status", help="服务与车辆状态").set_defaults(func=cmd_status)
  sub.add_parser("wizards", help="列出车主向导").set_defaults(func=cmd_wizards)

  p_chat = sub.add_parser("chat", help="对话")
  p_chat.add_argument("message", nargs="?", help="用户消息")
  p_chat.add_argument("--workflow", "-w", help="工作流 ID")
  p_chat.add_argument("--consumer", action="store_true", help="车主通俗模式")
  p_chat.set_defaults(func=cmd_chat)

  for name, help_text, handler in (
    ("doctor", "开不起来排查", cmd_doctor),
    ("tune", "调驾驶手感", cmd_tune),
    ("adapt", "适配新车", cmd_adapt),
  ):
    p = sub.add_parser(name, help=help_text)
    p.add_argument("message", nargs="?", help="补充说明")
    p.set_defaults(func=handler)

  p_wiz = sub.add_parser("wizard", help="运行指定向导")
  p_wiz.add_argument("wizard", help="向导 ID 或别名")
  p_wiz.add_argument("message", nargs="?", help="补充说明")
  p_wiz.set_defaults(func=cmd_wizard)

  p_bak = sub.add_parser("backup", help="平台备份 export|restore")
  p_bak.add_argument("action", choices=["export", "restore"])
  p_bak.add_argument("-o", "--out", help="导出文件路径")
  p_bak.add_argument("--file", "-f", help="恢复用的 JSON 文件")
  p_bak.add_argument("--mode", default="merge", choices=["merge", "replace"])
  p_bak.set_defaults(func=cmd_backup)

  p_cfg = sub.add_parser("config", help="查看 AI 配置")
  p_cfg.add_argument("--json", action="store_true")
  p_cfg.set_defaults(func=cmd_config)

  return parser


def main(argv: list[str] | None = None) -> int:
  global DEFAULT_BASE
  parser = build_parser()
  args = parser.parse_args(argv)
  if getattr(args, "url", None):
    DEFAULT_BASE = str(args.url).rstrip("/")
  func = getattr(args, "func", None)
  if not func:
    parser.print_help()
    return 0
  return int(func(args))


if __name__ == "__main__":
  raise SystemExit(main())
