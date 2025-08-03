import json
import math
import numpy as np
import os
import random
import socket
import subprocess
import sys
import urllib.error
import urllib.request

from collections import Counter
from datetime import datetime, timezone

import openpilot.system.sentry as sentry

from openpilot.common.conversions import Conversions as CV
from openpilot.system.version import get_build_metadata

from openpilot.frogpilot.common.frogpilot_utilities import run_cmd
from openpilot.frogpilot.common.frogpilot_variables import get_frogpilot_toggles, params, params_tracking

def handle_geocoding_error(error, latitude, longitude):
  error_map = {
    urllib.error.HTTPError: lambda e: f"HTTP error: {e.code} - {e.reason}",
    urllib.error.URLError: lambda e: f"URL error: {e.reason}",
    socket.gaierror: lambda e: "DNS resolution failed",
    socket.timeout: lambda e: "Socket timed out",
    TimeoutError: lambda e: "System timeout"
  }

  message = error_map.get(type(error), lambda e: f"Unexpected error: {e}")
  print(f"Failed to get zip code center: {message(error)}")

  if type(error) not in error_map:
    sentry.capture_exception(error)

  return latitude, longitude

def install_influxdb_client():
  try:
    import influxdb_client
    import influxdb_client.client.write_api
  except ModuleNotFoundError:
    print("influxdb-client not found. Attempting installation...")
    stock_mount_options = subprocess.run(["findmnt", "-no", "OPTIONS", "/"], capture_output=True, text=True, check=True).stdout.strip()

    run_cmd(["sudo", "mount", "-o", "remount,rw", "/"], "Successfully remounted / as read-write", "Failed to remount / as read-write")
    run_cmd(["sudo", sys.executable, "-m", "pip", "install", "influxdb-client"], "Successfully installed influxdb-client", "Failed to install influxdb-client", report=False)
    run_cmd(["sudo", "mount", "-o", f"remount,{stock_mount_options}", "/"], "Successfully restored stock mount options", "Failed to restore stock mount options")

def install_pgeocode():
  try:
    import pgeocode
  except ModuleNotFoundError:
    print("pgeocode not found. Attempting installation...")
    stock_mount_options = subprocess.run(["findmnt", "-no", "OPTIONS", "/"], capture_output=True, text=True, check=True).stdout.strip()

    run_cmd(["sudo", "mount", "-o", "remount,rw", "/"], "Successfully remounted / as read-write", "Failed to remount / as read-write")
    run_cmd(["sudo", sys.executable, "-m", "pip", "install", "pgeocode"], "Successfully installed pgeocode", "Failed to install pgeocode", report=False)
    run_cmd(["sudo", "mount", "-o", f"remount,{stock_mount_options}", "/"], "Successfully restored stock mount options", "Failed to restore stock mount options")

