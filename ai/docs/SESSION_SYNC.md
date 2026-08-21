# 会话同步机制（Gateway 服务端优先）

## OpenClaw Gateway 模式

1. **Gateway 为唯一真相源**：会话存在服务端，浏览器不做主存储
2. **任意设备连 WS**：`connect` → `connect_ack` → `hello` 全量快照
3. **实时 event**：`sessions` / `config` / `chat_event` / `chat_status` 广播
4. **stateVersion**：单调递增，客户端内存跟踪，新 Tab 以服务端为准

## op助手 实现（已对齐）

| 能力 | 实现 |
|------|------|
| Gateway | `core/sync/hub.py` — `/api/ai/sync/ws` |
| 服务端存储 | `tools/domains/platform/session_store.py` — Params `ai_web_sessions` + `stateVersion` |
| 客户端会话 | `SessionStore` **仅内存**，不写 localStorage |
| WS hello 全量 | `connect` → `hello`（sessions + config + activeJobs） |
| 实时推送 | POST sessions → `broadcast_sessions`；config 保存 → `broadcast_config` |
| 冲突策略 | `SessionSync.shouldTakeRemoteAuthoritative` — 服务端 stateVersion 更新即整包采用 |
| 流式跨设备 | `chat_event` / `chat_status` → `ChatJobs.handleSyncWsEvent` |
| 遗留迁移 | 首次启动若服务端空、浏览器有旧 localStorage → 一次性 POST 后清除 |

## 数据流

```
设备 A 发消息
  → SessionStore（内存）
  → debounce 400ms POST /api/ai/sessions
  → Params + stateVersion++
  → WS broadcast { type: sessions }

设备 B 打开页面
  → SessionStore.init()（空）
  → WS connect → hello
  → applyRemoteSessionsData（服务端优先）
  → 渲染会话

设备 B 观看 A 流式输出
  → chat_event 实时 UI 更新
```

## 客户端仍用 localStorage 的部分（非真相源）

- `theme.js` / `i18n.js`：主题与语言偏好
- `command-queue.js`：队列模式 UI 偏好
- `device-trust.js`：设备指纹
- `local-prefs.js`：工具开关偏好；**配置草稿**用 sessionStorage

## 与 OpenClaw 的差异

1. **无独立 Gateway 进程**：真相源是车机 Params（一车一 aid）
2. **LAN 同步**：连同一台 aid 的任意设备可实时同步
3. **多车机不互通**：不像云端 Gateway 跨实例

## 开发预览

```bash
py -3 ai/dev/run_pc.py
# 多 Tab 打开 http://127.0.0.1:5090/ 可测 WS 同步
```
