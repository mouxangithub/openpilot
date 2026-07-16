# Copyright (c) 2026, Rick Lan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, and/or sublicense,
# for non-commercial purposes only, subject to the following conditions:
#
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
# - Commercial use (e.g. use in a product, service, or activity intended to
#   generate revenue) is prohibited without explicit written permission from
#   the copyright holder.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Dashy server package.

The HTTP server for the dashy web UI, split from the former monolithic
serverd.py. Built on the Python standard library (http.server) — openpilot
dropped aiohttp upstream (PR #38226), and the dashy API is a small REST surface
plus a one-way SSE telemetry stream, which the stdlib serves without a framework.

Module layout (dependencies point downward, no cycles):
  config       constants + shared logger
  habit        pure accel-log habit-overlay math
  i18n         language sync + translation map
  params_util  SETTINGS allowlist, condition eval, param read/write
  cache        AppCache (Params, CarParams, settings context)
  http         request/response shim + threaded server + request handler
  stream       dashyState publisher loop (SSE source)
  handlers     the REST endpoint functions + route table
"""
