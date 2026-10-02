# 2026-10 设计决策：jetlink 对齐边界与 locationd 告警

记录 2026-10-01/02 两天的三项设计决策及其依据，供后续演进参考。
格式借鉴 zoompilot 的设计文档文化（docs/zoompilot/）：决策、根因、放弃的方案都留痕。

## 1. jetlink 对齐边界：为什么停在 zoompilot develop 的 94d41f458 + 4 个修复

**决策**：jetlink 生态对齐到 zoompilot develop `94d41f458`，外加 4 项修复（fetcher manifest、
modeld 校验、qlog big 标记、pin 回退 v0.7.3），不追 danger-unstable。

**依据**：
- develop 是实车验证线；danger-unstable 的 v0.7.4 hand-back 特性需要 modeld 侧
  frame_drop_ratio 配套（a10b49543），sp 不带该链路，半接入比不接入更危险。
- Mazda 调校与 SCC 重构在同一批提交里交织，剥离成本高于收益。

**放弃的方案**：全量跟进 develop（引入未验证的 Mazda/SCC 变更）；
跳过 pin 回退（保留 ce5f834 但无 hand-back 配套，行为不完整）。

## 2. locationd「临时错误」：旧 sanity 门与新校准的冲突

**现象**：更新后行驶中弹「sunnypilot 不可用 / locationd临时错误」。

**根因链**：df61c8fd9 让 IMU 校准首次可用 → 收集期 imu_calibrationd 发布大角度 rpyCalib
（水平装 ~90° pitch，设计使然）→ locationd 旧 ±30° sanity 门判每帧 cameraOdometry
INPUT_INVALID（只容 2 帧）→ inputsOK=False → SOFT_DISABLE。

**修复**（63fb2d870 + e844846e4）：
1. IMU 校准启用期间豁免大角度门（校准流程自身有 `_validate_final_matrix` 兜底）。
2. `_imu_source_seen` 粘性改 10 秒衰减——否则关闭校准后 paramsd 永久忽略 rpyCalib 帧，
   calib_valid 冻结在旧 IMU 矩阵上（开→关切换场景）。

**放弃的方案**：直接移除 locationdTemporaryError 事件（削弱真传感器异常的安全提示）；
仅在前端抑制显示（治标）。

## 3. pkl 校验是安全门，部署前必须只读预检

`check_modeld_pkl` / `check_camera_jit` 在 ModelState.__init__ 里把坏 pkl 从裸 KeyError
变成明确报错——但报错即 modeld 拒绝启动。因此部署包含这两项校验的版本前，必须用
**自包含脚本**（不依赖新代码）对设备现有 pkl 做只读验证；big pkl 缺失是正常状态
（无 chestnut 时不加载）。本次预检 driving_tinygrad.pkl 通过后才放行。

## 遗留

- SCC 弯道规划重构：依赖 opendbc icbm_actuation_profile 升级 + longitudinal_planner/
  controlsd 控车链改动，需独立分支与实车验证（任务 #154）。
- mici 分页设置体系：UI 架构重构，需与 carrot 设置融合方案（任务 #154）。
- 行驶中 inputsOK 瞬态取证：记录器在 /data/locdiag.py，下次行驶后分析 /data/locdiag.log。
