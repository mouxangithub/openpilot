"""
Copyright (c) 2025, Rick Lan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, and/or sublicense,
for non-commercial purposes only, subject to the following conditions:

- The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.
- Commercial use (e.g. use in a product, service, or activity intended to
  generate revenue) is prohibited without explicit written permission from
  the copyright holder.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

#!/usr/bin/env python3
import math
import os
import struct
import subprocess
import time
import serial
from typing import Optional, List, NamedTuple, Dict

from opendbc.car import structs
from opendbc.car.interfaces import RadarInterfaceBase

# --- Configurable Parameters ---
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 921600
USB_DEVICE_PATH = "3-1" # IMPORTANT: Configure this to match your hardware setup

SNR_THRESHOLD = 5.0
LATERAL_FILTER_DIST = 1.85 # m. Points outside this lateral distance from center are ignored.

# --- Constants ---
PACKET_HEADER = b'\xCB\xFE\xDD\xFF'
PACKET_FOOTER = b'\xC4\xFE\xDD\xFF'
HEADER_LENGTH = 4
FOOTER_LENGTH = 4
COUNT_LENGTH = 4
TARGET_DATA_LENGTH = 20

# --- Data structures for parsing ---
class RadarTarget(NamedTuple):
    track_id: int
    distance: float
    velocity: float
    horizontal_angle: float

class OpenpilotRadarPoint(NamedTuple):
    trackId: int
    dRel: float
    yRel: float
    vRel: float
    raw_target: RadarTarget

class RadarInterface(RadarInterfaceBase):

  def __init__(self, CP):
    super().__init__(CP)

    self.ser: Optional[serial.Serial] = None
    self.buffer = bytearray()

    # Persistent dictionary to store radar points, using the structs convention
    self.pts: Dict[int, structs.RadarData.RadarPoint] = {}

    self.rcp = None
    self.can_parser = None

    self._check_and_reset_usb()

    try:
      self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01)
    except serial.SerialException as e:
      print(f"Error initializing serial port after reset attempt: {e}")
      self.ser = None

  def _check_and_reset_usb(self) -> None:
    if os.path.exists(SERIAL_PORT):
      print(f"Radar device {SERIAL_PORT} found.")
      return

    print(f"Radar device {SERIAL_PORT} not found. Attempting USB reset...")

    unbind_path = '/sys/bus/usb/drivers/usb/unbind'
    bind_path = '/sys/bus/usb/drivers/usb/bind'

    if not os.path.exists(unbind_path) or not os.path.exists(bind_path):
        print("USB unbind/bind paths not found. Cannot reset device.")
        return

    try:
      print(f"Unbinding USB device at path {USB_DEVICE_PATH}...")
      subprocess.run(['sudo', 'tee', unbind_path], input=USB_DEVICE_PATH.encode(), check=True, capture_output=True)
      time.sleep(1)

      print(f"Rebinding USB device at path {USB_DEVICE_PATH}...")
      subprocess.run(['sudo', 'tee', bind_path], input=USB_DEVICE_PATH.encode(), check=True, capture_output=True)
      time.sleep(2)

      if os.path.exists(SERIAL_PORT):
        print("USB reset successful.")
      else:
        print("USB reset failed. Device still not found.")

    except subprocess.CalledProcessError as e:
      print(f"Failed to reset USB device. Error: {e.stderr.decode()}")
      print("Ensure passwordless sudo is configured for the 'tee' command.")
    except Exception as e:
      print(f"An unexpected error occurred during USB reset: {e}")


  def _parse_data_packet(self, data: bytes) -> Optional[List[OpenpilotRadarPoint]]:
    if len(data) < COUNT_LENGTH:
      return None

    try:
      num_targets = struct.unpack('<I', data[:COUNT_LENGTH])[0]

      expected_length = COUNT_LENGTH + num_targets * TARGET_DATA_LENGTH
      if len(data) != expected_length:
        print(f"Warning: Packet length mismatch. Expected {expected_length}, got {len(data)}. Skipping packet.")
        return None

      points: List[OpenpilotRadarPoint] = []
      for i in range(num_targets):
        offset = COUNT_LENGTH + i * TARGET_DATA_LENGTH

        raw_track_id, raw_snr, raw_dist, raw_vel, raw_h_angle = struct.unpack('<iiiii', data[offset:offset+20])

        snr = raw_snr / 100.0
        if snr < SNR_THRESHOLD:
          continue

        target = RadarTarget(
            track_id=raw_track_id,
            distance=raw_dist / 100.0,
            velocity=(raw_vel - 5000) / 100.0,
            horizontal_angle=raw_h_angle / 100.0 - 90.0
        )

        angle_rad = math.radians(target.horizontal_angle)
        dRel = target.distance * math.cos(angle_rad)
        yRel = target.distance * math.sin(angle_rad) * -1
        vRel = target.velocity * math.cos(angle_rad)

        if abs(yRel) > LATERAL_FILTER_DIST:
          continue

        op_point = OpenpilotRadarPoint(
            trackId=target.track_id,
            dRel=dRel,
            yRel=yRel,
            vRel=vRel,
            raw_target=target
        )
        points.append(op_point)

      return points
    except struct.error as e:
      print(f"Error unpacking data: {e}")
      return None

  def update(self, can_packets: list[tuple[int, list[CanData]]]) -> structs.RadarDataT | None:
    ret = structs.RadarData()
    if self.ser is None:
      ret.errors.append("Radar serial connection failed.")
      return ret

    try:
      if self.ser.in_waiting > 0:
        self.buffer.extend(self.ser.read(self.ser.in_waiting))

      header_index = self.buffer.find(PACKET_HEADER)
      if header_index != -1:
        footer_index = self.buffer.find(PACKET_FOOTER, header_index + HEADER_LENGTH)
        if footer_index != -1:
          payload = self.buffer[header_index + HEADER_LENGTH : footer_index]
          parsed_points = self._parse_data_packet(payload)

          if parsed_points is not None:
            current_track_ids = {pt.trackId for pt in parsed_points}

            # Update or add points directly from the parsed data
            for pt in parsed_points:
              if pt.trackId not in self.pts:
                self.pts[pt.trackId] = structs.RadarData.RadarPoint()

              self.pts[pt.trackId].trackId = pt.trackId
              self.pts[pt.trackId].dRel = pt.dRel
              self.pts[pt.trackId].yRel = pt.yRel
              self.pts[pt.trackId].vRel = pt.vRel
              self.pts[pt.trackId].measured = True

            # Remove points that are no longer tracked by the radar
            for track_id in list(self.pts.keys()):
              if track_id not in current_track_ids:
                del self.pts[track_id]

          self.buffer = self.buffer[footer_index + FOOTER_LENGTH:]

    except serial.SerialException as e:
      print(f"Serial error during update: {e}")
      ret.errors.append("Radar serial connection failed.")
      self.pts.clear()
    except Exception as e:
      print(f"An unexpected error occurred: {e}")
      ret.errors.append("Radar parsing error.")
      self.pts.clear()

    ret.points = list(self.pts.values())
    ret.valid = self.ser is not None and not ret.errors

    return ret
