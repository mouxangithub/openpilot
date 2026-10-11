# 7000 与当前项目的设置融合：现状、错位与方案

> 2026-10-11。基准：sp = `E:/sp`（branch `test`，`0bb80bd99`），设备 = C3 `192.168.2.233`。
> 所有数字都在设备上实测或从仓库文件统计得出，不是估算。

## 0. 结论速览

7000 上现在**并存两套设置目录**，面板显示一套、档案/热门值/预设工作在另一套：

| 消费者 | 目录来源 | 参数数 |
|---|---|---|
| `/api/settings`、`/api/settings/snapshot`（面板显示的） | sp `carrot/config.py::_DEFAULT_NAV_PARAMS` | **187** |
| `popular_values`、`setting_profiles`、`intro`、`services/params.py` | cp `carrot_settings.json` | **184** |

交集 141；**46 个面板可见的参数进不了档案、也不会被"热门值"采集**；**43 个 cp 目录里的参数 sp 根本没声明**（读会返回默认、写会 400）。

在此之上还有两个更大的问题：

- **覆盖率**：`params_keys.h` 声明了 **580** 个参数，面板只显示 **230**（sp ∪ cp 目录），**383 个完全看不到**——sunnypilot 52、mapd 20、sunnylink 13、力矩调参 12、Model Manager 12、Toyota 5、MADS 4 …
- **形状**：面板的 `by_name` 只有 `{name, default, type, group}`，**没有标签、没有取值范围、没有菜单树**（`categories` 缺失）→ 前端退化成"按 key 前缀分组的平铺列表"，而 cp 的设计是带 ko/en/zh 标签的三级菜单。

## 1. 设备实测证据

```
/api/settings/snapshot -> 200, catalog=187
  groups: ['display','general','lateral','longitudinal','navi','speed']   ← 按 key 前缀分组
  has categories: False                                                   ← 无菜单树
  by_name sample: {"name":"AutoTurnDistOffset","default":0,"type":"int","group":"navi"}

/api/setting_popular_values -> 200
  panel catalog (sp)          : 187
  popular-values catalog (cp) : 184
    only in panel (进不了档案/热门值): 46   e.g. AutoForkDistOffset, AutoTurnDistOffset, BsdDelayTime …
    only in cp catalog (sp 未声明)  : 43   e.g. CanfdHDA2, CruiseButtonTest1, HyundaiCameraSCC …

写路径正常（单一）：param_set AutoForkDistOffset 30 -> 11，snapshot 立刻回读 11 ✓
```

`UnifiedParams.get()` 是**真 Params 优先、JSON 缓存兜底**，所以值读取是实时的，这部分没问题。

## 2. 四组缺口（精确清单）

| 组 | 含义 | 数量 | 处置 |
|---|---|---|---|
| **A** | cp 目录有、**sp 未声明** | 33 | **必须不显示**（写会 400）。用 `params_keys.h` 过滤 |
| **B** | cp 目录有、sp 已声明但不在 sp 的 carrot 默认表 | 10 | **可安全补进面板** |
| **C** | sp 的 carrot 默认表有、cp 目录没有 | 46 | **sp 特有**，需要在菜单里给位置 |
| **D** | 两份目录都没有、sp 已声明 | 383 | 见 §3 的分类 |

B 的 10 个：`AutoCruiseControl`、`AutoGasCancelSpeed`、`AutoGasTokSpeed`、`AutoRoadSpeedAdjust`、`AutoSpeedUptoRoadSpeedLimit`、`HapticFeedbackWhenSpeedCamera`、`PaddleMode`、`SoftHoldOnCancel`、`StopDistanceCarrot`、`UseLaneLineSpeed`

C 的 46 个主要是 sp 的自动变道/路口系列：`AutoCurveSpeed*`、`AutoDoFork*`、`AutoFork*`、`AutoUp*`、`AutoTurn*`、`BsdDelayTime` …

## 3. D 的 383 个里，哪些是"设置"、哪些是"状态"

**不能整包丢给面板**——里面混了大量运行时状态：

| 前缀 | 数量 | 性质 |
|---|---|---|
| `Carrot*` | 27 | 混合（部分是设置，部分如 `CarrotNaviCompositionState` 是状态） |
| `Offroad*` | 21 | **状态**（`OffroadMode` 等） |
| `Is*` | 13 | **状态**（`IsOnroad`…） |
| `Last*` | 12 | **状态**（`LastUpdateTime`…） |
| `Updater*` | 9 | **状态** |
| `Live*` | 7 | **状态** |
| `Lateral*` / `Longitudinal*` / `Model*` / `Speed*` / `Osm*` / `Sunnylink*` / `Toyota*` | 14+13+14+8+10+9+7 | **大多是设置** |

**关键洞察**：sp 已经把"哪些参数是设置、归在哪个页面"这件事编码在了**车机设置页源码**里——
`openpilot/selfdrive/ui/sunnypilot/layouts/settings/*.py`。设备上扫出来是 **19 个页面 / 348 个键**：

