# C3 / DOS / 黑熊 / 多 Panda 移植指南

> **给 AI 与维护者**：当某 openpilot fork 不适配 **C3 内置 DOS（F4）**、**外接黑熊（F4 aux）** 或 **双 Panda（F4+H7）** 时，按本文在三个子模块/层级补齐改动。  
> **参考提交（本 fork `sp` / `master-c3`）**：
>
> | 层级 | 提交 | 说明 |
> |------|------|------|
> | `panda/` | `7d703710` | 适配C3：恢复 F4 构建、DOS 板级、Python 刷机 |
> | `openpilot` 主仓 | `43d4f56f` | C3 DOS 双 Panda、pandad USB、`launch_chffrplus`、指纹 `num_pandas` |
> | `opendbc_repo/` | `3244efe` | 多 Panda bus 指纹、F4 safety 裁剪、丰田威兰达 PHEV |
>
> **配套技能**：`ai/skills/c3-dos-panda/SKILL.md`（刷机/恢复流程）。

---

## 1. 背景：为什么需要移植

comma 新一代 `panda` 主线以 **H7（红熊 / C3X / C4）** 为主，`SUPPORTED_DEVICES` 往往只剩 H7。但：

| 硬件 | MCU | `hw_type` | 固件产物 |
|------|-----|-----------|----------|
| C3 内置 DOS | F4 | `0x06` | `panda/board/obj/panda.bin.signed` |
| 外接黑熊 Black Panda | F4 | `0x03` | 同上 |
| 外接红熊 Red Panda | H7 | `0x07` | `panda/board/obj/panda_h7.bin.signed` 或 `panda_tici/...` |

**症状（未移植时）**

- `python -c "from panda import Panda; Panda.list()"` 能列出 USB，但 `get_type()` / `get_mcu_type()` 报错 `unknown HW`
- `Panda.flash()` assert：`Unknown HW`
- `scons` 只产出 `panda_h7.bin.signed`，没有 `panda.bin.signed`
- openpilot GUI **Panda 否**，`pandaStates` 为空（pandad 起不来或签名校验失败）
- op助手 `panda_firmware_status` 显示 `firmware_match: false` 或 `status_error`

---

## 2. 移植总览（三层 + 子模块）

```
panda/ 子模块          openpilot 主仓 (sp)            opendbc_repo/              op 助手 ai/
─────────────────     ─────────────────────         ─────────────────          ─────────────────
F4 工具链 + DOS 板级   launch_chffrplus TICI_DOS      num_pandas 指纹查询         检测路径 + build_panda_firmware
scons → .bin.signed   pandad USB + 双 Panda         Toyota CanBus offset       flash_serial / recover
（产物在 panda/obj）   set_aux_panda / mount_nvme     safety.h CANFD 条件编译     recover_pandad_after_flash
                      card.py → get_car(num_pandas)
```

**原则**

- F4 固件 **永远** 来自 `panda/board/obj/panda.bin.signed`（`panda` 子模块 `scons` 产物）。
- **禁止** 把 `panda.bin.signed` 放进 `ai/` 或随 op助手 OTA 分发；`panda` 子模块更新后须 **重新 scons + 刷写**。
- **禁止** 把 `panda_tici` 或 H7 镜像刷到 F4/黑熊/DOS。

---

## 2.1 固件产物与 `ai` 的边界（AI 必读）

| 问题 | 答案 |
|------|------|
| `panda.bin.signed` 在 `ai` 里吗？ | **否**。`ai/` 仓库内无 `.signed` 固件文件。 |
| 固件从哪来？ | 车机/编译机上对 **`panda` 子模块** 执行 `scons`：`cd panda/board && scons -j$(nproc)` |
| C3 为何要移植 `panda`？ | 上游淘汰 F4 后无法产出 `panda.bin.signed`；须合入 `panda@7d703710` 等 F4 构建后再 scons |
| `panda` 更新后怎么办？ | 拉新子模块指针 → `build_panda_firmware` → offroad `flash_panda_firmware` → 重启 manager |
| op助手做什么？ | **知道路径与流程**：检测缺失、`build_panda_firmware` 调 scons、刷写读 openpilot 树下产物 |

