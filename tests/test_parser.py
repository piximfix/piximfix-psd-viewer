"""Unit tests for binary PSD (v1) and PSB (v2) parsing, layer extraction, and 8BIM resources."""

from __future__ import annotations

import pytest

from piximfix_psd.binary_reader import PsdFormatError
from piximfix_psd.models import ColorMode, CompressionMethod
from piximfix_psd.parser import build_synthetic_psd, parse_psd_bytes


def test_parse_psd_v1_rle_header_and_layers() -> None:
    raw = build_synthetic_psd(
        width=24,
        height=16,
        channels=4,
        version=1,
        compression=CompressionMethod.RLE_PACKBITS,
        layer_names=["Background", "Product Hero", "Price Badge"],
        dpi=300.0,
    )
    doc = parse_psd_bytes(raw)
    assert doc.header.format_label == "PSD"
    assert not doc.header.is_psb
    assert doc.header.width == 24
    assert doc.header.height == 16
    assert doc.header.channels == 4
    assert doc.header.color_mode == ColorMode.RGB
    assert len(doc.layers) == 3
    assert [layer.name for layer in doc.layers] == [
        "Background",
        "Product Hero",
        "Price Badge",
    ]
    assert doc.resolution is not None
    assert doc.resolution.h_res_ppi == 300.0
    assert len(doc.composite_rgba) == 24 * 16 * 4


def test_parse_psb_v2_64bit_large_document_format() -> None:
    raw = build_synthetic_psd(
        width=32,
        height=32,
        channels=4,
        version=2,
        compression=CompressionMethod.RLE_PACKBITS,
        layer_names=["Base Canvas", "Smart Group"],
        dpi=144.0,
    )
    doc = parse_psd_bytes(raw)
    assert doc.header.is_psb
    assert doc.header.format_label == "PSB"
    assert doc.header.width == 32
    assert doc.header.height == 32
    assert len(doc.layers) == 2
    assert doc.resolution is not None
    assert doc.resolution.h_res_ppi == 144.0
    assert len(doc.composite_rgba) == 32 * 32 * 4


def test_parse_psd_raw_uncompressed_composite() -> None:
    raw = build_synthetic_psd(
        width=12,
        height=10,
        channels=3,
        version=1,
        compression=CompressionMethod.RAW,
        layer_names=["Flat RGB"],
    )
    doc = parse_psd_bytes(raw)
    assert doc.compression == CompressionMethod.RAW
    assert len(doc.composite_rgba) == 12 * 10 * 4
    # Alpha channel should default to 255 for 3-channel RGB
    assert doc.composite_rgba[3] == 255


def test_reject_invalid_magic_signature() -> None:
    with pytest.raises(PsdFormatError, match="Invalid PSD signature"):
        parse_psd_bytes(b"NOT_A_PSD_HEADER_1234567890123456")


def test_reject_truncated_buffer() -> None:
    with pytest.raises(PsdFormatError, match="shorter than 26-byte"):
        parse_psd_bytes(b"8BPS\x00\x01")
