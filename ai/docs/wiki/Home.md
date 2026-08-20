# OP Agent Wiki

> 本页为 GitHub Wiki 首页源稿。在线阅读：
> - **Pages**：https://mouxangithub.github.io/ai/
> - **Wiki**：https://github.com/mouxangithub/ai/wiki
> - 同步说明见 [WIKI.md](../WIKI.md)

**OP Agent**（命令行：`op`）是 openpilot 的 AI 助手，帮助普通车主用自然语言完成**调优、新车适配、排障**，无需记参数名。

## 快速链接

| 页面 | 说明 |
|------|------|
| [Quick-Start](Quick-Start) | 5 分钟上手 |
| [OP-CLI](OP-CLI) | `op` 命令行完整参考 |
| [Web-Terminal](Web-Terminal) | 浏览器终端 + Hermes 风格 CLI |
| [Tuning-for-Owners](Tuning-for-Owners) | 车主调参指南 |
| [Troubleshooting](Troubleshooting) | 常见问题 |
| [Vehicle-Adaptation](Vehicle-Adaptation) | 新车适配入门 |
| [Daily-Memory](Daily-Memory) | 每日记忆 Wiki 页（AI 自读） |
| [GEPA-Evolution](GEPA-Evolution) | 技能自进化与 Golden 评测集 |

## 三种入口

1. **Web UI** — 车机/PC 浏览器 `:5090`，首屏四大向导按钮  
2. **`op` CLI** — SSH 或 Web 终端里直接敲 `op tune`  
3. **自然语言** — Web 聊天或终端输入中文，`?` 等价 `op chat`

## 安装

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
cd /data/openpilot && python3 -m ai.aid
```

详见仓库 [INSTALL.md](https://github.com/mouxangithub/ai/blob/main/docs/INSTALL.md)。

## 反馈

- [Bug / 功能 Issue](https://github.com/mouxangithub/ai/issues/new/choose)  
- [Discussions](https://github.com/mouxangithub/ai/discussions)

## 仓库文档

完整开发者文档：[docs/README.md](https://github.com/mouxangithub/ai/blob/main/docs/README.md)
