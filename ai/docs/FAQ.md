# 常见问题（FAQ）

## OP 和 op助手是什么关系？

对外产品名 **OP Agent**，CLI 命令 **`op`**。Web 中文界面可显示「OP 助手」。代码目录仍为 `ai/`。

## 需要会编程吗？

不需要。面向普通车主：用中文描述感受即可。开发者可用终端、PR 发布、技能编写等高级能力。

## op 和 Hermes CLI 一样吗？

心智模型类似：终端里敲 `op`，自然语言等价 `op chat`。OP 深度集成 openpilot（Params、路线、TSK），不是通用 Agent OS。

## 数据会上传到哪里？

对话走你配置的模型 API。路线/参数读取在本地设备。详见各服务商隐私政策。

## 能自动改参数吗？

不会未经确认修改。必须 Web 确认卡或终端 `y`。

## 如何从 GitHub 安装？

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
```

## Wiki 在哪？

https://github.com/mouxangithub/ai/wiki — 源稿在 `docs/wiki/`，见 [WIKI.md](WIKI.md)。

## 如何反馈 Bug？

https://github.com/mouxangithub/ai/issues/new/choose

## 车机存储会丢吗？

见 [INSTALL.md](INSTALL.md) 用户数据持久化章节。
