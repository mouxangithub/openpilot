# 丰田 / 雷克萨斯 SecOC 密钥

适用于 **丰田、雷克萨斯** 等带 SecOC 加密 CAN 的车型。密钥未安装前通常只能 dashcam，无法控车。

> 事实来源：`ai/docs/TSK_AND_AID.md`、`ai/docs/VEHICLE_ADAPTATION_GUIDE.md`（第二节 SecOC 分类）。**勿手写 `SecOCKey` Param**；一律走 TSK 工具链。

## 何时触发

- 侧栏无法开启 OP，日志含 `SECOC`、`SecOCKey`、`dashcam`、指纹正常但无横向
- `read_onroad_events` / `trip_review` 指向 SecOC 同步失败
- 用户明确要装/换/卸 SecOC 密钥（**必须 offroad**）

## 前置检查（offroad）

1. `lookup_secoc_tier` — 判断车型 Tier（是否社区可提取、是否需 DataFlash 等）
2. `get_tsk_manager_status` — manager / pandad / aid 状态
3. `get_tsk_offroad_alert_status` — TSK 是否允许启动作业
4. `grep_log` — `secoc|SECOC|SecOCKey|tsk`

若正在 onroad 或 manager 繁忙，先停车并确认 offroad。

## 推荐流程

### 一键（多数情况）

1. `lookup_secoc_tier` 确认 Tier
2. `tsk_run_pipeline` — 按 Tier 自动编排（采集 → 提取 → 安装）
3. `tsk_wait_for_job` — 轮询直到完成或失败
4. `tsk_restart_pandad(confirm=true)` — 恢复 pandad（TSK 会停 manager）
5. 再验：`read_params` 中 `SecOCKey` 已存在；`trip_review` / 试 engage

### 分步（失败重试或高级用户）

| 步骤 | 工具 | 说明 |
|------|------|------|
| CAN 采集 | `tsk_start_can_collect` | 按 Tier 要求的路况/时长 |
| DataFlash | `tsk_start_dataflash_dump` | 部分 Tier 需要 |
| 等待 | `tsk_wait_for_job` | 查看进度与错误 |
| 提取密钥 | `tsk_extract_key` | 从采集数据提取 |
| 安装 | `tsk_install_secoc_key` | 写入设备 |
| 查找并安装 | `tsk_find_and_install_key` | 已有密钥文件时 |
| 卸载 | `tsk_uninstall_key` | 换车或清密钥 |
| 取消 | `tsk_cancel_job` | 卡住时 |
| 清缓存 | `tsk_clear_cache` | 异常后重试前 |

## 与 Panda / 刷机的关系

- SecOC 流程会 **`stop_manager_and_pandad()`**；完成后用 `tsk_restart_pandad`，不要与 F4 刷机混为一步。
- C3 DOS / 多 Panda 问题见技能 **`c3-dos-panda`**，文档 `ai/docs/PANDA_FLASH.md`。

## 禁忌

- **不要** `write_params` 直接写 `SecOCKey`
- **不要** onroad 跑 TSK 采集/安装
- 密文 CAN 无法靠 `cabana_analyze` 猜算法；先解决密钥再谈适配

## 相关技能

- `engage-troubleshooting` — 无法开启 OP 总入口
- `sp-brand-toyota` / `sp-brand-lexus` — 丰田系调参与 SecOC 后验证
- `vehicle-adaptation` — 有密钥后的标准适配流程
