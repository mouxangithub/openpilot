# Control protocol

How the apps and the status page talk to the server. There is no socket: each
runs the server in its own process and uses `ServerController` (in
`JetlinkKit/Sources/JetlinkServer`) directly.

| Who | How |
| --- | --- |
| Mac and iPhone apps | Swift calls: `handle(_:)` runs a `ControlCommand`, `events` delivers each `ControlEvent` |
| Android app | Each command as a JSON object through JNI (`Native.command`), a JSON reply back; the screens draw a snapshot built from the events |
| Status page (Jetson, PC) | Listens only, never sends a command; relays events to browsers as Server-Sent Events |

It has no version number: every caller is built with the server it talks to.
The JSON below is what
`ControlEvent.jsonLine()` writes and the page streams: one object per line,
snake_case keys, sorted. An optional field with no value is left out, and a
reader takes a missing key as `null`; the examples below show such fields as
`<value>|null`.

## The status page

`jetlink-server --status-port P` (the installed service uses 5600) serves, to
any browser on the network, read-only and without a login:

| Path | What |
| --- | --- |
| `/` | the page |
| `/events` | Server-Sent Events: on connect the latest `hello`, `server`, `link`, `engine` and `inventory`, the last two minutes of `stats`, then `host` and one `hw` a second while a page is open |
| `/logs` | the server's last 300 log lines, as text |

```bash
curl -N http://<name>.local:5600/events
```

`host` (hostname, board, OS, kernel, GPU) and `hw` (CPU, memory, GPU,
temperatures, power, fan, disk) come from the Linux host; other hosts leave
them out.

## Events

`{"event": "<name>", "t": <unix time, float seconds>, ...}`. Placeholders in
angle brackets.

```jsonc
{"event":"server","t":0,"state":"serving","detail":"","backend":"trt",
 "runtime_version":"10.16.2.10","device":"Orin-sm87"}
// state: "serving" | "stopping". backend, runtime_version and device are what
// the hello to the comma carries.

{"event":"link","t":0,"state":"connected","detail":"","peer":"usb","medium":"usb3"}
// state: "waiting" | "connected" | "disconnected". medium, when connected:
// "usb3" | "usb2" | "usb1" | "usb" (speed unknown) | "tcp", from the comma's
// hello (a phone's cable is TCP over USB). Transitions only.

{"event":"engine","t":0,"state":"building","sha256":"<sha256>","detail":"",
 "stage":"build","frac":0.42,"msg":"","load_only":false}
// state: "none" | "building" | "loading" | "ready" | "failed". Every state
// change, and progress at most 4 times a second.

{"event":"stats","t":0,"frames":20,"fps":19.9,"slow":0,"window_s":1.0,
 "total_ms":{"mean":17.0,"p99":17.4,"max":18.1},"served_ms":{"mean":17.4,"p99":17.9,"max":18.6},
 "gpu_ms":{"mean":15.7},"stages_ms":{"queue":0.5,"gpu":15.7,"other":0.8,"send":0.4}}
// Once a second while frames arrive. total_ms: arrival to reply ready;
// served_ms adds the send; stages_ms are means that add up to served_ms.mean.
// slow: frames whose total was over 60 ms.

{"event":"inventory","t":0,"loaded":"<sha256>|null","last_loaded":"<sha256>|null",
 "models":[{"sha256":"<sha256>","bytes":765953504,"path":"<cache>/models/<sha16>.onnx",
            "name":"Cinque Terre V3 Model","ref":"<ref>|null"}],
 "artifacts":[{"sha256":"<sha256>","key":"<sha16>.ort1.29.0.coreml-Apple_M1_Pro",
               "path":"<cache>/engines/<sha16>.ort1.29.0.coreml-Apple_M1_Pro.ortcache",
               "bytes":2300000000,"backend":"ort","runtime_version":"1.29.0","device":"coreml-Apple_M1_Pro",
               "built_at":"<ISO 8601>|null","build_seconds":8.2,"checkpoint":"<id>|null","current":true}],
 "disk":{"models_bytes":765953504,"engines_bytes":2300000000,"free_bytes":120000000000}}
// A Mac's. current: this server would load that artifact. After builds,
// loads, downloads, imports, forget, and the inventory command.

{"event":"catalog","t":0,"fetched_at":1757440000.0,"url":"<catalog url>",
 "default_ref":"<ref>","error":"<why>|null",
 "models":[{"name":"Cinque Terre V3 Model","short_name":"CTV3M","ref":"<ref>",
            "build_time":"<ISO 8601>","index":13,"sha256":"<sha256>|null","bytes":765953504}]}
// Newest first. sha256 and bytes are null until that ref's pointer is
// resolved. error is set when a refresh failed and this is the cached list.

{"event":"download","t":0,"sha256":"<sha256>","ref":"<ref>|null","state":"progress",
 "frac":0.42,"bytes":321000000,"total":765953504,"rate_bps":41000000.0,"detail":"","source":"<url>"}
// state: "started" | "progress" (at most 4 a second) | "done" | "failed" | "cancelled".

{"event":"import","t":0,"path":"<file>","state":"hashing","frac":0.3,"sha256":"<sha256>|null","detail":""}
// state: "hashing" | "copying" | "done" | "failed".

{"event":"benchmark","t":0,"state":"running","elapsed":12.0,"total":60.0,"frames":240,
 "frame":{...},"report":{...}|null,"detail":""}
// state: "running" | "done" | "cancelled" | "failed"; report when done.

{"event":"shutdown_request","t":0,"reason":"<why>"}
// The comma asked a phone or Mac to power off; the apps refuse and say so.

{"event":"hello","t":0,"version":"0.7.0"}
// The status page's first event: the server's version, as
// `jetlink-server --version` prints it.
```

## Commands

`{"cmd": "<name>", ...arguments}`, answered by one reply:
`{"ok": true, ...extras}` or `{"ok": false, "error": "<sentence>"}`.

| cmd | arguments | reply extras | behaviour |
| --- | --- | --- | --- |
| `status` | | | re-sends `server`, `link`, `engine`, `inventory`, `catalog` |
| `catalog` | `refresh` (default false) | `queued: true` | fetches the catalog if asked, or if the cache is missing or over an hour old, resolves missing pointers, then emits `catalog` |
| `download` | `ref` or `sha256` | `sha256` | queues a download (one at a time, in order); `download` events follow |
| `cancel_download` | `sha256` | | cancels it and removes the `.part` |
| `import` | `path` | `queued: true` | hashes and copies the file in; `import` events, then `inventory` |
| `prepare` | `sha256`, `frame_skip` (default 4) | `state`; `sha256` when downloading | builds if needed and loads it. With no model file or engine on disk it downloads first and replies `state: "downloading"` |
| `unload` | | | releases the loaded engine |
| `forget` | `sha256`, `artifacts` (default true), `model` (default false) | | unloads it if loaded, deletes its engines and/or download, then `inventory` |
| `inventory` | | | emits `inventory` |
| `benchmark` | `seconds` (default 60, up to 3600) | `queued: true` | runs the loaded model at the comma's pace with no comma; `benchmark` events. Refused while a comma is connected |
| `cancel_benchmark` | | | stops it |
| `shutdown` | | | emits `server` with `stopping`; the app stops the server |
