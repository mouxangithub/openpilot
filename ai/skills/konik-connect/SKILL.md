# Konik Connect — 替换 Comma Connect 云配对

本 fork 已内置 **Konik** 后端（`launch_openpilot.sh` 导出 `API_HOST` / `ATHENA_HOST`），无需自部署 connect-killer 服务端。配对站在 **https://stable.konik.ai**（不是 comma connect）。

## 推荐：一条龙（停车 offroad）

对 op 助手说：**「帮我 Konik 一条龙配对」**

```
konik_connect_pipeline(confirm=true)
```

克隆机强制换新密钥：

```
konik_connect_pipeline(confirm=true, regenerate_keys=true)
```

PC 经 SSH 操作车机时加 `device_ip`。

流水线顺序：

1. 生成 `/persist/comma` RSA 密钥（缺密钥或 `regenerate_keys=true` 时执行 `1.sh`）
2. 删除旧 `DongleId`（`/data/params/d/DongleId` + `/persist/comma/dongle_id`）
3. 调用 `system/athena/registration.py` 的 `register()` → 向 `api.konik.ai` 领取新 DongleId
4. 提示打开 **https://stable.konik.ai** 扫码绑定账号

> manager 启动时也会自动 `register()`；一条龙是为**不重启 manager** 或需要 AI 引导时准备的。

## 分步执行

| 步骤 | 工具 | 说明 |
|------|------|------|
| 0 | `konik_connect_status` | 查看 SSH / 密钥 / DongleId / 注册进度 |
| 1 | SSH（PC） | `ssh comma@<IP>` 或 `network_diagnostics(device_ip=...)` |
| 2 | `konik_generate_device_keys(confirm=true)` | 克隆机必做；等价 `bash 1.sh` |
| 3 | `konik_reset_dongle_id(confirm=true)` | 清除旧 comma connect 身份 |
| 4 | `konik_register_device(confirm=true)` | 等价 `python3.12 system/athena/registration.py` |
| 5 | 用户扫码 | **https://stable.konik.ai** |
| 6 | `manager_control(action=restart)` | 可选，使 athena 用新 DongleId 上线 |

## 安全与隐私

- 写操作仅在 **offroad**；行驶中只读 `konik_connect_status`
- **禁止**在对话中复述完整私钥或 PEM 公钥
- 可展示公钥指纹、DongleId、配对链接

## 常见问题

- **克隆机未换密钥** → 先 `regenerate_keys=true` 再清 DongleId
- **注册返回 UnregisteredDevice** → 检查 WiFi、`API_HOST=https://api.konik.ai`、公钥是否存在
- **已注册但网页未绑定** → 打开 stable.konik.ai 扫码；与 API 注册是两步
- **PC 操作** → 所有写工具支持 `device_ip`
