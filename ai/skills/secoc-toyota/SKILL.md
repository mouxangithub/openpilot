# SecOC / TSK 丰田系技能

> 参考：[optskug/docs](https://github.com/optskug/docs) · 本 fork 内置 TSK · 适配总指南 `ai/docs/VEHICLE_ADAPTATION_GUIDE.md`

## 何时启用

- 丰田 / 雷克萨斯用户提到 **SecOC、TSK、ECU Security Key、安全密钥、dashcam only**
- `startupNoSecOcKey` 事件
- 已支持列表外的 TSS2+ 年款、RAV4 Prime、Sienna 等

## 核心事实（必须先讲清）

1. **SecOC ≠ 写 DBC**：没有本车 **SecOCKey** 前，无法合法发送转向控制 CAN。
2. **每台车密钥不同**，必须从本车 EPS 提取；不能共用社区别人的 key。
3. **AI 禁止**：用 `write_params` 写 `SecOCKey`、要求用户把完整密钥贴进聊天、在回复中复述完整 key。

## 本 fork 内置 SecOC（op 助手设置）

offroad 时打开 **`http://<设备IP>:5090/?settings=secoc`**（设置侧边栏 → SecOC 标签）。

三种安装路径（按车型选一条，不要混用误导）：

| 路径 | 适用车型 | 页面操作 | AI 工具（均需 offroad + `confirm=true`） |
|------|----------|----------|------------------------------------------|
| **TSK 一键提取** | 2021–2023 RAV4 Prime、Sienna 等 | 「开始 TSK 提取」 | `tsk_extract_key` |
| **手动安装** | 用户已有 32 位 hex 密钥 | 输入框 →「安装密钥」 | `tsk_install_secoc_key(key=…)` |
| **CAN + DataFlash 查找** | 2021+ 多数丰田 | 采 CAN → 导 DF →「查找密钥」 | `tsk_start_can_collect` → `tsk_start_dataflash_dump` → `tsk_find_and_install_key` |

密钥写入后 **重启设备**（`reboot_device` 或手动）；切换 fork 用 `git_checkout` / `git_pull`。

## AI 工具速查（必须熟练）

> **Comma 设备**：F4/C3 在 `panda_tici` **与** `pandad_tici` 均存在时用 tici 栈，否则回退 `panda`/`pandad`。详见 `ai/docs/COMMA_DEVICES.md`。

| 工具 | 类型 | 用途 |
|------|------|------|
| `get_tsk_manager_status` | 只读 | 密钥是否已装、CAN/DF 进度、`install_options`、`panda_backend`；返回 `ui_card` 可轮询 |
| `lookup_secoc_tier` | 只读 | optskug 🟢/🟡/🔴 分档参考 |
| `tsk_extract_key` | 写 | UDS 一键提取（RAV4 Prime/Sienna） |
| `tsk_install_secoc_key` | 写 | 安装用户提供的 hex（参数 `key`，勿在聊天公开） |
| `tsk_find_and_install_key` | 写 | CAN+DF 匹配查找并安装 |
| `tsk_start_can_collect` | 写 | 启动 CAN 采集（READY 模式） |
| `tsk_start_dataflash_dump` | 写 | 启动 DataFlash 导出（Not Ready） |
| `tsk_clear_cache` | 写 | 清除 CAN/DF 缓存（不删密钥） |
| `tsk_uninstall_key` | 写 | 卸载已装密钥 |
| `tsk_wait_for_job` | 只读 | 等待 CAN/DataFlash/match 作业结束 |
| `tsk_cancel_job` | 写 | 取消进行中的 CAN 或 DataFlash 采集 |
| `tsk_restart_pandad` | 写 | 黑屏恢复：终止本机 pandad（C3→`pandad_tici`，C3X/C4→`pandad`） |
| `tsk_run_pipeline` | 写 | CAN→DF→查找 一条龙 |
| `get_tsk_offroad_alert_status` | 只读 | Offroad 无固件提醒是否激活 |

**编排顺序（标准 🟢 路径）：**

1. `get_tsk_manager_status` + `lookup_secoc_tier`
2. 若未装密钥且为 RAV4 Prime/Sienna → 优先 `tsk_extract_key(confirm=true)`
3. 若用户说已有密钥 → 引导 `/?settings=secoc` 手动安装，或 `tsk_install_secoc_key(key=…, confirm=true)`
4. 否则 → `tsk_run_pipeline(confirm=true)`，或分步：`tsk_start_can_collect` → `tsk_wait_for_job(job=can)` → `tsk_start_dataflash_dump` → `tsk_wait_for_job(job=dataflash)` → `tsk_find_and_install_key`
5. 失败后查看返回的 `next_steps` / `debug`；黑屏可 `tsk_restart_pandad(confirm=true)`（仅杀当前设备对应进程）
6. 成功后提醒重启；`read_onroad_events` 确认无 `startupNoSecOcKey`

成功安装后工具结果仅含 `secoc_key_prefix`，**禁止**在回复中输出完整密钥。

## 车型分档（引导用户自查 optskug）

| 档位 | 含义 | 用户该做什么 |
|------|------|----------------|
| 🟢 | 可用标准 TSK 流程 | 设置 → SecOC，或让 AI 按上表编排工具 |
| 🟡 | 实验路径（如部分 **2024 美版 Sienna**） | [Vance425 笔记](https://github.com/Vance425/ToyotaSienna2024OpenpilotAnalysis-_Note) + [Bk2ol 工具](https://github.com/Bk2ol/tsk_extraction_by_can_log) |
| 🔴 | 目前无法破解 | 不要承诺能适配；仅 dashcam / 关注 #toyota-security |

**TSS 世代不能代替 SecOC 判断**——以 optskug 列表 + EPS 版本 + 制造年月为准。

## 标准 🟢 流程检查清单

1. 确认车型在 optskug **🟢** 列表（注意 **VIN 产地、门边制造年月**）。
2. offroad 打开 **`http://<IP>:5090/?settings=secoc`**。
3. 按车型选：一键提取 / 手动安装 / CAN→DF→查找。
4. 密钥写入后 Dashy → Developer → SecOCKey Install 核对（**用户自行操作**）。
5. 使用**支持 SecOC 的 fork/构建**（release 通常不支持）。
6. 重启后 `read_onroad_events` 确认无 `startupNoSecOcKey`。
7. 密钥就绪后，才进入 DBC/指纹/路试（见 `vehicle-adaptation` 技能）。

## 诊断工具（只读）

| 工具 | 用途 |
|------|------|
| `read_onroad_events` | 查 `startupNoSecOcKey` |
| `read_params` | CarParams、`SecOCKey` 是否已配置（**勿复述完整 key**） |
| `grep_log` | `secoc`, `SecOC`, `dashcam` |
| `trip_review` | 行程复盘含 SecOC 提示 |
| `cabana_analyze` | 解释 `0x2E4` / `STEERING_LKA` 等 |

## 话术模板

「您的症状符合 SecOC 车未安装密钥。请 offroad 打开 **http://&lt;设备IP&gt;:5090/?settings=secoc**，或在聊天中让我执行 TSK 工具（写操作需您点确认）。也可对照 https://github.com/optskug/docs 看年款是 🟢/🟡/🔴。」
