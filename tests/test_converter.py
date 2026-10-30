"""Unit tests for corner badge rendering, PNG encoding, and batch conversion."""

from __future__ import annotations

from pathlib import Path

from piximfix_psd.badge import apply_psd_corner_badge
from piximfix_psd.converter import BatchPsdConverter, export_rgba_to_png_bytes
from piximfix_psd.parser import build_synthetic_psd


def test_apply_psd_corner_badge_modifies_bottom_right_pixels() -> None:
    width, height = 48, 48
    blank = bytes([20, 20, 20, 255] * (width * height))
    badged = apply_psd_corner_badge(blank, width, height, label="PSD")
    assert len(badged) == len(blank)
    assert badged != blank


def test_export_rgba_to_png_valid_signature_and_iend() -> None:
    rgba = bytes([255, 0, 128, 255] * (16 * 16))
    png = export_rgba_to_png_bytes(rgba, 16, 16)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IHDR" in png
    assert b"IDAT" in png
    assert png.endswith(b"IEND\xaeB`\x82")


def test_batch_psd_converter_end_to_end(tmp_path: Path) -> None:
    psd_a = tmp_path / "card_a.psd"
    psd_b = tmp_path / "poster_b.psb"
    psd_a.write_bytes(build_synthetic_psd(width=32, height=32, version=1))
    psd_b.write_bytes(build_synthetic_psd(width=40, height=24, version=2))

    out_dir = tmp_path / "out"
    converter = BatchPsdConverter(apply_badge=True, max_workers=2)
    reports = converter.convert_batch([psd_a, psd_b], output_dir=out_dir)

    assert len(reports) == 2
    assert all(r.success for r in reports)
    assert (out_dir / "card_a.png").exists()
    assert (out_dir / "poster_b.png").exists()
