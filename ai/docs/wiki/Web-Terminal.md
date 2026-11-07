# Web Terminal

OP Web 终端 = **真 Shell（PTY）** + **Hermes 风格 `op` CLI** + **自然语言 → op chat**。

## 打开方式

Web UI → 终端按钮（xterm 弹窗）

## Shell 模式

直接输入 shell 命令。`op` 已在 PATH：

```bash
op status
op tune
ls ai/
```

欢迎语会提示常用 `op` 命令。

## AI 模式（无需记 op）

以下输入会走 **`op chat` 同款引擎**（`/api/ai/terminal/op`）：

- 中文自然语言：「跟车太近」
- `? 无法 engage`
- `/ai 帮我复盘`

**不会**拦截以 `op` 开头的行（交给 Shell 执行真实 CLI）。

| 前缀 | 行为 |
|------|------|
| `!command` | 强制 Shell |
| `op …` | Shell 执行 op CLI |
| 其他自然语言 | op chat（车主模式） |

## 改参确认

终端里若 AI 要改设置，会打印通俗 diff，输入 **`y`** 确认、**`n`** 取消。

## 限制

- PTY 需 Linux/macOS（AGNOS）；Windows 开发请用 WSL 或纯 AI 模式  
- 行驶中禁止控车指令；诊断只读工具可用  

## 相关

- [OP-CLI](OP-CLI)  
- 仓库 [TERMINAL.md](https://github.com/mouxangithub/ai/blob/main/docs/TERMINAL.md)
