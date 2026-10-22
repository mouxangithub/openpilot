# sunnylink/ - SP CLOUD PLATFORM

sunnypilot's parallel cloud-services stack (analog to comma's athena/api). 40+ files. See [openpilot/sunnypilot/AGENTS.md](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/AGENTS.md) for fork conventions.

## STRUCTURE

```
sunnylink/
├── api.py                    # API client (stg.api.sunnypilot.ai by default)
├── athena/                   # Daemon parallel to comma's athenad
│   ├── manage_sunnylinkd.py  # Wrapper that registers + spawns sunnylinkd
│   └── sunnylinkd.py         # Long-lived RPC client (websocket + JSON-RPC)
├── backups/                  # AES-encrypted device-state backup/restore
│   ├── manager.py            # Backup orchestrator
│   ├── AESCipher.py          # Encryption helper
│   └── utils.py
├── docs/                     # Schema reference docs (autogen targets)
├── settings_ui_src/          # YAML SOURCE for settings UI (edit here)
├── tools/                    # Settings-UI compiler chain - see "Settings UI" below
├── tests/                     # unittest tests for capabilities, params, signing
├── capabilities.py           # Capability discovery (server features advertise)
├── registration_manager.py   # Device registration daemon
├── statsd.py                 # SP-specific telemetry (statsd_sp process)
├── sunnylink_state.py        # Cached client state
├── uploader.py               # Optional uploader (only present file conditionally)
├── utils.py                  # sunnylink_ready(), sunnylink_need_register(), etc.
├── settings_ui.json          # COMPILED output - DO NOT hand-edit
├── settings_ui.schema.json   # JSON-schema for validation
└── params_metadata.json      # Param descriptions/units/range (compiled)
```

## SETTINGS UI PIPELINE (CRITICAL)

The settings UI is **compiled** from YAML source. The `.json` files in this dir are GENERATED.

```
settings_ui_src/*.yaml  --[apply_macros.py]-->  --[compile_settings_ui.py]--> settings_ui.json
                                                                              ^
                                                                              |
                                                              schema check via validate_settings_ui.py
```

| Tool | Purpose |
|------|---------|
| [tools/apply_macros.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/sunnylink/tools/apply_macros.py) | Expand reusable YAML fragments |
| [tools/compile_settings_ui.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/sunnylink/tools/compile_settings_ui.py) | YAML -> JSON |
| [tools/extract_settings_ui.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/sunnylink/tools/extract_settings_ui.py) | Reverse: JSON -> YAML (rare) |
| [tools/generate_settings_schema.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/sunnylink/tools/generate_settings_schema.py) | Regenerate schema after struct changes |
| [tools/validate_settings_ui.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/sunnylink/tools/validate_settings_ui.py) | Schema-validate `settings_ui.json` |

## REGISTRATION & KEYS

- Device registers via `registration_manager` (background daemon)
- Uses **elliptic curve keys** (Ed25519) - keys generated on first boot, persist across reinstalls
- Param keys: `SunnylinkEnabled`, `SunnylinkdPid`, `SunnylinkRegisteredHash`, etc.
- Status helpers in [utils.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/sunnylink/utils.py): `sunnylink_ready(params)`, `sunnylink_need_register(params)`, `use_sunnylink_uploader(params)`

## ANTI-PATTERNS (THIS DIR)

- **NEVER hand-edit `settings_ui.json`, `settings_ui.schema.json`** - they are compiled outputs. Edit `settings_ui_src/*.yaml` then re-run the compile chain.
- **NEVER block remote modification of `GithubSshKeys`** is intentional - server CANNOT push SSH keys ([CHANGELOG ref](file:///Users/cyonsun/Documents/Code/sunnypilot/CHANGELOG.md)).
- **NEVER store unencrypted backup payloads** - all device-state backups must go through `AESCipher`.
- **DO NOT call sunnylink endpoints directly from daemons** - go through [api.py](file:///Users/cyonsun/Documents/Code/sunnypilot/openpilot/sunnypilot/sunnylink/api.py) so retry/auth is consistent.

## NOTES

- API base URL is configurable via Param `SunnylinkApiUrl` (default points to staging `stg.api.sunnypilot.ai`).
- `manage_sunnylinkd` runs **always** (offroad+onroad); the inner `sunnylinkd` only connects when `sunnylink_ready()`.
- `backup_manager` runs offroad only AND requires `sunnylink_ready` - check process_config.py.
- Tests heavily mock the API - real HTTP calls are gated behind env vars. Run: `./tools/op.sh test openpilot/sunnypilot/sunnylink`.
