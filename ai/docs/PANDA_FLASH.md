# Panda 刷机与恢复（sunnypilot / C3 DOS）

> **单一事实来源**（与 `ai/docs/COMMA_DEVICES.md` 互补）。  
> **C3 / DOS / 黑熊 / 多 Panda 移植**：见 [`PANDA_C3_F4_PORTING.md`](PANDA_C3_F4_PORTING.md)（`panda@7d703710`、`sp@43d4f56f`、`opendbc@3244efe`）。  
> op 助手工具：`list_all_pandas`、`list_f4_pandas`、`flash_panda_firmware`、`recover_dos_panda`、`rebuild_pandad`、`panda_recovery_hint`。

## 术语

| 名称 | MCU | hw_type (`panda` Python) | 说明 |
|------|-----|--------------------------|------|
| DOS / 内置 Panda | F4 | `0x06` DOS | C3 板载 |
| 黑熊 Black Panda | F4 | `0x03` BLACK_PANDA | 常见外接 aux |
| 红熊 Red Panda | H7 | `0x07` RED_PANDA | 外接，自动刷 `panda_tici` |

## sunnypilot C3 架构要点

1. **`pandad_tici`** 负责 C3 上 pandad 进程（含 DOS 快速路径、**多 Panda USB**）。
2. **内置 F4 固件**：`panda/board/obj/panda.bin.signed` — **`panda` 子模块 `scons` 生成**，随 `panda` 迭代更新；**不内置在 `ai/`**。
3. op助手通过 `build_panda_firmware` 调 `scons panda/board`，刷写时读 openpilot 树下的产物路径。
4. **`panda_tici` 固件** 仅用于 **H7**（外接红熊）；刷到 F4 会损坏或无法启动。
5. `pandad_tici` 对非 H7 **跳过自动刷机**；代码更新后内置 DOS **需手动刷**。
6. `Panda.flash()` 在 `panda`/`panda_tici` Python 中 assert 仅 H7；F4 使用 **`Panda.flash_static` + bootstub**（`recover_dos_panda` 内联实现）。
7. **多 Panda** 靠 `pandad_tici` + `panda_tici` Python 的 `set_aux_panda()`，不是只替换 `panda_tici` 子模块。
8. **`panda` 子模块 bump 后**：必须重新 `scons` 生成 `.signed`，再刷写；勿把旧固件复制进 `ai`。

## 脚本与工具

| 入口 | 用途 |
|------|------|
| `ai/scripts/recover_dos_panda.py` | 可选 CLI（部分 fork 有）；**op 助手不依赖此文件** |
| op助手 `recover_dos_panda` | 内联实现于 `ai/tools/panda_flash_tools.py`，需 `confirm=true` |
| `tools/rebuild_pandad_tici.sh` | `updated` git reset 后重链 `pandad` 二进制 |
| op助手 `build_panda_firmware` | 在 openpilot 树下 `scons panda/board` 生成 `.signed`（**非 ai 内置**） |
| op助手 `list_all_pandas` | 全部 USB Panda + 多 Panda 场景 + `pgrep pandad` 快照 |

## 标准流程（车机）

```bash
# 1. 编译 F4 固件（若缺失）
cd /data/openpilot/panda/board && scons -j$(nproc)

# 2. 刷机（离路，仅 F4）
cd /data/openpilot
PYTHONPATH=/data/openpilot python3 ai/scripts/recover_dos_panda.py --internal

# 3. 重编 pandad（若被 updated 删掉或改了 pandad_tici 源码）
bash tools/rebuild_pandad_tici.sh

# 4. 重启
sudo reboot
```

## 双 Panda（内置 + 外接）

| 组合 | 内置 | 外接 | 刷机 | pandad |
|------|------|------|------|--------|
| 内置 + 红熊 | F4，跳过刷机 | H7，`panda_tici` 自动 | 内置一般不需动 | **双 serial** |
| 内置 + 黑熊 | F4，跳过刷机 | F4，跳过刷机 | **两只都可能需手动** `recover_dos_panda` | 视 fork |
| 官方 C3X 类 | SPI H7 | USB H7 | H7 自动 | 双 H7 |

### C3 DOS + 外接红熊（异构 F4 + H7）

常见用户场景：**内置 DOS (F4)** + **外接红熊 (H7)**，两只均在 USB 上（`lsusb` 两个 `3801:ddcc`）。这与 comma 官方「SPI 内置 H7 + USB 外接」不同，但 `pandad_tici` 应同时打开两只设备。

**已知 bug（已修复于 `master-c3`）：**

| 文件 | 问题 | 修复 |
|------|------|------|
| `selfdrive/pandad_tici/pandad.py` | `p.close()` 后仍读 `uses_panda_tici_firmware(p)` | close 前缓存 `has_non_h7_panda` → `BOARDD_SKIP_FW_CHECK` |
| `selfdrive/pandad_tici/panda_comms.cc` | 双 USB 时 `libusb_open` 失败直接 `fail`；`set_configuration` 与 Python 不一致 | 失败 `continue`；对齐 configuration 逻辑 |

**症状：** GUI 侧栏 **Panda 否**；`pandaStates` 空；`manager.log` 含 `USBErrorBusy` / `exitcode -6`；`pgrep -af pandad` 无进程或反复重启。

**修复后验证：**

```bash
pgrep -af pandad
# 期望：./pandad <内置serial> <外接serial>
list_all_pandas   # op 助手：multi_panda.scenario = heterogeneous_f4_h7
```

外接黑熊：`--external` 或 `--serial <aux序列号>`（`list_f4_pandas` 查 `internal=false`）。

## 验证

- `panda_status`：`pandaStates` 非空；`multi_panda` / `pandad_snapshot` 与 USB 一致
- 日志：`DOS internal panda: skipping Python panda setup`，无 `xhci-hcd` 误重连
- `pgrep -af pandad`：`pandad_tici` 二进制，多 Panda 时 cmdline 含多个 serial

## 常见错误

| 现象 | 原因 | 处理 |
|------|------|------|
| NO PANDA + USB 两只 Panda | `pandad_tici` 双 USB bug / 崩溃循环 | `rebuild_pandad_tici` + reboot；查 `USBErrorBusy` |
| NO PANDA + xhci 重连 | USB 过滤 / pandad 退出 | 已修复的 `pandad_tici` 代码 + 重启 |
| 刷机后仍 NO PANDA | 未 `rebuild_pandad_tici` | 运行重编脚本并 reboot |
| 用了 panda_tici 固件刷 F4 | 固件包错误 | DFU 恢复 + `recover_dos_panda` |
| `Panda.flash()` 断言失败 | F4 不在 SUPPORTED_DEVICES | 用 `recover_dos_panda` |
| 外接红熊误刷 F4 固件 | 工具选错 | **禁止** `recover_dos_panda`；用 `pandad_tici` |

## 相关文档

- [`COMMA_DEVICES.md`](COMMA_DEVICES.md) — 产品映射与 pandad 模块选择
- [`TSK_AND_AID.md`](TSK_AND_AID.md) — TSK 停 manager/pandad 行为
- 技能 `c3-dos-panda` — op 助手排障顺序
