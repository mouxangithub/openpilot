"""CANPacket_t Python-FFI vs native-C ABI contract tests.

Intent (ported from StarPilot test_canpacket_abi.py, adapted to this fork's
libsafety_py): a C probe library compiled from the real can.h pins down
sizeof / _Alignof / offsetof / whole-struct copy semantics, and the Python
(cffi) view must agree with it. This is the guard against silent layout drift
between the safety C code and its Python bindings.

ABI contract in this fork: can.h declares CANPacket_t as
`__attribute__((packed, aligned(4)))`, while libsafety_py registers the cdef
with packed=True. Therefore the cffi *logical* size is the unrounded packed
size (70) while the native size is rounded to the 4-byte alignment (72).
Native code always copies its own sizeof — the canary tests below prove both
facts, so any change on either side fails loudly here instead of corrupting
adjacent memory at runtime.

cc-dependent tests are skipped on hosts without a C toolchain; they run in CI.
"""
import ctypes
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from opendbc.safety.tests.libsafety import libsafety_py

HAVE_CC = shutil.which("cc") is not None

PROBE_SOURCE = '''#include <stddef.h>
#include <string.h>
#include "can.h"
size_t packet_size(void) { return sizeof(CANPacket_t); }
size_t packet_alignment(void) { return _Alignof(CANPacket_t); }
size_t packet_data_offset(void) { return offsetof(CANPacket_t, data); }
void packet_copy(const CANPacket_t *src, CANPacket_t *out) { *out = *src; }
void packet_fill(CANPacket_t *out) {
  memset(out, 0x92, sizeof(*out));
  out->addr = 0x123; out->bus = 2; out->data_len_code = 15; out->extended = 1;
  for (unsigned int i = 0; i < 64; ++i) out->data[i] = (unsigned char)i;
}
'''


@unittest.skipIf(not HAVE_CC, "C toolchain unavailable")
class TestCanPacketAbiVsNative(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.directory = tempfile.TemporaryDirectory()
    cls.addClassCleanup(cls.directory.cleanup)
    directory = Path(cls.directory.name)
    source = directory / "probe.c"
    source.write_text(PROBE_SOURCE)
    library = directory / "probe.so"
    subprocess.run(
      ["cc", "-shared", "-fPIC", "-std=gnu11", "-O0", "-Wall", "-Wextra", "-Werror",
       "-I", str(libsafety_py.safety_dir), str(source), "-o", str(library)],
      check=True)
    cls.ffi = libsafety_py.ffi
    cls.ffi.cdef('''size_t packet_size(void); size_t packet_alignment(void); size_t packet_data_offset(void);
void packet_copy(const CANPacket_t *src, CANPacket_t *out); void packet_fill(CANPacket_t *out);''')
    cls.native = cls.ffi.dlopen(str(library))
    cls.packed_size = cls.ffi.sizeof("CANPacket_t")
    cls.native_size = cls.native.packet_size()

  def test_packed_logical_size_differs_from_aligned_native_size_by_contract(self):
    # cdef is registered packed=True -> unrounded packed size.
    # Native struct is packed, aligned(4) -> rounded up to a multiple of 4.
    head = 6  # 1B bitfields + 4B addr word + 1B checksum (see CANPACKET_HEAD_SIZE)
    self.assertEqual(self.packed_size, head + 64)
    self.assertEqual(self.native_size, (head + 64 + 3) // 4 * 4)
    self.assertLess(self.packed_size, self.native_size)

  def test_data_offset_matches_native_exactly(self):
    self.assertEqual(self.ffi.offsetof("CANPacket_t", "data"), self.native.packet_data_offset())
    self.assertEqual(self.native.packet_data_offset(), 6)

  def test_cffi_allocation_satisfies_native_alignment(self):
    self.assertEqual(self.native.packet_alignment(), 4)
    packet = self.ffi.new("CANPacket_t *")
    self.assertEqual(int(self.ffi.cast("uintptr_t", packet)) % self.native.packet_alignment(), 0)

  def test_native_fill_visible_through_ffi_and_copy_respects_native_size(self):
    storage = self.ffi.new("unsigned char[]", self.native_size + 16)
    self.ffi.buffer(storage)[:] = b"\xa5" * (self.native_size + 16)
    packet = self.ffi.cast("CANPacket_t *", storage)
    self.native.packet_fill(packet)
    self.assertEqual((packet.addr, packet.bus, packet.data_len_code, packet.extended), (0x123, 2, 15, 1))
    self.assertEqual(bytes(self.ffi.buffer(packet.data)), bytes(range(64)))
    # native struct copy honours its own (aligned) size: the two bytes between
    # the packed logical size and the native size are real memory it touches...
    source = self.ffi.new("CANPacket_t *")
    output = self.ffi.new("CANPacket_t *")
    self.native.packet_fill(source)
    self.native.packet_copy(source, output)
    self.assertEqual((output.addr, output.bus, output.data_len_code), (0x123, 2, 15))
    self.assertEqual(bytes(self.ffi.buffer(output.data)), bytes(range(64)))
    # ...but the guard region past the native size must never be touched.
    guard = self.ffi.new("unsigned char[]", self.native_size + 16)
    self.ffi.buffer(guard)[:] = b"\xa5" * (self.native_size + 16)
    out = self.ffi.cast("CANPacket_t *", guard)
    self.native.packet_fill(out)
    self.assertEqual(bytes(self.ffi.buffer(guard)[self.native_size:]), b"\xa5" * 16)

  def test_ffi_memmove_roundtrip_preserves_payload(self):
    storage = self.ffi.new("unsigned char[]", self.native_size)
    packet = self.ffi.cast("CANPacket_t *", storage)
    self.native.packet_fill(packet)
    mirror = self.ffi.new("CANPacket_t *")
    self.ffi.memmove(mirror, packet, self.packed_size)
    self.assertEqual((mirror.addr, mirror.bus, mirror.data_len_code), (0x123, 2, 15))
    self.assertEqual(bytes(self.ffi.buffer(mirror.data)), bytes(range(64)))
    # packed-size memmove: bytes [packed_size, native_size) are padding, not payload


class TestMakeCanPacketSemantics(unittest.TestCase):
  """Python-side constructor contract (no C toolchain needed)."""

  def test_extended_flag_derived_from_addr(self):
    classic = libsafety_py.make_CANPacket(0x1D3, 0, b"\x00" * 8)
    extended = libsafety_py.make_CANPacket(0x1D3 + 0x800, 0, b"\x00" * 8)
    self.assertEqual(classic[0].extended, 0)
    self.assertEqual(extended[0].extended, 1)

  def test_data_len_code_and_payload_roundtrip(self):
    dat = bytes(range(8))
    packet = libsafety_py.make_CANPacket(0x2E4, 2, dat)
    self.assertEqual(packet[0].addr, 0x2E4)
    self.assertEqual(packet[0].bus, 2)
    self.assertEqual(libsafety_py.ffi.buffer(packet[0].data)[:8], dat)

  def test_max_fd_payload(self):
    dat = bytes(64)
    packet = libsafety_py.make_CANPacket(0x1D3, 0, dat)
    self.assertEqual(bytes(libsafety_py.ffi.buffer(packet[0].data)), dat)
    # dlc 15 encodes 64 bytes per dlc_to_len
    self.assertEqual(packet[0].data_len_code, 15)


if __name__ == "__main__":
  unittest.main()
