# 快速上手（Quick Start）

与 Wiki [Quick-Start](wiki/Quick-Start.md) 同步。5 分钟完成首次配置并开始使用 OP Agent。

## 安装

见 [INSTALL.md](INSTALL.md)。

## 配置 API

1. 浏览器打开 `http://<设备IP>:5090`
2. 首次向导：选择服务商、填写 API Key、选模型
3. 可选：车型、主要诉求（调优 / Engage / 适配 / 复盘）

## 车主四大入口

| 场景 | Web | CLI |
|------|-----|-----|
| 调手感 | 首屏「调驾驶手感」/ `/调手感` | `op tune` |
| 适配新车 | 「适配新车」/ `/适配新车` | `op adapt` |
| 开不起来 | 「开不起来排查」/ `/开不起来` | `op doctor` |
| 复盘 | 「复盘上一趟」/ `/复盘` | `op review` |

## 改参确认

AI 修改驾驶设置前会显示**通俗中文对比**，静止状态下确认后才会写入。终端里输入 `y`/`n`。

## CLI

```bash
op status
op chat "跟车太近"
```

详见 [CLI.md](CLI.md)、[TERMINAL.md](TERMINAL.md)。

## 产品定位

[PRODUCT.md](PRODUCT.md)
