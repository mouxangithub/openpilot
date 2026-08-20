# 显示与设备设置

## 显示

`get_display_settings` / `set_display_settings`

键：`OnroadScreenOffBrightness`、`OnroadScreenOffTimer`、`InteractivityTimeout`、`Brightness`

无屏设备：原生 `ui` 不运行，亮度/熄屏请引导用户用 **WebUI → Display** 或 Param；见 `WebuiHeadlessMode` 与技能 `headless-webui`。

## 设备 / 开发者

`get_device_settings` / `set_device_settings`

键：`MaxTimeOffroad`、`DeviceBootMode`、`QuietMode`、`QuickBootToggle`、`EnableGithubRunner`、`EnableCopyparty`

### GitHub Runner Service

`EnableGithubRunner` 仅 **允许** manager 在离路时启停 systemd Runner，**不是**安装开关。

- 需先打开 **显示高级控制项**（`ShowAdvancedControls`）
- 非 release 分支才显示 Runner 开关
- 完整安装/CI/prebuilt 流程见技能 **`github-runner`** 与 `ai/docs/GITHUB_RUNNER.md`
- 诊断：`github_runner_status`、`github_runner_recovery_hint`

## Lite 蜂鸣

`get_sp_device_hw`、`set_sp_dev_beep`
