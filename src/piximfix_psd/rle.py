"""Apple PackBits RLE encoder/decoder and planar-to-interleaved RGBA channel compositor."""

from __future__ import annotations

from typing import List, Sequence
from .binary_reader import PsdFormatError


def decode_packbits_row(encoded: bytes | memoryview, expected_length: int) -> bytes:
    """
    Decode a single PackBits RLE scanline into `expected_length` uncompressed bytes.

    PackBits specification:
      - Header byte N in [0..127]: copy the next N + 1 literal bytes.
      - Header byte N in [-127..-1] (or 129..255 unsigned): repeat the next single byte (1 - N) times.
      - Header byte -128 (0x80): no-op.
    """
    out = bytearray()
    idx = 0
    total = len(encoded)

    while idx < total and len(out) < expected_length:
        header = encoded[idx]
        idx += 1
        if header < 128:
            count = header + 1
            if idx + count > total:
                raise PsdFormatError("Truncated PackBits literal run in scanline")
            out.extend(encoded[idx : idx + count])
            idx += count
        elif header > 128:
            count = 257 - header
            if idx >= total:
                raise PsdFormatError("Truncated PackBits repeat byte in scanline")
            val = encoded[idx]
            idx += 1
            out.extend(bytes([val]) * count)
        # header == 128 (0x80) is a no-op

    if len(out) < expected_length:
        out.extend(b"\x00" * (expected_length - len(out)))
    return bytes(out[:expected_length])


def encode_packbits_row(raw: bytes | memoryview) -> bytes:
    """Encode a single scanline using Apple PackBits RLE compression."""
    data = bytes(raw)
    n = len(data)
    if n == 0:
        return b""

    out = bytearray()
    i = 0
    while i < n:
        run_len = 1
        while i + run_len < n and run_len < 128 and data[i + run_len] == data[i]:
            run_len += 1

        if run_len >= 3:
            out.append(257 - run_len)
            out.append(data[i])
            i += run_len
        else:
            lit_start = i
            lit_len = 0
            while i < n and lit_len < 128:
                check_run = 1
                while (
                    i + check_run < n
                    and check_run < 3
                    and data[i + check_run] == data[i]
                ):
                    check_run += 1
                if check_run >= 3 and lit_len > 0:
                    break
                i += 1
                lit_len += 1
            out.append(lit_len - 1)
            out.extend(data[lit_start : lit_start + lit_len])

    return bytes(out)


def interleave_planar_channels_to_rgba(
    channel_planes: Sequence[bytes],
    width: int,
    height: int,
    color_mode: int,
) -> bytes:
    """
    Convert planar channel arrays (R, G, B, [A] or Grayscale or CMYK) into
    tightly packed 32-bit RGBA bytes (width * height * 4).
    """
    pixel_count = width * height
    if pixel_count == 0:
        return b""

    rgba = bytearray(pixel_count * 4)

    # Grayscale (ColorMode.GRAYSCALE == 1)
    if color_mode == 1 or len(channel_planes) == 1:
        gray = channel_planes[0]
        alpha = channel_planes[1] if len(channel_planes) > 1 else None
        for idx in range(pixel_count):
            g = gray[idx] if idx < len(gray) else 0
            a = alpha[idx] if (alpha is not None and idx < len(alpha)) else 255
            base = idx * 4
            rgba[base] = g
            rgba[base + 1] = g
            rgba[base + 2] = g
            rgba[base + 3] = a
        return bytes(rgba)

    # CMYK (ColorMode.CMYK == 4) — Photoshop stores inverted CMYK (0=full ink, 255=no ink)
    if color_mode == 4 and len(channel_planes) >= 4:
        c_plane, m_plane, y_plane, k_plane = (
            channel_planes[0],
            channel_planes[1],
            channel_planes[2],
            channel_planes[3],
        )
        alpha = channel_planes[4] if len(channel_planes) > 4 else None
        for idx in range(pixel_count):
            c = c_plane[idx] / 255.0
            m = m_plane[idx] / 255.0
            y = y_plane[idx] / 255.0
            k = k_plane[idx] / 255.0
            r = int(round(255.0 * c * k))
            g = int(round(255.0 * m * k))
            b = int(round(255.0 * y * k))
            a = alpha[idx] if (alpha is not None and idx < len(alpha)) else 255
            base = idx * 4
            rgba[base] = max(0, min(255, r))
            rgba[base + 1] = max(0, min(255, g))
            rgba[base + 2] = max(0, min(255, b))
            rgba[base + 3] = a
        return bytes(rgba)

    # Standard RGB / RGBA
    r_plane = channel_planes[0]
    g_plane = channel_planes[1] if len(channel_planes) > 1 else r_plane
    b_plane = channel_planes[2] if len(channel_planes) > 2 else r_plane
    a_plane = channel_planes[3] if len(channel_planes) > 3 else None

    rgba[0::4] = r_plane[:pixel_count]
    rgba[1::4] = g_plane[:pixel_count]
    rgba[2::4] = b_plane[:pixel_count]
    if a_plane is not None and len(a_plane) >= pixel_count:
        rgba[3::4] = a_plane[:pixel_count]
    else:
        rgba[3::4] = b"\xff" * pixel_count

    return bytes(rgba)
