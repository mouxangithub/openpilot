# 功能与 API 概览

统一 Web：`http://<IP>:5090`

## 主要模块

| 模块 | 入口 | 说明 |
|------|------|------|
| AI 聊天 | `/` | 流式对话、工具调用、多模型路由 |
| 设置 | 侧栏 | 模型、定时任务、知识库、开发面板 |
| TSK SecOC | `/?settings=secoc` | 丰田密钥安装 / 提取 / CAN·DataFlash |
| Cabana | 顶栏闪电图标 | 实时/回放 CAN、DBC、曲线、视频 |

## AI API（节选）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ai/bootstrap` | 首屏聚合数据 |
| GET/POST | `/api/ai/config` | 读写模型配置 |
| POST | `/api/ai/chat` | SSE 流式聊天 |
| GET | `/api/ai/package/version` | op助手 包版本 |
| POST | `/api/ai/package/update` | git 更新 + integrate |
| GET | `/api/ai/fork/detect` | 扫描 openpilot 树 |
| POST | `/api/ai/fork/analyze` | AI 分析 fork |
| POST | `/api/ai/fork/sync` | 生成技能/文档草稿 |

## TSK API（节选）

| 方法 | 路径 |
|------|------|
| GET | `/api/tsk/health` |
| GET | `/api/tsk/summary` |
| POST | `/api/tsk/extract` |
| POST | `/api/tsk/install-key` |

完整路由见 [TSK_AND_AID.md](TSK_AND_AID.md)。

## 常用 Param（`ai_*`）

| 键 | 说明 |
|----|------|
| `ai_provider` / `ai_model` / `ai_api_key` | 对话模型 |
| `ai_model_fast` / `ai_model_deep` / `ai_model_routing` | 多模型路由 |
| `ai_first_run_done` | 首次向导完成 |
| `ai_fork_id` | 最近一次 fork 分析 slug |
| `ai_timezone` | 路线/Cabana 时区 |

完整列表：`ai/common/params.py`。

## 车机自检

```bash
pgrep -af 'ai\.aid'
tail -20 /tmp/aid.log
curl -s http://127.0.0.1:5090/api/ai/status
```

## 已知限制

- 行驶中：写 Param、shell、TSK 写操作受 `safety.py` 限制（开放模式 `ai_admin_mode=1` 仍禁止直接控车）。
- Cabana 离线视频：优先 `qcamera.ts`；HEVC 浏览器常无法直播。
- C3/C3X/C4 部分新工具链需实机回归。

更完整的能力矩阵见 [AI_AGENT_ROADMAP.md](AI_AGENT_ROADMAP.md)。