```
alpha_longitudinal_toggles, bluetooth_settings, carrot_tuning, carrot_tuning_egpu,
cruise, developer, device, display, models, navigation, ...
```

这正是我此前给 8088 面板写的 `carrot/web_settings.py::scan_ui_pages()` 在做的事——
**用车机页面本身当分组的单一事实源**，而不是在服务端再维护一份。

所以 D 不需要"挑"，**用这个扫描结果就是现成的、经车机 UI 审过的设置集**。

## 4. 方案

### 原则

1. **一个目录**：面板、档案、热门值、预设必须读同一份。现在分裂的根因是 `/api/settings` 走 `settings_sp`（前缀分组）、其余走 cp 的 `carrot_settings.json`。
2. **只显示已声明的键**：一律以 `params_keys.h` 为准（A 组必须过滤掉）。
3. **不重复造目录**：sunnypilot 的设置分组已经有权威来源（车机页面源码），扫描它而不是重写一份。
4. **写路径不动**：`/api/param_set` 仍是唯一写入口（已验证工作正常）。

### 落地（三步，可分开提交）

**第 1 步 — 统一目录（修错位）**

让 sp 的 `/api/settings` 也读 `carrot_settings.json` 那份（即 cp 的 `get_settings_cached()`），
于是面板、档案、热门值、预设四者天然一致；同时面板**白拿** cp 的标签/范围/菜单树。

配套：把 `carrot_settings.json` 里 **sp 未声明的 33 个键删掉**（否则面板会给出写不进去的控件），
并把 **B 组 10 个**补进去。

**第 2 步 — 补齐 sp 特有（C 组 46 个）**

C 组都在 sp 的 carrot 默认表里、只是 cp 目录没有。做法：在生成的目录里给它们一个
`sunnypilot`/`carrot` 分组（用 sp 的 `_DEFAULT_NAV_PARAMS` 的默认值与类型），
标签先用 key 本身（cp 的标签是韩文，sp 这批没有对应文案）。

**第 3 步 — 接入 sunnypilot 设置（D 组）**

新增一个由**车机页面扫描**得出的分组：复用 `carrot/web_settings.py::scan_ui_pages()` +
`group_keys()`（已在 8088 面板上验证可用，设备实测 19 页 / 348 键），
以 `params_keys.h` 的声明类型渲染控件。
这样 7000 面板看到的设置与车机自己的 UI 一致，且**不会**把 `IsOnroad` 这类状态当设置暴露出去。

### 与既有三个设置面的关系（避免重复）

| 面 | 端口 | 定位 | 本次动作 |
|---|---|---|---|
| 车机大 UI | 设备屏 | 权威设置界面 | 不动，作为 §3 的扫描源 |
| `webui` 子模块 | 5080 | 大 UI 的镜像（`panel_catalog.py`，38 面板 / 218 参数，带标签与描述） | 不动 |
| carrot 小面板 | 8088 | 车机页面扫描 + nav/radar/models | 不动（其扫描逻辑被第 3 步复用） |
| **CarrotPilot 面板** | **7000** | **carrot 调参面 + sunnypilot 设置** | 本次目标 |

7000 不该变成"580 个参数的转储"——它是 **carrot 调参 + sunnypilot 设置**两个面，
状态类键不进去。

## 5. 风险

- 切 `/api/settings` 到 cp 的目录会**改变面板的分组与文案**（前缀分组 → cp 的菜单树）。这是想要的，但属可见变化。
- `carrot_settings.json` 是 cp 的 vendored 文件。**不直接改它**，而是生成一份 fork 版（`carrot_settings_sp.json`）
  并让 `DEFAULT_SETTINGS_PATH` 指过去，这样上游那份保持可再同步。
- 第 3 步引入的 348 个键里有 `developer` 页的参数（如 `ShowDebugInfo`），要确认它们不是"仅开发者"才该显示。

## 6. 待确认

- 第 1 步会把面板从"按前缀分组的 187 项"变成"cp 菜单树的 184 项 + B 组" —— 是否接受分组变化？
- 第 3 步的 sunnypilot 分组要不要**默认折叠**（348 项一次铺开对手机端偏重）？

---

## 7. 落地结果（2026-10-11，已 push `933d2230e`，设备实测）

三步全部实现，设备重启后实测：

| 指标 | 之前 | 之后 |
|---|---|---|
| 面板可见参数 | 187 | **330**（本车经品牌过滤后；生成时 338） |
| 面板分组 | 6 个前缀桶 | **34 组**，菜单树 5 个顶级节点 |
| `categories`（菜单树） | **缺失** | ✅ `DRIVING / VEHICLE / DISPLAY / SYSTEM / SUNNYPILOT` |
| 面板目录 == 档案/热门值目录 | ❌ 187 vs 184 | ✅ **330 == 330，identical** |
| sp 特有 carrot 参数可进档案 | ❌ 46 个不行 | ✅ |
| cp 目录里 sp 未声明的参数 | 43 个会 400 | ✅ 已滤除 |

### 做了什么

