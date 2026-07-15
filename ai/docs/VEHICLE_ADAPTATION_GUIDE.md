# 车型适配指南（Dragonpilot + op助手）

本文面向**想自己或借助 AI 适配新车**的使用者，说明能力边界、分步流程，以及 **SecOC 加密车**、**EPS/低速锁止** 等常见坑。

> **安全声明**：openpilot 类系统涉及行车安全。所有首次控车测试必须在**封闭场地、低速**进行；禁止在公开道路做未验证的首次转向/纵向实验。AI 生成内容仅为草稿，必须由人 review 后合入代码。

---

## 一、op助手现在能「读懂」CAN 吗？

**能辅助理解，不等于自动破解或自动控车。**

| 能力 | 实际含义 | 局限 |
|------|----------|------|
| **Cabana + DBC 解码** | 若车型已有 DBC，可看到报文地址、信号名、物理值 | 无 DBC 时只能看原始十六进制 |
| **`cabana_explain_signal`** | 用 LLM 用白话解释**单个已解码信号** | 依赖你提供的 DBC/信号名；可能说错，需人对照手册 |
| **`cabana_analyze`** | 根据你粘贴的 CAN 帧文本做模式分析 | 不自动连车抓包；大段帧需人筛选 |
| **`read_dbc_file` / `list_dbcs`** | 读 opendbc 里已有 DBC 作对照 | 只读，不能改生产库 |
| **适配草稿工具** | AI 可生成 DBC/CarState 片段到 `adaptation_drafts/` | 需人导出、在 PC 上合入 opendbc、路试 |

**SecOC / 加密 CAN 的额外限制**：

- 密文帧在日志里**看不出明文含义**，AI 也无法从 ciphertext 直接「猜出」转向扭矩算法。
- 必须先解决 **SecOCKey**（或确认车型无 SecOC），否则适配工作停在「dashcam / 无法控车」。

结论：**AI 适合当「有 DBC 时的翻译官 + 草稿生成器 + 流程向导」**；**密钥提取、首次上车控车、合入主线**仍须人完成。

---

## 二、先判断：你的车属于哪一类？

在动手前，先对号入座（避免在 🔴 车型上浪费数月）。

### 2.1 已在支持列表