```bash
# 典型 C3 DOS 流程（固件不来自 ai）
git -C panda log -1 --oneline          # 确认 F4 适配提交已合入
cd panda/board && scons -j$(nproc)     # 生成 obj/panda.bin.signed
ls -la obj/panda.bin.signed            # 验证产物
# offroad：flash_panda_firmware(confirm=true)
```

---

## 3. `panda` 子模块改动清单（对照 `7d703710`）

### 3.1 构建系统 `SConscript`

- 增加 `base_project_f4`（Cortex-M4、STM32F413、链接脚本 `stm32f4_flash.ld`）
- `CPPPATH` 加入 `./board/stm32f4/inc`
- **同时** 编译两个目标：
  - `build_project("panda", base_project_f4, ...)` → `panda.bin.signed`
  - `build_project("panda_h7", base_project_h7, ...)` → `panda_h7.bin.signed`

### 3.2 STM32F4 平台文件（从旧版 comma `panda` 或本仓历史引入）

整目录 `board/stm32f4/`：`inc/`、`startup_stm32f413xx.s`、`stm32f4_config.h`、`llbxcan.*`、`llusb.*` 等。

### 3.3 板级与 CAN

| 文件 | 作用 |
|------|------|
| `board/boards/dos.h` | C3 内置 DOS 引脚、CAN 收发器、harness、`board_dos` |
| `board/boards/board_declarations.h` | `HW_TYPE_DOS 6`、`extern board_dos` |
| `board/stm32f4/board.h` | `detect_board_type()` → DOS 时 `hw_type = HW_TYPE_DOS` |
| `board/config.h` | `#elif defined(STM32F4)` 包含 f4 config |
| `board/drivers/drivers.h` | F4 走 **bxcan**（非 fdcan）；harness/uart 与 H7 共用宏 |
| `board/main.c` | `#ifdef STM32F4` 用 `bxcan.h`，否则 `fdcan.h` |
| `board/drivers/bxcan.h` | F4 CAN 驱动（从旧树迁入） |

### 3.4 Python `python/__init__.py`（关键）

对照 `7d703710`，至少包含：

```python
# 恢复全部 hw_type 常量（含黑熊 0x03、DOS 0x06）
F4_DEVICES = [HW_TYPE_WHITE_PANDA, HW_TYPE_GREY_PANDA, HW_TYPE_BLACK_PANDA,
              HW_TYPE_UNO, HW_TYPE_DOS]
H7_DEVICES = [HW_TYPE_RED_PANDA, HW_TYPE_RED_PANDA_V2, HW_TYPE_TRES, ...]
SUPPORTED_DEVICES = F4_DEVICES + H7_DEVICES
INTERNAL_DEVICES = (HW_TYPE_DOS, HW_TYPE_TRES, HW_TYPE_CUATRO)

def get_mcu_type(self) -> McuType:
  hw_type = self.get_type()
  if hw_type in Panda.F4_DEVICES:
    return McuType.F4
  if hw_type in Panda.H7_DEVICES:
    return McuType.H7
  if self._assume_f4_mcu:
    return McuType.F4
  raise ValueError(f"unknown HW type: {hw_type}")

def get_type(self):
  ret = self._handle.controlRead(...)
  if isinstance(ret, bytearray):
    return bytes(ret)   # 避免 unhashable bytearray
  ...
```

**刷机路径**：`flash()` / `up_to_date()` / `flash_static` 使用 `self.get_mcu_type()`，**不要** 写死 `McuType.H7`。

**bootstub 识别**：旧 bootstub 无 `0xc1` 端点时，用 USB `bcdDevice` 推断 `_bcd_hw_type`（C3 DOS 常见 `bcd != 0x2300`）。

