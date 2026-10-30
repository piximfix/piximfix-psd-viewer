"""Big-endian binary reader and writer utilities for PSD (32-bit) and PSB (64-bit) streams."""

from __future__ import annotations

import struct


class PsdFormatError(ValueError):
    """Raised when a PSD/PSB stream violates the Adobe file format specification."""


class BinaryReader:
    """Zero-copy cursor over a bytes or memoryview buffer with big-endian unpacking."""

    def __init__(self, buffer: bytes | memoryview) -> None:
        self._buf = memoryview(buffer)
        self._pos = 0
        self._len = len(self._buf)

    @property
    def position(self) -> int:
        return self._pos

    @property
    def remaining(self) -> int:
        return max(0, self._len - self._pos)

    def seek(self, offset: int) -> None:
        if offset < 0 or offset > self._len:
            raise PsdFormatError(f"Seek offset {offset} out of bounds (size={self._len})")
        self._pos = offset

    def skip(self, count: int) -> None:
        self.seek(self._pos + count)

    def read_bytes(self, count: int) -> bytes:
        if count < 0 or self._pos + count > self._len:
            raise PsdFormatError(
                f"Unexpected EOF at offset {self._pos}: requested {count} bytes, "
                f"only {self.remaining} remaining"
            )
        chunk = bytes(self._buf[self._pos : self._pos + count])
        self._pos += count
        return chunk

    def read_ascii(self, count: int) -> str:
        raw = self.read_bytes(count)
        return raw.decode("latin1")

    def read_u8(self) -> int:
        return struct.unpack(">B", self.read_bytes(1))[0]

    def read_i8(self) -> int:
        return struct.unpack(">b", self.read_bytes(1))[0]

    def read_u16(self) -> int:
        return struct.unpack(">H", self.read_bytes(2))[0]

    def read_i16(self) -> int:
        return struct.unpack(">h", self.read_bytes(2))[0]

    def read_u32(self) -> int:
        return struct.unpack(">I", self.read_bytes(4))[0]

    def read_i32(self) -> int:
        return struct.unpack(">i", self.read_bytes(4))[0]

    def read_u64(self) -> int:
        return struct.unpack(">Q", self.read_bytes(8))[0]

    def read_length_field(self, is_psb: bool) -> int:
        """Read a 4-byte length for PSD (v1) or 8-byte length for PSB (v2)."""
        return self.read_u64() if is_psb else self.read_u32()

    def read_pascal_string(self, padding_multiple: int = 2) -> str:
        """Read a length-prefixed Pascal string padded to `padding_multiple` bytes."""
        length = self.read_u8()
        raw = self.read_bytes(length)
        total_read = 1 + length
        remainder = total_read % padding_multiple
        if remainder != 0:
            pad_bytes = padding_multiple - remainder
            self.skip(pad_bytes)
        return raw.decode("latin1", errors="replace")
