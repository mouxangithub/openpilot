# OP CLI 参考

命令名：**`op`**（`python3 -m ai.cli` 或 `$OPENPILOT_ROOT/op`）

## 环境变量

| 变量 | 说明 |
|------|------|
| `OP_AGENT_URL` / `OP_URL` | Agent 服务地址，默认 `http://127.0.0.1:5090` |
| `OPENPILOT_ROOT` | openpilot 根目录 |
| `PYTHONPATH` | 需包含 `$OPENPILOT_ROOT` |

## 子命令

```
op status              # 服务与配置
op wizards             # 车主向导列表
op chat [-w WORKFLOW] [--consumer] "消息"
op doctor [消息]       # = engage 排查向导
op tune [消息]         # 调手感
op adapt [消息]        # 适配新车
op wizard <id> [消息]
op backup export [-o file]
op backup restore -f file [--mode merge|replace]
op config [--json]
```

## 实现

- `ai/cli/main.py` — 参数解析  
- `ai/cli/runner.py` — 与终端共用的流式请求体  

终端 SSE：`POST /api/ai/terminal/op`（与 `op chat` 同一引擎）

## Wiki

[OP-CLI](wiki/OP-CLI.md)