**枚举**：`list()` 合并 SPI + USB，`usb_list` 在 `spi_list` 之后，避免重复。

### 3.5 编译与验证（子模块内）

```bash
cd panda/board
scons -j$(nproc)
ls -la obj/panda.bin.signed obj/panda_h7.bin.signed
```

---

## 4. `openpilot` 主仓改动（对照 `sp@43d4f56f`）

> 主仓提交信息：`feat(c3): 集成 op助手子模块，完善 C3 DOS 双 Panda 与 CI/上游同步工具链`。  
> 移植 C3/DOS 时 **至少** 合入下列与 Panda 相关的文件；UI/翻译/CI 等可按需 cherry-pick。

### 4.1 `launch_chffrplus.sh` — 硬件探测与 DOS 环境

| 函数 | 作用 |
|------|------|
| `set_tici_hw()` | 探测内置 Panda MCU（F4=DOS / H7=TRES），缓存到 `/persist/sp_dev_panda_mcu_type` |
| | F4 → `export TICI_DOS=1` + `mount_nvme()` + `set_aux_panda()` |
| | H7 → `export TICI_TRES=1` |
| `set_aux_panda()` | C3 DOS 专用：将 aux USB-C（`a600000.ssusb`）切 host 模式枚举第二只 Panda；无 aux 则恢复 device 模式 |
| `mount_nvme()` | DOS（F4）挂载 NVMe 到 `/data/media/0/realdata` |
| `set_lite_hw()` | 检测 Lite 硬件（`LITE=1`） |
| `fix_opendbc_capnp_import()` | 修正 `car.capnp` 的 capnp import 路径 |

**顺序**：`set_tici_hw` 在 `set_aux_panda` **之前**（探测内置 Panda 时 aux 口尚未切 host，保证只读到一只）。

### 4.2 `selfdrive/pandad/` — 双 Panda USB 与 DOS

| 文件 | 改动要点 |
|------|----------|
| `panda_comms.cc`（新） | `PandaUsbHandle`：libusb 枚举/打开 Panda（VID `0xbbaa`/`0x3801`） |
| `panda.cc` | 构造时 **先 USB 后 SPI**；`bus_offset` 支持多 Panda CAN bus 映射 |
| `panda.h` | `PandaCommsHandle` 抽象；`list(usb_only)` 合并 USB+SPI 序列号 |
| `pandad.cc` | `main` 接受 **多个 serial**；双 Panda 循环 health/CAN |
| | `red_panda_comma_three`：DOS+H7 时忽略 DOS 误点火（harness box 无 connector） |
| `pandad.py` | `should_launch_cpp_directly()`：单内置 F4 + `TICI_DOS=1` 跳过 Python 自动刷机 |
| `SConscript` | 链接 `libusb-1.0`，编译 `panda_comms.cc` |
| `main.cc` | `argv[1..]` 全部作为 panda serial 传入 |

```python
# pandad.py — C3 单内置 DOS 不自动刷 F4
def should_launch_cpp_directly(panda_serials: list[str]) -> bool:
  return os.getenv("TICI_DOS") == "1" and len(panda_serials) == 1
```

**双 Panda bus 规则**：第一只 Panda `bus_offset=0`（bus 0–3），第二只 `bus_offset=4`（bus 4–7）。`pack_can_buffer` / `unpack_can_buffer` 按 offset 过滤/标注 `src`。

### 4.3 `selfdrive/car/card.py`

启动指纹时把 **实际 Panda 数量** 传给 opendbc：

```python
num_pandas = len(messaging.recv_one_retry(self.sm.sock['pandaStates']).pandaStates)
self.CI = get_car(..., num_pandas, ...)
```

### 4.4 `tools/scripts/car/fw_versions.py`

CLI 指纹工具同样读取 `pandaStates` 长度，调用 `get_fw_versions(..., num_pandas=num_pandas)`。

