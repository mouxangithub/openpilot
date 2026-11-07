# C3 DOS / 黑熊 / 红熊 Panda 刷机、恢复与 F4 移植

适用于 **comma three（C3 / `tici`）** 内置 **DOS（F4）**、外接 **黑熊（F4, aux）** 或 **红熊（H7, aux）**。

> **事实来源**：`ai/docs/PANDA_FLASH.md`、`ai/docs/PANDA_C3_F4_PORTING.md`、`ai/docs/COMMA_DEVICES.md`。  
> **F4 移植参考提交**（三层）：
> - `panda@7d703710` — F4 固件与 Python
> - `sp@43d4f56f` — 主仓 pandad 双 USB、`launch_chffrplus`、`num_pandas`
> - `opendbc@3244efe` — 多 Panda 指纹、Toyota CanBus、F4 safety 裁剪
> CLI `ai/scripts/recover_dos_panda.py` **可选**；op 助手 **内联刷机**（`ai/tools/panda_flash_tools.py`）。

---

## 何时触发

- 侧栏 **NO PANDA** / **否**（`pandaStates` 空但 USB 有 Panda）
- 新 fork / OTA 后 **不适配黑熊、DOS、C3 内置 F4**
- `from panda import Panda` → `unknown HW` / `SUPPORTED_DEVICES` 仅 H7
- `panda/board/obj/panda.bin.signed` **不存在**
- `panda_firmware_status` → `firmware_match: false` 或需刷写 sig
- 刷写 Panda 后 GUI 仍 **Panda 否**（pandad 未恢复 → 重启 manager）

---

## 术语与固件来源

| 对象 | MCU | hw_type | 固件路径（openpilot 树下） | 刷机方式 |
|------|-----|---------|---------------------------|----------|
| 内置 DOS | F4 | `0x06` | `panda/board/obj/panda.bin.signed` | **手动**（offroad） |
| 外接黑熊 | F4 | `0x03` | 同上 | **手动** `external=true` |
| 外接红熊 | H7 | `0x07` | `panda_h7.bin.signed` 或 `panda_tici/...` | **pandad 自动** |

**固件不随 `ai` 分发**：`panda.bin.signed` 由 **`panda` 子模块 `scons` 生成**；`panda` 更新后须 `build_panda_firmware` 再刷写。`ai` 只提供路径检测、编译与刷写工具。

- **禁止**：把 `.signed` 复制进 `ai/`；对 F4 使用 `panda_tici` 固件。
- **单内置 DOS**：`TICI_DOS=1` → pandad **跳过** Python 自动刷机；改 `panda/` 后须 **手动刷**。
- **刷写后**：调用 `recover_pandad_after_flash` 逻辑或 **重启 manager**，否则 GUI Panda 否。

---

## F4 移植方法论（其他 openpilot 不适配时）

当目标 fork 的 `panda` 子模块已 **淘汰 F4（仅 H7）**，但硬件仍是 C3 DOS / 黑熊：

### 第一步：确认缺口

1. `list_all_pandas` / `panda_firmware_status`
2. 车机：`ls panda/board/obj/panda.bin.signed`
3. 读 `panda/python/__init__.py`：`SUPPORTED_DEVICES` 是否含 `F4_DEVICES` / `HW_TYPE_DOS`

### 第二步：合入 panda 子模块（对照 `7d703710`）

**最小必改**（详见 `ai/docs/PANDA_C3_F4_PORTING.md` §3）：

| 区域 | 内容 |
|------|------|
| `SConscript` | `base_project_f4` + `build_project("panda", ...)` |
| `board/stm32f4/` | F4 HAL、启动文件、bxcan |
| `board/boards/dos.h` | C3 DOS 板级 |
| `board/stm32f4/board.h` | `detect_board_type` → DOS |
| `board/main.c` / `drivers.h` | F4 用 bxcan，H7 用 fdcan |
| `python/__init__.py` | `F4_DEVICES`、`get_mcu_type()`、`bytes` 化 `get_type()`、按 MCU 刷机 |

