# jetlink host tools

Host-side (Jetson / Linux PC) utilities for the Accelerator Link, adapted from
CarrotPilot's `tools/jetlink/` (MIT, Copyright cp contributors). Self-contained:
stdlib only, no openpilot imports.

| tool | purpose |
|---|---|
| `host_health.py` | read-only host health (thermal, storage, memory) — writes `/dev/shm/carrot-jetlink-health.json`, all work outside the inference path |
| `inspect_jetson.py` | Jetson audit: L4T/JetPack versions, runtime compatibility, model hash check |
| `configure_headless.py` | switch a host to headless (no X/DE) so the full GPU budget goes to inference |

Source: E:/cp commit-era `tools/jetlink/`; paths that referenced carrot-specific
state (`/etc/carrot-jetlink-protected.json`) are kept as-is and are inert unless
that provisioning scheme is in use. Run these on the host, not on the comma.
