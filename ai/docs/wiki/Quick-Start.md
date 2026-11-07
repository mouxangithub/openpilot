# Quick Start

## 1. 安装并启动

```bash
# 车机（已有 /data/openpilot）
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
cd /data/openpilot && python3 -m ai.aid
```

浏览器打开：`http://<设备IP>:5090`

## 2. 首次配置

1. 按向导填写 **API Key** 与模型  
2. 可选：填写车型、勾选诉求（调优 / Engage / 适配 / 复盘）  
3. 完成知识库索引（可跳过）

## 3. 车主最常用四件事

| 按钮 / 命令 | 做什么 |
|-------------|--------|
| 调驾驶手感 / `op tune` | 跟车、变道、加减速舒适度 |
| 适配新车 / `op adapt` | 认车、指纹、CAN 草稿 |
| 开不起来 / `op doctor` | 无法 Engage 排查 |
| 复盘上一趟 / `op review` | 停车后路线总结 |

Web 聊天也可输入：`/调手感`、`/适配新车`、`/开不起来`、`/复盘`

## 4. 改设置前会确认

AI 提议改参数时，会显示**通俗中文对比**（改前 → 改后），需点「确认应用」或终端输入 `y`。

不满意可说「撤销上次调参」或 Web 调参护照里恢复快照。

## 5. SSH 用法

```bash
ssh comma
op status
op chat "跟车太近怎么办"
```

## 下一步

- [OP-CLI](OP-CLI)  
- [Tuning-for-Owners](Tuning-for-Owners)  
- [Troubleshooting](Troubleshooting)
