"""Tests for WebRTC API bridge (StreamRequestBody compatibility)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class TestWebrtcApi(unittest.TestCase):
  def test_normalize_camera_aliases(self):
    from webui.server.bridge.webrtc_api import _normalize_camera

    self.assertEqual(_normalize_camera("roadCameraState"), "road")
    self.assertEqual(_normalize_camera("wideRoadCameraState"), "wideRoad")
    self.assertEqual(_normalize_camera("driverCameraState"), "driver")
    self.assertEqual(_normalize_camera("unknown"), "road")

  @patch("openpilot.system.webrtc.helpers.post_stream_request")
  @patch("openpilot.system.webrtc.helpers.wait_for_webrtcd")
  @patch("openpilot.system.webrtc.helpers.StreamRequestBody")
  def test_offer_uses_cameras_list(self, mock_body_cls, _wait, mock_post):
    from webui.server.bridge.webrtc_api import webrtc_offer

    mock_post.return_value = {"sdp": "v=0", "type": "answer"}
    mock_body_cls.return_value = MagicMock()

    res = webrtc_offer("v=0", "wideRoadCameraState")

    self.assertTrue(res["ok"])
    mock_body_cls.assert_called_once()
    kwargs = mock_body_cls.call_args.kwargs
    self.assertEqual(kwargs["cameras"], ["wideRoad"])
    self.assertEqual(kwargs["sdp"], "v=0")
    self.assertTrue(kwargs["enabled"])
    self.assertNotIn("init_camera", kwargs)


if __name__ == "__main__":
  unittest.main()
