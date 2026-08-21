# OP CLI

命令名：**`op`**（不是 `op-agent`）

## 环境

```bash
export OP_AGENT_URL=http://127.0.0.1:5090   # 默认
export OPENPILOT_ROOT=/data/openpilot
```

安装后：`$OPENPILOT_ROOT/op` 或 `python3 -m ai.cli`

## 命令一览

| 命令 | 说明 |
|------|------|
| `op status` | 服务与 AI 配置状态 |
| `op chat "问题"` | 对话（流式输出） |
| `op tune` | 调驾驶手感向导 |
| `op doctor` | 开不起来排查 |
| `op adapt` | 适配新车 |
| `op wizards` | 列出车主向导 |
| `op backup export -o x.json` | 平台备份 |
| `op backup restore -f x.json` | 恢复备份 |
| `op config` | 查看 AI 配置 |

## 示例

```bash
op status
op chat "帮我看看最近一趟有没有异常退出"
op tune
op doctor
ssh comma 'op chat "无法 engage，仪表没有图标"'
```

## 与 Web 终端

Web 终端（xterm）中可直接敲 `op` 子命令；自然语言输入等价 `op chat`（车主模式）。

详见 [Web-Terminal](Web-Terminal)。

## 开发者

实现：`ai/cli/main.py`、`ai/cli/runner.py`  
仓库文档：[CLI.md](https://github.com/mouxangithub/ai/blob/main/docs/CLI.md)
