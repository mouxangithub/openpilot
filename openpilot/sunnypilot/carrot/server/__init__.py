"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Carrot HTTP/WebSocket API server (port 7000).

CarrotPilot serves its app API from `selfdrive/carrot/server/` on port 7000, and the
companion app (navipilot / CP 搭子) treats 7000 as its main channel: the parameter REST API
plus the raw and camera WebSockets under `/ws/`. This fork only had the 8088 nav-params
panel, so the app reported "设备未连接" and its conditional-experiment mode could not switch.

The layout mirrors CarrotPilot's (`server/features/...`, `server/services/...`) so the
remaining endpoints can be ported mechanically, but every module here reads and writes
through sunnypilot's own interfaces - `Params` for state and cereal for live data - so the
fork keeps a single control path.
"""
