"""Carrot realtime helpers that need no aiohttp.

Only the compact-state encoder lives here. CarrotPilot's `realtime/` also carries the raw
transport, but this fork already has it elsewhere: `server/services/raw_protocol.py`,
`raw_services.py`, `raw_relay.py` and `server/features/ws.py`.
"""