```bash
cd panda && git cherry-pick 7d703710   # 或按文档逐项合入
cd board && scons -j$(nproc)
```

### 第三步：核对 openpilot 主仓（对照 `sp@43d4f56f`）

| 区域 | 内容 |
|------|------|
| `launch_chffrplus.sh` | `set_tici_hw` → `TICI_DOS` / `TICI_TRES`；F4 时 `set_aux_panda` + `mount_nvme` |
| `selfdrive/pandad/` | `panda_comms.cc` USB、`bus_offset` 多 Panda、`pandad.py` `should_launch_cpp_directly` |
| `selfdrive/car/card.py` | `get_car(..., num_pandas=len(pandaStates))` |
| `tools/scripts/car/fw_versions.py` | 同上 `num_pandas` |

### 第四步：核对 opendbc_repo（对照 `opendbc@3244efe`）

| 区域 | 内容 |
|------|------|
| `opendbc/car/fw_versions.py` | `num_pandas`：跳过超出 `num_pandas*4` 的 bus 查询 |
| `opendbc/car/car_helpers.py` | `fingerprint` / `get_car` 透传 `num_pandas` |
| `opendbc/car/toyota/*` | `CanBus` offset；`CAN.pt >= 4` 时双 safety config |
| `opendbc/safety/safety.h` | `#ifdef CANFD` 包裹 CAN-FD-only safety（F4 无 CANFD） |

### 第五步：刷机 + 恢复 pandad

1. offroad → `flash_panda_firmware(confirm=true, all_pandas=true)` 或 SecOC 刷写
2. 刷写后 **重启 manager** 或 `tsk_restart_pandad`（若仍 Panda 否）
3. 验证：`panda_firmware_status` 签名匹配、`pgrep -af pandad`、GUI Panda **是**

**AI 应优先阅读** `ai/docs/PANDA_C3_F4_PORTING.md` 获取完整文件列表与决策树。

---

## 推荐工具顺序（offroad，已有机型支持时）

1. `panda_status` / `list_all_pandas`
2. `panda_firmware_status` — 签名是否匹配
3. `panda_recovery_hint` — NO PANDA 诊断
4. 缺 `panda.bin.signed` → 先 **F4 移植**（上节），再 `build_panda_firmware`
5. `flash_panda_firmware(confirm=true, all_pandas=true)` — 优先于仅 `recover_dos_panda`
6. 刷写后仍 Panda 否 → **重启 manager**（`tsk_restart_manager` 或 SecOC 按钮）
7. 双 USB 崩溃 → `rebuild_pandad` + reboot

| 目标 | 工具 |
|------|------|
| 内置 DOS | `flash_panda_firmware` 或 `recover_dos_panda(internal=true)` |
| 外接黑熊 F4 | `recover_dos_panda(external=true)` |
| 外接红熊 H7 | **不要** `recover_dos_panda`；确保 pandad 自动刷 H7 |

---

## CLI（车机 SSH）

```bash
cd /data/openpilot/panda/board && scons -j$(nproc)
cd /data/openpilot
PATH=/usr/local/venv/bin:$PATH PYTHONPATH=/data/openpilot \
  python3 -c "from ai.tools.panda_flash_tools import flash_panda_firmware; print(flash_panda_firmware(confirm=True, all_pandas=True))"
# 若 GUI Panda 否：
# SecOC → 重启 manager，或 reboot
```

---

## 与 TSK / SecOC

- TSK 采集会 `stop_manager_and_pandad()`；结束后恢复 pandad / manager。
- SecOC 面板「刷写 Panda 固件」= `POST /api/panda/flash`；完成后应提示 pandad 恢复或重启 manager。

## 相关技能

- `engage-troubleshooting` — 无法开启 OP
- `diagnostics` — 进程与日志
- `network-diagnostics` — devsync 同步移植后的 `panda` 子模块