### 4.5 其它主仓项（可选）

- `ai` 子模块 + `start_op_assistant()`：开机拉起 op助手 `:5090`（与 Panda 无直接关系，本 fork 标配）
- `common/hardware/comma/`、`camerad` AR0231 等：C3 硬件配套，移植 Panda 时可不同步

---

## 5. `opendbc_repo` 改动（对照 `opendbc@3244efe`）

> 提交信息：`适配c3，Toyota添加威兰达插混和多panda bus`。

### 5.1 多 Panda 指纹查询 `num_pandas`

**问题**：双 Panda 时 bus 4–7 才可用；单 Panda fork 去查高 bus 会超时或误匹配。

| 文件 | 改动 |
|------|------|
| `opendbc/car/fw_versions.py` | `get_present_ecus` / `get_fw_versions` / `get_fw_versions_ordered` 增加 `num_pandas`；`r.bus > num_pandas * 4 - 1` 时 **跳过** 该查询 |
| `opendbc/car/car_helpers.py` | `fingerprint()` / `get_car()` 透传 `num_pandas`（默认 1） |

主仓 `card.py` 必须传入真实 `num_pandas`（见 §4.3），否则双 Panda 车型指纹会失败。

### 5.2 Toyota 多 Panda bus（`CanBus` offset）

| 文件 | 改动 |
|------|------|
| `opendbc/car/toyota/values.py` | 新增 `CanBus(CanBusBase)`：`pt=offset`、`alt=offset+1`、`cam=offset+2` |
| `opendbc/car/toyota/interface.py` | `CAN = CanBus(fingerprint=fingerprint)`；若 `CAN.pt >= 4` 在 safety 列表前插入 `noOutput`（第二只 Panda 占位） |
| `opendbc/car/toyota/carstate.py` / `carcontroller.py` / `toyotacan.py` / `radar_interface.py` | 使用 `CanBus` 替代硬编码 `Bus.pt` 等 |
| `opendbc/car/toyota/fingerprints.py` | 新增 `TOYOTA_WILDLANDER_PHEV` 指纹 |
| `opendbc/sunnypilot/car/car_list.json` | 车型列表登记 |

**含义**：外接 aux Panda 时 PT 总线在 bus 4+，Toyota 逻辑通过 fingerprint 推断 offset，自动对齐 CAN 发送/接收 bus。

### 5.3 F4 Panda safety 裁剪（`#ifdef CANFD`）

F4 DOS **无 CAN-FD**；`opendbc/safety/safety.h` 将仅 CAN-FD 的 safety mode 包在 `#ifdef CANFD` 内：

- `volkswagen_meb`、`hyundai_canfd` 的 include 与 `set_safety_hooks` 表项
- `gen_crc_lookup_table_16`

`opendbc/safety/modes/hyundai_common.h`、`declarations.h` 有配套小改动。  
**panda F4 固件编译** 时不定义 `CANFD`，避免链接/体积问题。

### 5.4 Cherry-pick 示例

```bash
cd opendbc_repo
git fetch <remote with 3244efe>
git cherry-pick 3244efec
```

若仅需多 Panda 指纹、不要威兰达车型，可只合入 `fw_versions.py` + `car_helpers.py` + Toyota `CanBus` 相关文件。

---

## 6. op 助手 `ai/` 层（本 fork 已实现）

| 模块 | 作用 |
|------|------|
| `ai/system/panda_stack.py` | 检测 `panda/` vs `panda_tici/`、`pandad` vs `pandad_tici` |
| `ai/tools/panda_flash_tools.py` | F4 `flash_serial()`、`flash_panda_firmware()`、场景指引 |
| `ai/tsk/lib/panda_connect.py` | `TICI_DOS` 检测、刷写后 `recover_pandad_after_flash()` |
| `ai/skills/c3-dos-panda/SKILL.md` | 排障与刷机 SOP |

