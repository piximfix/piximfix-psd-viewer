"""Unit tests for PackBits RLE compression/decompression and planar RGBA interleaving."""

from __future__ import annotations

from piximfix_psd.rle import (
    decode_packbits_row,
    encode_packbits_row,
    interleave_planar_channels_to_rgba,
)


def test_packbits_roundtrip_mixed_runs_and_literals() -> None:
    original = (b"\xAA" * 20) + b"\x01\x02\x03\x04\x05" + (b"\xFF" * 45) + b"\x10\x20"
    encoded = encode_packbits_row(original)
    decoded = decode_packbits_row(encoded, len(original))
    assert decoded == original
    assert len(encoded) < len(original)


def test_packbits_empty_scanline() -> None:
    assert encode_packbits_row(b"") == b""
    assert decode_packbits_row(b"", 0) == b""


def test_interleave_grayscale_and_cmyk_to_rgba() -> None:
    # 2x1 grayscale
    gray_rgba = interleave_planar_channels_to_rgba([b"\x40\xC0"], width=2, height=1, color_mode=1)
    assert gray_rgba == b"\x40\x40\x40\xff\xc0\xc0\xc0\xff"

    # 1x1 inverted CMYK (255, 255, 255, 255 in Photoshop = pure white RGB 255, 255, 255)
    cmyk_rgba = interleave_planar_channels_to_rgba(
        [b"\xff", b"\xff", b"\xff", b"\xff"], width=1, height=1, color_mode=4
    )
    assert cmyk_rgba == b"\xff\xff\xff\xff"
