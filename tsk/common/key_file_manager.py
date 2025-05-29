# tsk/common/key_file_manager.py

import os
import re
import threading
import time

from tsk.common.env import is_agnos
from tsk.ui.layout import Theme


class KeyFileManager:

  DATA_PARAMS_D_SECOCKEY_PATH = "/data/params/d/SecOCKey"
  CACHE_PARAMS_SECOCKEY_PATH = "/cache/params/SecOCKey"
  HOME_SECOCKEY_PATH = os.path.expanduser("~/SecOCKey")

  def __init__(self):
    self.installed_key = KeyFileManager._read_key_from_files()  # Initialize installed_key
    threading.Thread(target=self._update_key_status_loop, daemon=True).start()

  @staticmethod
  def _is_key_valid(key: str) -> bool:
    """Checks if the key is a valid 32-character lowercase hexadecimal string."""
    if not isinstance(key, str):
      return False

    if len(key) != 32:
      return False

    pattern = r"^[0-9a-f]{32}$"
    return bool(re.match(pattern, key))

  @staticmethod
  def _read_key_from_file(file_path: str) -> str | None:
    """
    Reads and validates a key from the given file path.
    If the key is invalid, the file is deleted.

    Returns:
      The key if it's valid, None otherwise.
    """
    if not os.path.exists(file_path):
      return None

    try:
      with open(file_path, "r") as f:
        key = f.read().strip()
        if KeyFileManager._is_key_valid(key):
          return key
        else:
          # Key is invalid, delete the file
          try:
            os.remove(file_path)
            print(f"Deleted invalid key file: {file_path} which contained {key}")
          except Exception as e:
            print(f"Error deleting invalid key file {file_path}: {e}")
          return None
    except Exception as e:
      print(f"Error reading key file {file_path}: {e}")
      return None  # Return None on any error

  @staticmethod
  def _read_key_from_files() -> str | None:
    """Reads the key from the appropriate file(s) based on the AGNOS environment."""
    if not is_agnos():
      return KeyFileManager._read_key_from_file(KeyFileManager.HOME_SECOCKEY_PATH)

    data_params_d_secockey = KeyFileManager._read_key_from_file(KeyFileManager.DATA_PARAMS_D_SECOCKEY_PATH)
    cache_params_secockey = KeyFileManager._read_key_from_file(KeyFileManager.CACHE_PARAMS_SECOCKEY_PATH)

    existing_key = cache_params_secockey or data_params_d_secockey

    if not existing_key:
      return None

    # Write the existing key to missing files
    if data_params_d_secockey != existing_key:
      KeyFileManager._write_key_to_file(KeyFileManager.DATA_PARAMS_D_SECOCKEY_PATH, existing_key)
    if cache_params_secockey != existing_key:
      KeyFileManager._write_key_to_file(KeyFileManager.CACHE_PARAMS_SECOCKEY_PATH, existing_key)

    return existing_key

  @staticmethod
  def _write_key_to_file(file_path: str, key: str) -> None:
    """Writes the key to the specified file path."""
    print(f"Writing key to file: {key} {file_path}")
    try:
      with open(file_path, "w") as f:
        f.write(key)
    except Exception as e:
      print(f"Error writing key to file {file_path}: {e}")

  def _update_key_status_loop(self) -> None:
    """Periodically updates the key status."""
    while True:
      self.installed_key = KeyFileManager._read_key_from_files()
      time.sleep(Theme.status_update_interval)  # Check every x second

  def install_key(self, key: str) -> None:
    """Installs the key by writing it to the appropriate file(s) based on the AGNOS environment."""
    if not KeyFileManager._is_key_valid(key):
      print("Invalid key format. Installation aborted.")
      return

    if not is_agnos():
      KeyFileManager._write_key_to_file(KeyFileManager.HOME_SECOCKEY_PATH, key)
      KeyFileManager._installed_key = KeyFileManager._read_key_from_files()
      return

    KeyFileManager._write_key_to_file(KeyFileManager.DATA_PARAMS_D_SECOCKEY_PATH, key)
    KeyFileManager._write_key_to_file(KeyFileManager.CACHE_PARAMS_SECOCKEY_PATH, key)
    self.installed_key = KeyFileManager._read_key_from_files()

  def uninstall_key(self) -> None:
    """Deletes the key from the appropriate file(s) based on the AGNOS environment."""
    def _delete_file(file_path: str):
      if os.path.exists(file_path):
        try:
          os.remove(file_path)
          print(f"Deleted key file: {file_path}")
        except Exception as e:
          print(f"Error deleting key file {file_path}: {e}")

    if not is_agnos():
      _delete_file(KeyFileManager.HOME_SECOCKEY_PATH)

    else:
      _delete_file(KeyFileManager.DATA_PARAMS_D_SECOCKEY_PATH)
      _delete_file(KeyFileManager.CACHE_PARAMS_SECOCKEY_PATH)
    self.installed_key = KeyFileManager._read_key_from_files()
