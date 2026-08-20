# 无法开启 OP

顺序：`trip_review` → **Panda（C3 DOS）** → SecOC/指纹 → 摄像头/进程 → 车型

## 侧栏 NO PANDA / Panda 离线（C3 DOS）

1. `panda_status` — `pandaStates`、`usb_all`、`multi_panda`、`pandad_snapshot`
2. `list_all_pandas` — 双 USB（如内置 F4 + 外接红熊）时查 `heterogeneous_f4_h7`
3. `panda_recovery_hint` — 含 USBErrorBusy / 崩溃循环建议
4. `grep_log` — `pandad|panda|xhci|USBErrorBusy|DOS internal`
5. offroad：`tsk_restart_pandad(confirm=true)`
6. 双 Panda 崩溃 → `rebuild_pandad(confirm=true)` + `reboot_device`
7. 仍失败且为 F4 → 技能 **`c3-dos-panda`**：`flash_panda_firmware` 或 `recover_dos_panda(confirm=true, internal=true)` / `external=true`（外接黑熊）
8. **不适配 C3/DOS/黑熊**（缺 `panda.bin.signed`、`unknown HW`、双 Panda 指纹失败）→ `ai/docs/PANDA_C3_F4_PORTING.md`：三层合入 `panda@7d703710`、`sp@43d4f56f`、`opendbc@3244efe` → `scons` + 刷写
9. **刷写后 GUI 仍 Panda 否** → 重启 manager（pandad 被 kill 后 manager 不会自动重建子进程）

**禁忌**：F4 不要用 H7 固件；见 `ai/docs/PANDA_FLASH.md`。

## Lite C3（无功放）

若 `get_host_environment` / `get_sp_device_hw` 显示 `lite: true`（`device_type` 为 `tici`）：

1. **不要**依赖 `soundd` 或驾驶员监控（`dmonitoringd`）——Lite 上这些进程不启动。
2. 需要声音反馈时：`set_sp_dev_beep(true)`，确认 onroad 后 `beepd` 运行（`SpDevBeep=1`）。
3. **勿**写入 `RecordAudio`、`AlwaysOnDM`（`params_policy` 会拒绝）。
4. UI 设置列表中 `lite_unavailable` 项可忽略。

丰田/雷克萨斯：`lookup_secoc_tier` + TSK 工具链。