刷写 F4 后会 `stop_pandad()`；若 GUI **Panda 否**，需 **重启 manager** 或调用 `recover_pandad_after_flash()`（manager 对外部 SIGKILL 不会自动重建 pandad 子进程）。

---

## 7. 在新 fork 上的操作 SOP

### 7.1 诊断（先确认缺什么）

```bash
# 子模块指针
git -C panda log -3 --oneline
ls panda/board/obj/panda.bin.signed 2>/dev/null || echo "MISSING F4 FW"

# USB
PYTHONPATH=/data/openpilot python3 -c "
from panda import Panda
print('list', Panda.list())
p=Panda(Panda.list()[0])
print('type', p.get_type().hex())
print('mcu', p.get_mcu_type())
print('SUPPORTED', Panda.SUPPORTED_DEVICES)
p.close()
"
```

### 7.2 移植步骤

1. **panda**：对比 `panda@7d703710`，合入 §3 文件 → `scons panda/board`。
2. **openpilot 主仓**：合入 §4（至少 `launch_chffrplus.sh`、`pandad/*`、`card.py`）。
3. **opendbc_repo**：合入 §5（至少 `num_pandas` 指纹链；双 Panda 丰田再加 `CanBus`）。
4. **核对** 子模块指针与 `TICI_DOS` 是否在启动脚本生效。
5. **offroad 刷写** 内置 DOS：`flash_panda_firmware(confirm=true)` 或 SecOC。
6. **刷写后** `recover_pandad_after_flash()` 或重启 manager。
7. **验证**：`panda_firmware_status`；双 Panda 时 `pandaStates` 长度为 2；指纹/车型识别正常。

### 7.3 Cherry-pick 示例

```bash
# panda F4
cd panda && git cherry-pick 7d703710 && cd board && scons -j$(nproc)

# openpilot 主仓（在 sp 根目录）
git cherry-pick 43d4f56f   # 冲突多时可按 §4 手工合入 pandad + launch_chffrplus

# opendbc
cd opendbc_repo && git cherry-pick 3244efec
```

若 cherry-pick 冲突多，按各节文件清单逐项手工合入。

### 7.4 勿做的事

- 勿对 F4 调用 `Panda.flash()`（若 `SUPPORTED_DEVICES` 未含 F4 会直接 assert）
- 勿用 `panda_tici` 固件刷 DOS/黑熊
- 勿假设 `scons` 或 OTA 会自动刷内置 F4
- 刷写后勿忽略 pandad 恢复（否则 GUI Panda 否）

---

## 8. AI 决策树（简版）

```
用户：C3 / 黑熊 / DOS / Panda 否 / 双 Panda / 指纹失败 / 不适配
  ├─ list_all_pandas → 有 USB？几只？F4/H7 组合？
  ├─ panda 子模块缺 panda.bin.signed 或 SUPPORTED_DEVICES 仅 H7？
  │    └─ 是 → §3 panda@7d703710 + scons + 手动刷写
  ├─ 有双 USB 但 pandaStates 仅 1 或 pandad 只开一个？
  │    └─ 核对 §4 launch_chffrplus set_aux_panda + pandad 多 serial + panda_comms.cc
  ├─ 双 Panda 车型指纹超时 / bus 错误？
  │    └─ 核对 §5 opendbc num_pandas + Toyota CanBus；card.py 是否传 num_pandas
  ├─ 刷写后 Panda 否？
  │    └─ recover_pandad_after_flash 或 restart manager
  └─ 外接红熊 H7 → pandad 自动刷 panda_h7.bin.signed，勿 recover_dos_panda
```

---

## 9. 相关文档

- [PANDA_FLASH.md](PANDA_FLASH.md) — 刷机流程、双 Panda、NO PANDA
- [COMMA_DEVICES.md](COMMA_DEVICES.md) — C3/C3X/C4 与 pandad 模块对照
- 技能 `ai/skills/c3-dos-panda/SKILL.md` — op助手工具调用顺序
