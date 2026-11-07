# C3 Lite 硬件

适用于 **comma three Lite**（无功放/无麦克风）的 op助手排查与 `SpDevBeep`。

## 何时触发

- 用户提到 Lite、无声音反馈、蜂鸣、DevUI
- `get_sp_device_hw` 显示 LITE 变体

## 推荐顺序

1. `get_sp_device_hw` — Lite 变体、`SpDevBeep`
2. `set_sp_dev_beep` — GPIO 蜂鸣反馈（confirm=true）
3. `get_display_settings` / `get_device_settings` — 亮度、开发者项
4. 无麦克风：勿依赖语音输入；用 `post_drive_voice_summary(speak=false)` 文字简报

## 与标准 C3 差异

- 进程：`beepd`（Lite）vs 标准音频路径
- 调参/Engage 流程与标准 C3 相同；Panda/Runner 见 `c3-dos-panda`、`github-runner`

## 相关技能

- `sp-device-lite`
- `engage-troubleshooting`
- `diagnostics`
