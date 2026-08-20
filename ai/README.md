# op助手（openpilot AI Agent）

面向 **comma 设备上各类 openpilot fork** 的通用 AI 助手：聊天调参、路线诊断、车辆适配、TSK SecOC、Cabana CAN 分析、社区 Wiki 知识库。

| 项目 | 说明 |
|------|------|
| 安装位置 | `<openpilot>/ai`（车机默认 `/data/openpilot/ai`） |
| Web 入口 | `http://<设备IP>:5090` |
| 配置 | 车机 `/data/ai/config.json`（无需编译 `params_keys.h`） |
| 进程入口 | `python3 -m ai.aid`（唯一根目录 Python 入口：`aid.py`） |
| 集成 | 已内置于本仓库；`launch_chffrplus.sh` 自动启动 `aid` |

## 系统架构（2026-08）

```
aid.py                    # 唯一进程入口
server/                   # HTTP / WebSocket 传输层
  app_factory.py          # 应用工厂、启动任务
  handlers/               # REST 按域拆分（chat / config / sessions / rag …）
  routes/                 # 路由注册
core/                     # 平台内核（不依赖 HTTP）
  llm/                    # 模型路由、Embedding、用量
  chat/                   # 对话 runner、jobs、压缩、命令队列
  sync/                   # 会话 WS 同步、设备信任
  workspace/              # 人设与工作区
  runtime/                # 心跳、进化管线、sidecar
services/                 # 垂直业务能力
  cabana/                 # CAN 实时/回放（dbc、replay、handlers）
  tsk/                    # SecOC API
  panda/                  # Panda 刷机
  rag/                    # 内置知识 JSON 加载
infra/                    # 路径、时区、鉴权、版本
tools/                    # LLM 工具
  registry.py / executor.py
  domains/                # core · tune · vehicle · can · secoc · devops · cloud · media · platform
web/static/js/
  app/                    # globals · dom · registry
  chat/                   # model-tag 等
data/rag/builtin/         # 可选静态内置知识 JSON
```

**依赖规则**：`server` → `services` / `core` → `infra`；`core` 不 import `server`。  
详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 与 [docs/ARCHITECTURE_TARGETS.md](docs/ARCHITECTURE_TARGETS.md)。

## 核心能力

- **通用 fork 感知** — 安装时扫描 `git remote`、目录与 Param 前缀，匹配 Dragonpilot / sunnypilot / FrogPilot 等（`fork/community_registry.json`）
- **安装即学习** — 写入 `ai_install_snapshot.json` 与 `workspace/FORK_PROFILE.md`；对话自动注入 fork/设备上下文
- **社区 Wiki → RAG** — 从 GitHub、Discourse、MediaWiki 拉取文档入库
- **健康检查与分诊** — Engage、SecOC、Panda、指纹一键排查
- **Cabana 面板** — Web 内实时/回放 CAN 解码与导出
- **多 Agent 编排** — 主调度 + 预制专员（tune / route / adapt / secoc …）
- **技能与插件** — 可扩展工具链（TSK、Sunnylink、GitHub CI 等）

## 快速开始

**车机（SSH）：**

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
```

**PC 开发预览：**

```bash
cd /path/to/openpilot
py -3 ai/dev/run_pc.py --port 5090
# 浏览器 http://127.0.0.1:5090
```

PC 模式使用 Mock Params、无 cereal 实时状态；配置 API Key 后可测试聊天与设置。详见 [dev/README.md](dev/README.md)。

**车机手动启动：**

```bash
export OPENPILOT_ROOT=/data/openpilot
cd "$OPENPILOT_ROOT" && python3 -m ai.aid
```

打开 `http://<IP>:5090` 完成首次向导（模型 API、车型等）。

## 常用命令

```bash
# 手动触发 fork 快照 + Wiki 同步
PYTHONPATH=$OPENPILOT_ROOT python3 -c "
from ai.fork.post_install import run_post_install_learn
print(run_post_install_learn())
"

# 强制重新拉取社区 Wiki
curl -X POST http://127.0.0.1:5090/api/ai/rag \
  -H 'Content-Type: application/json' \
  -d '{"operation":"wiki_ingest","force":true}'

# 架构 import 门禁（PC 自动装 mock）
py -3 ai/scripts/verify_architecture.py
```

## 文档

| 文档 | 说明 |
|------|------|
| [docs/README.md](docs/README.md) | **文档总索引** |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 分层架构、模块职责、前端结构 |
| [docs/ARCHITECTURE_TARGETS.md](docs/ARCHITECTURE_TARGETS.md) | 迁移状态与脚本清单 |
| [docs/INSTALL.md](docs/INSTALL.md) | 安装、集成、更新、卸载 |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | 首次配置、快捷卡片 |
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | Web 功能与 API 端点 |
| [docs/FORK_AND_COMMUNITY.md](docs/FORK_AND_COMMUNITY.md) | 多社区 fork、Wiki RAG |
| [docs/CAPABILITIES.md](docs/CAPABILITIES.md) | 用户向能力速查 |
| [docs/FAQ.md](docs/FAQ.md) | 常见问题 |
| [dev/README.md](dev/README.md) | PC 预览、测试 |

**卸载：** `bash ai/install/uninstall.sh` — 见 [INSTALL.md#卸载](docs/INSTALL.md)。

## 设备支持

| 设备 | 说明 |
|------|------|
| C2 | comma two（Android）；部分 TSK/C3 工具不适用 |
| C3 / C3X / C4 | AGNOS + pandad；完整工具链 |
| PC | 开发与回放（`ai/dev/run_pc.py`） |

详见 [docs/COMMA_DEVICES.md](docs/COMMA_DEVICES.md)。

## 仓库

- op助手：https://github.com/mouxangithub/ai
