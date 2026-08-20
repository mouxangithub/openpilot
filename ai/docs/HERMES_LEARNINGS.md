# Hermes Agent 借鉴笔记（op助手）

参考：[hermes-agent](https://github.com/NousResearch/hermes-agent) · [Web Dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)

## 已落地

| Hermes 能力 | op助手 实现 | 说明 |
|-------------|-------------|------|
| Web 终端（xterm + PTY WS + AI 路由） | `server/terminal.py` + `terminal-panel.js` + `terminal-ai.js` | 自然语言/`?` 在 xterm 内联流式回复；`!` 强制 Shell；AI 期间 mute PTY |
| **Sidecar 工具事件** | `sidecar_hub.py` + `terminal-sidecar.js` | `/api/ai/sidecar/ws`，终端旁 live tool 列表 |
| **3D 动态办公室** | `office-scene.js` + `office-panel.js` | 等距场景：idle 喝咖啡/溜达/打盹，派活走向工位 |
| 结构化 + 终端双轨 | 聊天 Web UI + 终端面板 | Hermes Chat = TUI + JSON sidecar；我们 = 聊天 + 终端侧栏 |
| 会话/job 持久 | `chat_jobs` + SessionStore | 刷新可恢复后台 job |
| Sync WS v2 | `web-sync-ws.js` + `sync_protocol.py` | connect 握手，ai.js 经 SyncWsClient 统一连接 |

## Hermes Web Dashboard 核心设计

1. **Chat 页嵌入真实 TUI**：POSIX PTY + xterm.js 渲染 ANSI。
2. **`/api/pty` WebSocket**：双向字节流；resize 用 `\x1b[RESIZE:cols;rows]`。
3. **Sidecar 事件通道**：并行 JSON 事件，终端旁显示 tool-call 列表 — **已实现**。
4. **Dashboard 配置**：API Key、模型、skills — 对应设置侧栏 + bootstrap。

## 行驶中终端策略

1. 顶部栏点击 **终端** 图标
2. 需要 **AGNOS/Linux**（车载设备或 Linux 开发机）
3. **行驶中可用** — 仅诊断；`assert_shell_safe` 拦截控车命令
4. 与 AI `run_shell_command` 工具互补：终端给人用，工具给 Agent 用

## 刻意不照搬

- **完整 Hermes TUI in browser**：主界面是 Web 聊天，不是 Ink TUI 克隆
- **Claw3D 全量 Next.js 栈**：车载/C3 用轻量 Canvas 等距引擎；桌面可后续接 [Claw3D](https://github.com/fathah/hermes-office) 真 3D
- **Node.js TUI 依赖**：直接用 bash PTY
- **Nous Portal OAuth**：无公网 Dashboard 需求
- **PTY 内逐字节命令过滤**：交互式 shell 靠启动提示 + 工具层 `assert_shell_safe`；完整 PTY 过滤成本高
