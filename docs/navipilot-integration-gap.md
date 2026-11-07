# navipilot（CP 搭子）对接缺口

`navipilot`（`github.com/jixiexiaoge/navipilot`）是本车机配套的 Android App。它**不是**
CarrotNavi APK：端口布局与主通道都不同，排查前必须先分清，否则会得出错误结论。

本文记录 2026-09-27 实测 + 源码核对的结果。

## 1. 「7705 Active = 未激活 — CEM暂停」的成因（已确认，非故障）

App 侧指示器的取值（`ui/components/AutoSwitchExperimentPage.kt`）：

```kotlin
val isActive = carrotManFields?.value?.active ?: false
Text(if (isActive) "已激活 — CEM可工作" else "未激活 — CEM暂停")
```

`active` **只**来自设备 UDP 7705 广播的 JSON（`CarrotManDataModels.kt`：

> `// comma3 7705 接收状态（仅 active 被 app 读取）`

而设备侧这个字段就是 openpilot 的接管状态（`carrot_man.make_send_message`）：

```python
active = False
if self.sm.alive.get('selfdriveState', False):
  active = bool(self.sm['selfdriveState'].active)
msg['active'] = active
```

**激活条件 = 设备 7705 广播里 `active == true`，即车在行车上且 openpilot 已接管
（`selfdriveState.active`）。** 停车或未接管时为 `false`。

2026-09-27 实测（设备 192.168.2.246，停车）——信标本身完全正常，5 秒收到 8 个报文：

```json
{"Carrot2":"2026.003.000","IsOnroad":false,"CarrotRouteActive":false,
 "ip":"192.168.2.246","port":7706,"active":false,"xState":0,
 "v_ego_kph":0,"v_cruise_kph":0,"tbt_dist":0,"sdi_dist":0,
 "navi_http_port":7713,"nRoadLimitSpeed":0,"vTurnSpeed":55, ...}
```

字段齐全（sp 的信标是 CarrotPilot 的**超集**：cp 16 键 + `goalPosX/goalPosY/
szGoalName/nRoadLimitSpeed/vTurnSpeed`），所以「未激活」不是发现失败、不是缺字段、
也不是网络问题——**上路接管后会自动变成「已激活 — CEM可工作」**。

CEM 的前置条件同样印证（`ConditionalExperimentManager.kt`）：

```kotlin
if (!prefs.getBoolean("cem_enabled", false)) return false
// 前提：7705 active 必须为 true
if (carrotManFields == null || !carrotManFields.active) return false
```

## 2. 端口矩阵（sp 现状 vs navipilot 需求）

| 端口 | navipilot 用途 | sp 现状 |
|---|---|---|
| UDP 7705 | App 监听设备发现广播，读 `active` | ✅ 已实测在发（carrot_man + carrot_navi 双源） |
| UDP 7706 | 导航数据上行（GPS/限速/TBT/电子眼，5 Hz） | ✅ |
| TCP 7709 | 路线点 | ✅ |
| ZMQ 7710 | 控制命令（超车变道） | ✅ `carrot_man` `bind tcp://*:7710` |
| TCP 7711 | 车辆/模型数据（旧版接收器保留） | ✅ `xiaoge_data` |
| HTTP 7713 | sinf 交通灯上行 | ✅ `carrot_man._navi_http_port` |
| 7714 | v2 navi | ✅ |
| **WS 7000 `/ws/raw_multiplex?services=`** | 实时 cereal 数据（主要通道） | ❌ **缺** |
| **WS 7000 `/ws/camera/road`** | 摄像头 H.264 预览 | ❌ **缺** |
| **HTTP 7000 `/api/param_set`、`/api/params_bulk`** | 参数读写 | ❌ **缺** |
| **HTTP 8082 `/store_toggle_values`** | 下发设置 | ❌ 8082 是小鸽 V-ASM 页面，无此端点 |

**这就是 App 弹「❌ 切换失败: 设备未连接」的原因**：CEM 切换走的是
`paramClient.setParam("ExperimentalMode", …)` → HTTP 7000（`CarrotParamClient.kt`
`private const val PORT = 7000`），而本仓库没有任何 7000 服务。

## 3. 待补的 7000 层（来自 CarrotPilot 的对应模块）

navipilot 实际只用 4 个端点，对应 cp 的路由表（`server/features/ws.py`）：

```
/ws/compact_state      (可选，App 未使用)
/ws/raw_multiplex      <- App 主通道
/ws/raw/{service}
/ws/camera/{camera}    <- App 用 road
```

| cp 模块 | 行数 | 作用 |
|---|---|---|
| `realtime/raw_protocol.py` | 37 | 多路复用帧格式（`encode_raw_multiplex_frame` / `build_raw_multiplex_hello`） |
| `realtime/raw_services.py` | 45 | 可用服务清单 |
| `realtime/transports/raw_ws.py` | 325 | `RawWsHub` |
| `realtime/transports/camera_ws.py` | 471 | `CameraWsHub` |
| `server/features/ws.py` | 99 | 4 条 ws 路由 |
| `server/features/params.py` | 310 | `/api/param_set`、`/api/params_bulk` |
| （可选）`realtime/compact_state.py` | 652 | 紧凑状态 + C++/Cython 原生部分 |

**合计约 1,290 行**（不含 compact_state）。注意这**远小于** cp 的 `server/`(30k) +
`web/`(148k)——那些是它自己的网页管理台，navipilot 并不需要。也就是说给 navipilot
补一个**最小 7000 服务**是可行且有边界的，不必整套搬。

另需在 8082 上补一个 `POST /store_toggle_values`（sp 的 `v_asm_server` 目前只有
`/`、`/api/status`、`/api/config`、`/api/snapshot`、`POST /api/config`、`POST /api/settings`）。

## 4. 结论

- **7705「未激活」= 没接管，不是故障**，无需修设备端。
- App 真正缺的是 **7000 端口的实时数据 + 参数 API**，以及 8082 的
  `/store_toggle_values`。
- ZMQ 7710、7706、7709、7711、7713、7714 都已具备。
