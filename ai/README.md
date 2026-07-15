# op助手（Openpilot AI Agent）

专为 **openpilot 及任意社区 fork** 设计的 AI 助手：聊天调参、路线诊断、车辆适配、TSK SecOC、Cabana CAN 分析。

| 项目 | 说明 |
|------|------|
| 独立仓库 | https://github.com/mouxangithub/ai |
| 安装位置 | `<openpilot>/ai`（车机默认 `/data/openpilot/ai`） |
| Web 入口 | `http://<设备IP>:5090` |
| 一键安装 | 见 [docs/INSTALL.md](docs/INSTALL.md) |

## 快速开始

**车机（SSH）：**

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
```

**PC：**

```bash
export OPENPILOT_ROOT=/path/to/openpilot
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
cd "$OPENPILOT_ROOT" && python3 -m ai.aid
```

安装脚本会自动：克隆/更新 `ai/` → **改写** `params_keys.h` 与 `launch_chffrplus.sh` → 编译 `params_pyx.so`。

**卸载：** `bash ai/install/uninstall.sh` 或见 [docs/INSTALL.md](docs/INSTALL.md#卸载)。

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/README.md](docs/README.md) | 文档总览 |
| [docs/INSTALL.md](docs/INSTALL.md) | 安装、更新、集成 openpilot |
| [docs/TSK_AND_AID.md](docs/TSK_AND_AID.md) | TSK SecOC 与 aid 架构 |
| [docs/COMMA_DEVICES.md](docs/COMMA_DEVICES.md) | C3 / C3X / C4 与 Panda 栈 |
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | 功能与 API 概览 |

## 致谢与来源

- **TSK Web（丰田 SecOC 管理界面）** 功能源自社区项目 [**optskug/openpilot**](https://github.com/optskug/openpilot)，已集成到本仓库 `ai/tsk/` 与 `:5090` Web UI（设置 → SecOC）。
- op助手本体由 [mouxangithub/ai](https://github.com/mouxangithub/ai) 独立分发，可安装到任意 openpilot fork。

## Fork 适配说明

**不维护固定 fork 白名单。** 开发面板 → **Fork 分析** 会扫描当前 openpilot 树（git remote、README、特征目录、`params_keys.h`、各 fork 的 `settings/ITEMS` 等）；配置模型后可让 **AI 阅读整个项目** 生成分析与技能草稿（`ai/data/fork_analysis/`、`ai/data/fork_drafts/`，需人工审核）。

## 许可

与所在 openpilot fork 的许可证保持一致；TSK 相关代码请同时遵守 optskug/openpilot 社区许可与署名惯例。
