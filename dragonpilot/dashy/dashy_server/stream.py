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

"""Telemetry publisher: the source of the SSE stream.

The stream is one-way (server -> browser), so it's SSE, not a WebSocket. This
one thread polls the dashyState SubMaster and stores the latest frame in shared
app state; each SSE connection (its own request thread, see http.py) streams
that buffer to its client. stream_latest is written before stream_seq is
bumped, so a reader that sees a new seq is guaranteed the matching frame."""

import time

from cereal import messaging

from .config import logger


def _publisher_loop(app_state, stop_event):
  # ZMQ sockets are thread-affined: build + poll the SubMaster on this thread.
  try:
    sm = messaging.SubMaster(['dashyState'])
  except Exception as e:
    logger.warning(f"Publisher disabled (SubMaster init failed): {e}")
    return

  logger.info("dashyState publisher loop started")

  while not stop_event.is_set():
    try:
      sm.update(0)
      if sm.updated['dashyState']:
        json_data = sm['dashyState'].json
        app_state['stream_latest'] = json_data.encode() if isinstance(json_data, str) else json_data
        app_state['stream_seq'] += 1
      time.sleep(0.01)
    except Exception as e:
      # Don't let a transient error tear down the loop silently.
      logger.exception(f"Publisher loop error: {e}")
      time.sleep(0.1)
