# 排障指南

## 服务与网络

| 现象 | 处理 |
|------|------|
| 网页打不开 | 确认 `python3 -m ai.aid`；检查 5090 端口 |
| `op status` 连不上 | 设置 `OP_AGENT_URL`；确认 aid 监听 0.0.0.0 |
| API 报错 | 设置页测试连接；检查 Key 与模型名 |

## 驾驶相关

| 现象 | 处理 |
|------|------|
| 无法 Engage | `op doctor` 或 Web「开不起来排查」 |
| 改参后变差 | 「撤销上次调参」；调参护照恢复快照 |
| 行驶中不能改参 | 正常安全限制；停车后再确认写入 |

## 终端

| 现象 | 处理 |
|------|------|
| Windows 无 PTY | 用 WSL 或 Web 聊天；见 [TERMINAL.md](TERMINAL.md) |
| 找不到 `op` | 重装 install.sh；`PATH` 含 `$OPENPILOT_ROOT/op` |
| 自然语言无响应 | 确认 AI 已配置；`?` 触发帮助 |

## 提交 Bug

[GitHub Issue — OP Agent Bug](https://github.com/mouxangithub/ai/issues/new?template=op_bug.yml)

附：`op status` 输出、版本号、车型。

## 更多

- [FAQ.md](FAQ.md)
- Wiki [Troubleshooting](wiki/Troubleshooting.md)
