# Dragonpilot Dashy 与设置源

本 fork 的调优 UI 与参数真相来源：

1. **`dragonpilot/settings/*.py`** — 定义可调项（title、description、brand 过滤）
2. **Params `dp_*`** — 运行时存储
3. **Dashy**（`:5088`，Param `dp_dev_dashy`）— Web 调优面板，镜像多数开关

## AI 推荐工作流

1. `list_dp_settings` — 列出当前品牌可见项 + 当前值（**优先于**死记 Param 名）
2. `read_params` — 核对具体 key
3. `get_params_catalog` — 确认写入等级
4. 静止时 `write_params` 或 `apply_tune_preset`（需用户确认）

## Dashy API（设备在线时）

- `GET http://127.0.0.1:5088/api/settings` — 设置树
- 写操作走 Dashy 白名单；**op助手** 直接写 Params，不必依赖 Dashy 进程

## 与 CarrotPilot 的区别

| 概念 | CarrotPilot (CP) | Dragonpilot (本 fork) |
|------|------------------|------------------------|
| 调优入口 | Carrot 专有 Param / UI | `dp_*` + Dashy |
| 横向全速域 | Carrot MADS 等 | `dp_lat_alka` |
| 社区 fork | ajouatom / Carrot2 | dragonpilot |

用户说「CP 调优」时，先澄清是否指 **Carrot 另一台设备**；在本车一律用 `dp_*`。

## 模型与设备

- `dp_dev_model_selected` / `list_dp_settings` 中的模型项
- `select_driving_model` 工具：静止 + 确认后切换
- 改模型后建议 `restart_ui` 或 reengage
