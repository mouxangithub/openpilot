# Konik vs Comma Connect

帮助用户在 **Konik** 与 **Comma Connect** 之间选型与配对。

## 何时触发

- 「不用 comma 云」「Konik 怎么配」「connect 替代」
- 路线不上传 comma、要自建云

## 对比要点

| 维度 | Comma Connect | Konik |
|------|---------------|-------|
| 配对 | `comma_auth_status` | `konik_connect_status` |
| 路线云 | `list_comma_routes` | Konik 控制台 |
| 设备密钥 | 出厂 DongleId | 克隆机需 `konik_generate_device_keys` |
| 一条龙 | — | `konik_connect_pipeline(confirm=true)` |

## 推荐顺序

1. `konik_connect_status` + `comma_auth_status`
2. `network_diagnostics`
3. 选 Konik → workflow `cloud_connect_compare` 或 `konik_connect_pipeline`
4. 仍用 comma 路线 → 保持 Comma 登录

## 相关技能

- `konik-connect`
- `network-diagnostics`
