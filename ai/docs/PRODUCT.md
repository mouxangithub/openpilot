# OP Agent 产品定位

## 一句话

**OP**（OP Agent）让不懂编程、不懂汽修的普通车主，也能用自然语言完成 openpilot 的调优、新车适配和排障——像跟懂车的朋友聊天，而不是记参数名。

## 为谁服务

| 用户 | 典型诉求 |
|------|----------|
| 日常车主 | 跟车距离、变道风格、加减速舒适度 |
| 新车车主 | 能不能用、怎么适配、指纹/CAN |
| 遇到问题的车主 | 开不起来、突然退出、上次改完变差了 |

## 入口

| 入口 | 说明 |
|------|------|
| **Web** | 车载/局域网 `:5090`，首屏四大快捷向导 |
| **CLI `op`** | `op chat` / `op tune` / `op doctor` / `op adapt` |
| **SSH** | `ssh comma` 后运行 `op`，适合远程诊断 |
| **终端 AI** | Web 终端 `?` 前缀或 `terminal-ai.js` |

环境变量：`OP_AGENT_URL` / `OP_URL`（默认 `http://127.0.0.1:5090`）

## 车主向能力（已实现）

- **consumer_lexicon**：参数 → 通俗中文标签
- **四大向导**：适配新车、调手感、开不起来、复盘上一趟
- **改参确认卡**：人类可读 diff，确认/取消，一键撤销提示
- **斜杠指令**：`/调手感`、`/适配新车`、`/开不起来`、`/复盘`
- **停车复盘**：调度器默认 `post_drive_review_offroad`
- **进化技能车主语言滤镜**：`filter_consumer_language`

## 我们刻意不做（当前阶段）

- 20+ 消息网关（Telegram/Discord 等）—— 车载 Web + `op` CLI 优先
- 自动未经确认写参数 —— 必须用户确认
- 替代专业汽修诊断仪 —— 辅助 openpilot 生态，不包修整车

## 与 Hermes 的差异

Hermes 是通用 Agent OS；**OP 是 openpilot 垂直助手**，深度集成 Params、路线、Cabana、TSK、调参护照与车机状态，面向「开车的人」而非「写代码的人」。

## 相关文档

- [HERMES_EVOLUTION.md](./HERMES_EVOLUTION.md) — 技能进化闭环
- [VEHICLE_ADAPTATION_GUIDE.md](./VEHICLE_ADAPTATION_GUIDE.md) — 新车适配
- [ARCHITECTURE.md](./ARCHITECTURE.md) — 技术架构
