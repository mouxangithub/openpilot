# 功能与 API 概览

统一 Web：`http://<IP>:5090`

## 主要模块

| 模块 | 入口 | 后端位置 |
|------|------|----------|
| AI 聊天 | `/` | `server/handlers/chat_handlers.py` · `core/chat/runner.py` |
| 设置 | 侧栏 | `server/handlers/config_handlers.py` |
| 会话同步 | 自动 WS | `core/sync/hub.py` |
| TSK SecOC | `/?settings=secoc` | `services/tsk/routes.py` · `tsk/service.py` |
| Cabana | 顶栏闪电图标 | `services/cabana/` |
| Panda 刷机 | 快捷卡片 / API | `services/panda/routes.py` |
| 多 Agent | OP 办公室 | `agents/` · `GET/POST /api/ai/agents` |

## AI API（节选）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ai/bootstrap` | 首屏聚合（`?lite=1` 轻量） |
| GET | `/api/ai/status` | 行车状态、配置摘要 |
| GET/POST | `/api/ai/config` | 读写模型配置 |
| POST | `/api/ai/chat` | SSE 流式聊天 |
| GET/POST | `/api/ai/sessions` | 会话列表与保存 |
| GET | `/api/ai/sync/ws` | 会话/配置实时同步 |
| GET | `/api/ai/sync/schema` | WS 协议 schema |
| POST | `/api/ai/terminal/op` | Web 终端自然语言 |
| GET | `/api/ai/consumer/wizards` | 车主向导列表 |
| GET | `/api/ai/package/version` | 包版本 |
| POST | `/api/ai/package/update` | git 更新 + integrate |
| GET | `/api/ai/fork/detect` | 扫描 openpilot 树 |
| GET | `/api/ai/workspace` | 工作区文件 |
| GET | `/api/ai/toolsets` | 工具集元数据 |

完整路由：`server/routes/__init__.py`。

## Cabana API（节选）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/cabana/car` | 当前车型 / DBC 建议 |
| GET | `/api/cabana/dbcs` | DBC 列表 |
| GET | `/api/cabana/routes` | 本地路线列表 |
| GET | `/api/cabana/ws` | 实时 CAN |
| GET | `/api/cabana/offline/ws` | 回放 CAN |

## TSK API（节选）

| 方法 | 路径 |
|------|------|
| GET | `/api/tsk/health` |
| GET | `/api/tsk/summary` |
| POST | `/api/tsk/extract` |
| POST | `/api/tsk/install-key` |

完整说明见 [TSK_AND_AID.md](TSK_AND_AID.md)。

## Panda API

| 方法 | 路径 |
|------|------|
| GET | `/api/panda/status` |
| POST | `/api/panda/flash` |

## 常用 Param（`ai_*`）

| 键 | 说明 |
|----|------|
| `ai_provider` / `ai_model` / `ai_api_key` | 对话模型 |
| `ai_model_fast` / `ai_model_deep` / `ai_model_routing` | 多模型路由 |
| `ai_first_run_done` | 首次向导完成 |
| `ai_fork_id` | 最近一次 fork 分析 slug |
| `ai_timezone` | 路线/Cabana 时区（`infra/timezone.py`） |

完整列表：`common/params.py`。

## 车机自检

```bash
pgrep -af 'ai\.aid'
tail -20 /tmp/aid.log
curl -s http://127.0.0.1:5090/api/ai/status
```

## PC 开发

```bash
py -3 ai/dev/run_pc.py --port 5090
py -3 ai/scripts/verify_architecture.py
```

## 已知限制

- 行驶中：写 Param、shell、TSK 写操作受 `system/safety.py` 限制。
- PC：无 cereal 实时状态；无 `pycryptodome` 时 TSK 路由跳过；Windows 无时区库时 Cabana 路线时间使用 UTC+8 固定偏移。
- Cabana 离线视频：优先 `qcamera.ts`；HEVC 浏览器常无法直播。

更完整的能力矩阵见 [AI_AGENT_ROADMAP.md](AI_AGENT_ROADMAP.md)。
