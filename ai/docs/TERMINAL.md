# Web 终端

Hermes 风格：**Shell 跑真实 `op` CLI**，自然语言走 **`op chat` 引擎**。

## 架构

```
Web xterm
  ├─ PTY bash ──► op status / op tune / …
  └─ terminal-ai.js
        ├─ 自然语言 / ? / /ai ──► POST /api/ai/terminal/op (SSE)
        └─ 改参确认 ──► y/n ──► POST /api/ai/terminal/op/confirm
```

## 服务端

- `ai/server/terminal.py` — PTY WebSocket，PATH 注入 `op`  
- `ai/server/handlers/terminal_op.py` — OP 流式聊天  

## 前端

- `web/static/js/terminal-panel.js` — xterm 弹窗  
- `web/static/js/terminal-ai.js` — 路由与流式渲染  

## 用户提示

| 输入 | 行为 |
|------|------|
| `op …` | Shell 执行 CLI |
| `!ls` | 强制 Shell |
| 中文问句 | op chat（车主模式） |
| `?` | 帮助 |

## Wiki

[Web-Terminal](wiki/Web-Terminal.md)
