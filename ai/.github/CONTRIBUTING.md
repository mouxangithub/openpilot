# Contributing to OP Agent

感谢参与 [mouxangithub/ai](https://github.com/mouxangithub/ai)（OP Agent / op助手）！

## 产品定位

请先阅读 [docs/PRODUCT.md](../docs/PRODUCT.md)：我们优先服务**不懂编程的普通车主**，CLI 命令为 **`op`**。

## 开发环境

```bash
export OPENPILOT_ROOT=/path/to/openpilot
cd $OPENPILOT_ROOT && python3 -m ai.aid
```

PC 测试：`http://127.0.0.1:5090`

## 提交 Issue

使用 [Issue 模板](https://github.com/mouxangithub/ai/issues/new/choose)：

| 模板 | 用途 |
|------|------|
| OP Agent Bug | Web / CLI / 终端缺陷 |
| 功能建议 | 新能力 |
| 调参 / 驾驶手感 | 车主调优 |
| 新车适配 | 指纹 / CAN |
| 文档改进 | docs / Wiki |

## 提交 PR

1. Fork → 分支 `ai/your-feature`
2. 填写 [PR 模板](pull_request_template.md)
3. 确保 CI 通过（`ai/.github/workflows/tests.yml`）
4. 车机相关改动注明测试设备（C2/C3/C4/PC）

## 文档与 Wiki

- 仓库文档：`docs/`（见 [docs/README.md](../docs/README.md)）
- GitHub Wiki 源稿：`docs/wiki/`（见 [docs/WIKI.md](../docs/WIKI.md) 同步说明）

## 代码约定

- 车主可见文案：通俗中文，参数改动走确认流
- CLI 入口统一 `op`，勿新增 `op-agent` 命令名
- 最小 diff，匹配现有 `ai/` 风格