1. **`carrot/tools/build_settings_catalog.py`**（新）生成 `carrot_settings_sp.json`：以 cp 的
   `carrot_settings.json` 为骨架（保留 ko/en/zh 标签、min/max/unit、菜单树），做三处改动——
   删掉 sp 未声明的 33 个、补入 sp 特有的 46 个 carrot 参数、补入车机 16 个设置页的 141 个参数。
2. **`DEFAULT_SETTINGS_PATH` 指向新文件**，`features/settings.py` 换成 cp 的版本 →
   面板、档案、热门值、预设、intro 五者读同一份。
3. **车机页面扫描复用**：直接调 8088 面板用的 `carrot/web_settings.py::scan_ui_pages()`，
   两个面板对「某设置属于哪一页」不可能不一致；扫出的 348 个字符串按 `params_keys.h` 过滤成 141 个真实参数，
   类型与默认值同样取自声明。

菜单里 `SUNNYPILOT` 节点分两支：`carrot (sp)`（sp 特有的 46 个，按族分组）与
`On-device settings`（16 个车机页：steering 22、cruise 21、vehicle 14、visuals 13、osm 12…）。

### 覆盖与安全边界

- 覆盖 **338 / 580** 已声明参数（生成时）。剩下的 242 个是**状态类**（`Is*`、`Last*`、`Updater*`、
  `Live*`、`Offroad*`）与未被任何车机页面引用的内部键 —— **有意不暴露**。
- 任何控件都只能由**已声明**的键构建，杜绝「点了写不进去」。

### 与既有三个设置面的关系

车机大 UI、`webui`（5080）、8088 面板均未改动；7000 现在**复用** 8088 的扫描逻辑而非另造一份目录。

### 维护

改完 `params_keys.h`、`carrot/config.py::_DEFAULT_NAV_PARAMS` 或车机设置页之后，重跑：

```bash
python -m openpilot.sunnypilot.carrot.tools.build_settings_catalog
```

## 8. 中文标注与新增栏位（2026-10-11，已 push `bf28d5c86`，设备实测）

187 条 fork 新增参数原先的 `cdescr` 是 "sunnypilot" 占位，`CARROT_SP_UI` 的 16 个页面分组
zh 直接用英文页面名。此轮补齐：

1. **`carrot/tools/sp_param_labels.py`**（新，纯数据表，per-file-ignores E501）：
   每个新增参数一行，四个槽位（en title/descr + zh title/descr），描述按代码实际行为
   （`carrot_serv.py`、sp 横向/纵向）撰写，非望文生义。生成器经 `apply_param_labels()` 消费。
2. **菜单标签**：`FAMILY_LABELS`（carrot (sp) 五族 → 岔路自动驾驶/横向扩展/速度扩展/显示扩展/杂项）、
   `PAGE_LABELS`（16 页 → 转向/巡航/视觉/显示/OSM 地图/导航/行程/车辆/模型选择/开发者/设备/软件/
   Sunnylink/开关/Alpha 纵向控制/Carrot 调校）。`SUNNYPILOT` 节点 zh = "sunnypilot 自有设置"。
3. **新增栏位**：
   - **地图**（`CARROT_SP_MAPS`，9 项）：OsmMapDataEnabled、OsmLocal、MapboxStyle、
     MapTurnSpeedFactor、CarrotMapDecelEnabled（新条目，带标注）、CarrotNaviHudMapProfile、
     ClusterNaviMapTheme/Type/Fps；
   - **IMU 惯性测量**（`CARROT_SP_IMU`，4 项）：ImuCalibrationEnabled/Requested/Status/Matrix
     （本 fork locationd IMU 校准面，带标注）；
   - **模型选择**页并入 `ModelManager_MirrorUrl`/`ModelManager_GithubProxy`（已声明但不在
     cp 目录也不在 defaults，此轮补为条目）；
   - 参数按名去重（同一参数被两个页面扫描到时先到先得），337 条全唯一、0 占位。
4. **cgroup 同步翻译**：flat groups 列表里 maps→地图、imu→IMU 惯性测量、models→模型选择、
   steering→转向。

### 蓝牙为何没有栏位

车机蓝牙页（`bluetooth_settings`）扫出的 24 个键全部是 UI 字符串（Scan/Pair/Forget…），
`params_keys.h` 无任何蓝牙声明键——配对是设备级操作，不存在参数面，7000 无法用参数控件承载；
设备端蓝牙页本身已可用。

### 设备实测（192.168.2.233 @ bf28d5c86）

- `/api/health` ok，`/` 200；
- `/api/settings` 与 `/api/settings/snapshot`：337 items / 35 组，`categories` 树
  `SUNNYPILOT → CARROT_SP(46) + CARROT_SP_UI(144, 16 页) + CARROT_SP_MAPS(9) + CARROT_SP_IMU(4)`；
- 抽查标注：`Mads → MADS 开关`、`AutoUpRoadLimit40KMH → 道路限速上调幅度`、
  `ImuCalibrationEnabled → IMU 校准`、`ModelManager_MirrorUrl → 模型下载镜像`。