def get_zip_code_center(latitude, longitude):
  try:
    import pgeocode

    url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={latitude}&lon={longitude}&addressdetails=1"
    request = urllib.request.Request(url, headers={"User-Agent": "frogpilot-zip-code-checker/1.0 (https://github.com/FrogAi/FrogPilot)"})
    with urllib.request.urlopen(request, timeout=10) as response:
      location_data = json.load(response)

    address = location_data.get("address", {})
    postal_code = address.get("postcode")
    country_code = address.get("country_code", "us").upper()

    if not postal_code:
      sentry.capture_exception(Exception(f"Reverse geocoding failed: missing postal code for lat={latitude}, lon={longitude}, response={location_data}"))
      raise ValueError(f"Postal code missing from reverse geocoding response: {location_data}")

    postal_code = postal_code.strip().replace(" ", "").replace("-", "").upper()
    if not postal_code.isalnum():
      sentry.capture_exception(Exception(f"Suspicious postal code format after cleanup: {postal_code}, original={address.get('postcode')}, country={country_code}"))

    geocoder = pgeocode.Nominatim(country_code)
    postal_code_info = geocoder.query_postal_code(postal_code)

    if postal_code_info is not None and not math.isnan(postal_code_info.latitude) and not math.isnan(postal_code_info.longitude):
      return float(postal_code_info.latitude), float(postal_code_info.longitude)
    else:
      sentry.capture_exception(Exception(f"Postal code lookup returned NaN or None for code={postal_code}, country={country_code}, data={postal_code_info}"))

    postal_code_data = geocoder._data[["postal_code", "latitude", "longitude"]].dropna()
    if postal_code_data.empty:
      sentry.capture_exception(Exception(f"Fallback postal code dataset is empty for lat={latitude}, lon={longitude}"))
      raise ValueError(f"Fallback postal code dataset is empty for country={country_code}")

    latitude_radians = math.radians(latitude)
    longitude_radians = math.radians(longitude)

    all_latitudes = np.radians(postal_code_data["latitude"].to_numpy())
    all_longitudes = np.radians(postal_code_data["longitude"].to_numpy())

    latitude_differences = all_latitudes - latitude_radians
    longitude_differences = all_longitudes - longitude_radians

    haversine = (
      np.sin(latitude_differences / 2) ** 2 +
      np.cos(latitude_radians) * np.cos(all_latitudes) * np.sin(longitude_differences / 2) ** 2
    )
    distance = 2 * np.arctan2(np.sqrt(haversine), np.sqrt(1 - haversine))

    closest_index = int(np.argmin(distance))
    closest_latitude = float(postal_code_data.iloc[closest_index]["latitude"])
    closest_longitude = float(postal_code_data.iloc[closest_index]["longitude"])

    if closest_latitude == 0.0 and closest_longitude == 0.0:
      sentry.capture_exception(Exception(f"Fallback to nearest postal code returned (0.0, 0.0) for lat={latitude}, lon={longitude}, country={country_code}"))

    return closest_latitude, closest_longitude

  except (urllib.error.URLError, urllib.error.HTTPError, socket.gaierror, socket.timeout, TimeoutError, Exception) as error:
    return handle_geocoding_error(error, latitude, longitude)

def send_stats():
  frogpilot_toggles = get_frogpilot_toggles()

  if frogpilot_toggles.frogs_go_moo:
    return

  install_influxdb_client()
  install_pgeocode()

  from influxdb_client import InfluxDBClient, Point, WriteOptions
  from influxdb_client.client.write_api import SYNCHRONOUS

  bucket = os.environ.get("STATS_BUCKET", "")
  org_ID = os.environ.get("STATS_ORG_ID", "")
  token = os.environ.get("STATS_TOKEN", "")
  url = os.environ.get("STATS_URL", "")

  location = json.loads(params.get("LastGPSPosition") or "{}")
  original_latitude = location.get("latitude")
  original_longitude = location.get("longitude")
  latitude, longitude = get_zip_code_center(original_latitude, original_longitude)

  theme_sources = [
    frogpilot_toggles.icon_pack.replace("-animated", ""),
    frogpilot_toggles.color_scheme,
    frogpilot_toggles.distance_icons.replace("-animated", ""),
    frogpilot_toggles.signal_icons.replace("-animated", ""),
    frogpilot_toggles.sound_pack
  ]

  theme_counter = Counter(theme_sources)
  most_common = theme_counter.most_common()
  max_count = most_common[0][1]

  selected_theme = random.choice([item for item, count in most_common if count == max_count]).replace("-user_created", "").replace("_", " ")

  point = (Point("user_stats")
    .field("car_make", frogpilot_toggles.car_make.title())
    .field("car_model", frogpilot_toggles.car_model)
    .field("driving_model", frogpilot_toggles.model_name.replace("🗺️", "").replace("📡", "").replace("👀", "").replace("(Default)", "").strip())
    .field("event", 1)
    .field("frogpilot_drives", params_tracking.get_int("FrogPilotDrives"))
    .field("frogpilot_hours", params_tracking.get_int("FrogPilotMinutes") / 60)
    .field("frogpilot_miles", params_tracking.get_int("FrogPilotKilometers") * CV.KPH_TO_MPH)
    .field("latitude", latitude)
    .field("longitude", longitude)
    .field("theme", selected_theme.title())

    .tag("branch", get_build_metadata().channel)
    .tag("dongle_id", params.get("FrogPilotDongleId", encoding="utf-8"))

    .time(datetime.now(timezone.utc))
  )

  try:
    InfluxDBClient(org=org_ID, token=token, url=url).write_api(write_options=SYNCHRONOUS).write(bucket=bucket, org=org_ID, record=point)
    print("Successfully sent FrogPilot stats!")
  except Exception as exception:
    sentry.capture_exception(exception)
    print(f"Failed to send FrogPilot stats: {exception}")
