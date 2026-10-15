"""Xiaoge Onnx BSD/Lane detection subsystem.

Ported from CarrotPilot (cp):
  selfdrive/carrot/xiaoge/

Architecture:
  - lane_inference.py  - YOLOv8-Seg lane segmentation ONNX model (solid/dashed classification)
  - v_asm_inference.py - V-ASM blind-spot detection ONNX model
  - nv12.py            - NV12 Y-plane utilities for camera data parsing
  - xiaoge_vision.py   - Data classes and carState integration helpers

Requirements:
  - opencv-python-headless >= 4.10.0  (for cv2.dnn.readNetFromONNX)
  - numpy >= 1.24

Camera source:
  On real hardware (C3): reads from VisionIPC / camerad NV12 buffers.
  On PC dev: requires a video file source or mock data (camera hardware unavailable).
"""