- 查 [comma 车型表](https://comma.ai/vehicles) 或本 fork 的 `opendbc_repo/docs/CARS.md`。
- 若已支持：多数情况是**调 Dragonpilot `dp_*` 参数**，不是从零写 DBC。

### 2.2 无 SecOC，仅缺指纹（最常见「可适配」）

特征：

- 插上设备能识别或接近识别，日志里 `carState` 有合理车速/转向角；
- 社区无人提及 TSK / SecOC / `SECOC_SYNCHRONIZATION` 等。

路径：**标准适配流程**（本文第四节）。工作量通常为数天～数周（取决于 CAN 复杂度）。

### 2.3 SecOC / TSK 车 — 密钥可提取（🟢）

丰田/雷克萨斯部分 2020–2023 年款（如美版 RAV4 Prime、2021–2023 Sienna 部分批次等）社区已有**可重复的密钥提取**流程。

- **权威车型清单与 Setup Guide**：[optskug/docs](https://github.com/optskug/docs)  
- **背景**：[Willem 的 SecOC 密钥提取文章](https://icanhack.nl/blog/secoc-key-extraction/)

流程概要：**先提取 SecOCKey → 写入设备 → 再谈 DBC/指纹**。详见第五节。

### 2.4 SecOC — 实验路径（🟡，如部分 2024 Sienna）

部分 **2024+ 美版 Sienna** 等车型**不走** optskug 标准 GUI 流程，但社区有 **DataFlash 扫描 + CAN MAC 校验** 等实验工具。

- 社区文档：[optskug/docs — 🟡 实验路径](https://github.com/optskug/docs#-reported-working-with-a-newer-experimental-path)  
- 研究笔记（中文）：[Vance425 — Toyota Sienna 2024 分析](https://github.com/Vance425/ToyotaSienna2024OpenpilotAnalysis-_Note)  
- 相关实验仓库（示例）：[Bk2ol/tsk_extraction_by_can_log](https://github.com/Bk2ol/tsk_extraction_by_can_log)

**注意**：同一车型不同产地/生产日期/EPS 版本可能 **成功或失败**；必须把 VIN 产地、门边制造年月、EPS 编号、成败结果反馈到 Discord `#toyota-security`。

### 2.5 SecOC — 目前无法破解（🔴）

[optskug/docs 的 🔴 列表](https://github.com/optskug/docs#-not-hacked-and-cant-run-openpilot) 包括大量 **2022+ 新平台、2024+ 多数改款、Tundra HSM、2024+ RAV4 Prime** 等。

特征：

- 无法从 EPS 导出密钥，或导出后 MAC 校验始终失败；
- CAN 日志里转向相关帧带 SecOC 尾缀，无法仿造合法控制报文。

**此时 AI 适配无法让你「真正控车」**，最多做 dashcam、收集日志、等待社区进展。不要购买设备时期望「靠 AI 自动破解」。

---

## 三、你需要准备什么

| 项目 | 说明 |
|------|------|
| 设备 | comma three（C3）、threeX（C3X）、four（C4）；`device_type` 为 `tici` / `tizi` / `mici`（见 `ai/docs/COMMA_DEVICES.md`） |
| 线束 | 对应品牌 harness（丰田 SecOC 车常用 Harness A） |
| 网络 | 提取密钥、云端 embedding/RAG 时建议 WiFi |
| 场地 | 封闭停车场或赛道用于低速验证 |
| PC | 用于 git、改 opendbc、提 PR / 刷 fork |
| op助手 | 开启「车辆适配」技能；静止时可保存适配草稿 |

---

## 四、标准适配流程（非 SecOC 或已有 SecOCKey）

这是 **AI + 人** 的推荐闭环；在 op助手对话中可直接说：「按适配指南帮我做 XXX 车型」。

### 阶段 A：信息采集（现场 · 人为主）

1. **确认指纹**  
   - 设置 → 关于 / 日志里看 `CarParams` / `carFingerprint`。  
   - 工具：`read_params`（CarParams、Version）。

2. **静止抓 CAN**  
   - 打开 op助手 **Cabana** 抽屉，或导出路线日志。  
   - 记录：**bus 号**、关键 **CAN ID**、报文**长度**、点火/挂 D 档/轻踩油门/打方向时哪些 ID 变化。

3. **找相近车型**  
   - 让 AI：`list_dbcs` → `read_dbc_file` 读相近丰田/本田/大众 DBC 对照。

### 阶段 B：AI 分析（车机或 WiFi）

4. **帧分析**  
   - 把 Cabana 复制的帧粘贴给 AI，调用 `cabana_analyze`。  
   - 对已知信号用 `cabana_explain_signal` 做白话确认。

5. **整理指纹候选**  
   - `analyze_can_id_pattern` 汇总 ID 列表。  
   - 对照 [opendbc fingerprints](https://github.com/commaai/opendbc/tree/master/opendbc/car) 与同品牌车型。

### 阶段 C：生成草稿（AI · 仅写草稿区）

6. **起草文件**（示例结构）  
   ```
   adapt_<车型>/
     dbc/xxx.dbc
     carstate.py.snippet
     carcontroller.py.snippet
     fingerprint.json
     NOTES.md
   ```

7. **保存草稿**（须**车辆静止**）  
   - 工具：`save_adaptation_draft`（`confirm=false` 先预览 → Web 弹窗确认 → 或 `confirm=true`）。  
   - 文件只落在 `/data/openpilot/adaptation_drafts/`，**不会**写入 opendbc。

8. **导出**  
   - `export_adaptation_bundle` 获取全部文本 + PR checklist。  
   - 拷到 PC，按 checklist 修改 `opendbc` 并编译 fork。

### 阶段 D：开发机合入（人 · 必须）

9. 在 `opendbc/car/fingerprints.py` 添加指纹。  
10. 注册 `interface.py`、补全 CarState/CarController/CarParams。  
11. 核对 **checksum**、**counter**、**扭矩限幅**。  
12. 本地仿真 / replay（若有路线日志）。

### 阶段 E：路试（人 · 必须）

| 步骤 | 内容 |
|------|------|
| E1 | 静止：设备识别车型、无 critical fault |
| E2 | 封闭场地 &lt; 20 km/h：仅看状态帧是否合理 |
| E3 | 开启 LKAS/ACC 测试：先轻转、再跟车 |
| E4 | 记录 `grep_log` / onroad 事件，回到阶段 B 迭代 |

**op助手写确认**：`save_adaptation_draft`、`write_params` 等写操作均需静止 + 确认，行驶中会被拦截。

---

## 五、SecOC / TSK 车型专章（丰田/雷克萨斯等）

### 5.1 原理（一句话）

丰田在部分车型的**横向控制 CAN 报文**末尾加了 **SecOC 认证码**。没有本车 **SecOCKey**，openpilot 发出的转向指令会被 ECU 拒绝 → 表现为 **dashcam only** 或 **无法 engage**。

这与「写 DBC」是**两件事**：**先密钥，后适配**。

### 5.2 判断你是否是 SecOC 车

- 在 [optskug/docs 车型列表](https://github.com/optskug/docs#cars) 查年款/产地。  
- 日志/DBC 中出现 `SECOC_SYNCHRONIZATION`（如 `0x0F`）、`STEERING_LKA` 带认证尾缀。  
- 设备提示 unrecognized / dashcam，且社区标明 TSK。

### 5.3 标准密钥提取（🟢 车型）

**以 [optskug/docs Setup Guide](https://github.com/optskug/docs#setup-guide) 为准**，概要：

1. 在家安装 **TSK Manager** 自定义软件（C4 / C3X: `optskug/tskm`；C3 见文档内 C3 URL）。本 fork 内置 TSK 于 op 助手 `:5090`，无需单独装 tskm。  
2. 车内接 harness + Comma Power，按文档进入 **Not Ready To Drive**（勿长时间耗电）。  
3. 按 TSK Manager 向导对 **EPS** 执行提取（硬件 exploit，**每台车密钥不同**）。  
4. 得到 **32 位十六进制 SecOCKey**。

### 5.4 写入 Dragonpilot / 设备

本 fork 在 **Dashy 开发者** 中提供 SecOCKey 安装项（`SecOCKey` Param），也会同步到设备路径（见 `dragonpilot/dashy/serverd.py`）。

- 在 Dashy 设置 → Developer → **SecOCKey Install** 填入 32 位 hex。  
- **切勿**把真实密钥发给 AI、贴到公开仓库或 Discord 公开频道。  
- op助手策略：**不会**代写 `SecOCKey`（敏感 Param 禁止自动写入）。

写入后需使用**支持 SecOC 的 fork/构建**（上游 release 通常不支持 SecOC，见 `CARS.md`）。

### 5.5 实验路径（🟡，如 2024 Sienna）

若你在 🟡 列表：

1. 阅读 [Vance425 笔记](https://github.com/Vance425/ToyotaSienna2024OpenpilotAnalysis-_Note) 了解 `0x2E4` / `0x131` / DataFlash 等术语。  
2. 跟随 [Bk2ol 实验仓库](https://github.com/Bk2ol/tsk_extraction_by_can_log)（或 Discord 最新推荐工具）。  
3. 准备：**EPS 版本号**、制造年月、US/国产、完整 CAN 日志、提取成败记录。  
4. 密钥验证通过后，同样用 Dashy 写入 `SecOCKey`，再走第四节的路试。

**AI 在此阶段的角色**：解释日志里**哪些帧是 steering command**、对照笔记里的 ID 表、帮你整理 NOTES.md — **不能**代替 EPS 编程或 oracle 暴力破解。

### 5.6 🔴 无法破解时

- 不要继续投入「写 DBC」期望能转向。  
- 可：dashcam 记录、向 `#toyota-security` 提供匿名日志、关注 optskug/I-CAN-hack 更新。  
- 2024+ 很多车型 ciphertext 日志对研究价值有限，直到有人攻破新 EPS/HSM。

---

## 六、「锁止」（Lockout）适配说明

「锁止」在不同品牌含义不同，**不是 SecOC**，但也常导致 **无法 engage 或转向中断**。

### 6.1 大众 / 奥迪 / 斯柯达（VAG）— EPS Lockout

**现象**：低速或停车后 EPS 拒绝助力，openpilot 报转向相关 fault。

**Dragonpilot 调优**：

- 设置项：`dp_vag_avoid_eps_lockout`（**Avoid EPS Lockout**）  
- 作用：低速时**降低转向扭矩请求**，避免触发 EPS 保护性锁止。  
- 路径：Dragonpilot 设置 → VAG 分区（仅 VAG 品牌显示）。

**适配建议**：

1. 确认车型指纹与 `opendbc` VAG 条目一致。  
2. 先关闭激进横向参数，在封闭场地低速试 `engage`。  
3. 若仍锁止：让 AI `snapshot_tune_state` + `list_dp_settings` 检查横向增益；开启 `dp_vag_avoid_eps_lockout` 后重试。  
4. CarController 里扭矩斜率/上限需符合该车型 EPS 规范（草稿阶段在 `carcontroller.py.snippet` 注明限幅）。

### 6.2 本田 / 讴歌 — LOW_SPEED_LOCKOUT

**现象**：`carState` 里 `steerFaultTemporary`、EPS 状态 `LOW_SPEED_LOCKOUT`（低速正常现象，过高车速仍锁止则异常）。

**适配建议**：

1. `read_onroad_events` + `grep_log` 搜 `steer`。  
2. 确认 `minSteerSpeed` / 车型 CarParams 与 opendbc 本田定义一致。  
3. 部分车型需正确解析 `STEER_STATUS`；DBC 错误会导致误报 fault。  
4. AI 可对照已有本田 DBC 帮你比对信号，但需人路试验证。

### 6.3 丰田 — ACC / PCM 低速锁止

**现象**：`PCM_CRUISE_2` 的 `LOW_SPEED_LOCKOUT` 导致纵向或跟车异常（与 SecOC 不同）。

**适配建议**：

1. 先排除 SecOC（第五节）。  
2. 检查是否 `openpilotLongitudinalControl`、雷达 ACC 车型特殊逻辑（`RADAR_ACC` 等）。  
3. 对照 `opendbc/car/toyota/carstate.py` 中 lockout 处理注释。  
4. Dragonpilot 纵向相关 `dp_*` 由 `list_dp_settings` 列出，勿盲目开大跟车激进度。

### 6.4 福特 TRON（另一类 CAN 安全）

部分新款福特使用 **TRON**（类似 SecOC 的 CAN-FD 安全），与丰田 SecOC 不同。  
参考：[BluePilot TRON 状态列表](https://bluepilot.dev/2025/08/13/confirmed-tron-status-list/)。  
**当前 upstream openpilot 对 TRON 平台为 dashcam only**，适配路径与丰田 SecOC 不同，需单独社区方案。

---

## 七、在 op助手里怎么用 AI 协作

### 推荐对话示例

```
我是一辆 2022 丰田 XXX，目前 unrecognized。已确认不是 SecOC 列表里的 🔴 车型。
我已附上 Cabana 抓的 CAN ID 列表，请按适配指南：
1. 对照 list_dbcs 找相近 DBC
2. cabana_analyze 分析这些帧
3. 生成 fingerprint + dbc 草稿
4. save_adaptation_draft 保存到项目 adapt_xxx
```

SecOC 车：

```
我是 2021 RAV4 Prime，正在按 optskug 文档提取 SecOCKey。
请根据 read_params 和 cabana 日志，帮我确认是否出现 STEERING_LKA / 0x2E4，
并说明写入 SecOCKey 后还应检查哪些 Dragonpilot 设置。
不要让我把密钥贴到聊天里。
```

### 技能与知识库

- 设置 → **技能** → 开启「车辆适配」。  
- 可将 [optskug/docs](https://github.com/optskug/docs) 的**公开章节**摘要粘贴到 **知识库**（向量检索），便于对话引用 — **不要上传含密钥的内容**。

---

## 八、常见问题

| 问题 | 回答 |
|------|------|
| AI 能自动发 PR 合入 opendbc 吗？ | **不能**，只出草稿 bundle。 |
| 只有 DBC 没有 SecOCKey 能转向吗？ | **不能**（SecOC 车）。 |
| 2024 Sienna 一定可用吗？ | **不一定**；看 EPS 版本与产地，见 🟡/🔴 列表与 Vance425 笔记。 |
| C3 上能跑本地 embedding 吗？ | 不推荐；用云端 embedding + 车机向量检索即可。 |
| 行驶中能保存草稿吗？ | **不能**；写操作需静止并确认。 |

---

## 九、参考链接

| 资源 | 链接 |
|------|------|
| 丰田 SecOC 总文档 | https://github.com/optskug/docs |
| SecOC 密钥提取原理 | https://icanhack.nl/blog/secoc-key-extraction/ |
| 2024 Sienna 研究笔记 | https://github.com/Vance425/ToyotaSienna2024OpenpilotAnalysis-_Note |
| comma 车型 / SecOC 说明 | `opendbc_repo/docs/CARS.md` |
| I-CAN-hack secoc 工具 | https://github.com/I-CAN-hack/secoc |
| comma Discord | https://discord.comma.ai（#toyota-security） |

---

## 十、修订记录

- 2026-07：初版，配合 op助手 `adaptation_drafts`、向量 RAG、车辆适配技能。
