def get_camera_packets(use_wide_camera: bool) -> list[str]:
  # sp service names (narrowRoadCameraState/cabinCameraState, zp opendbc layout).
  # Road-camera validity is independent and keeps the existing disable policy.
  packets = ["narrowRoadCameraState", "cabinCameraState"]
  if use_wide_camera:
    packets.append("wideRoadCameraState")
  return packets
