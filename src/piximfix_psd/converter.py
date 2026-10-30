"""Zero-dependency PNG encoder and multi-threaded batch PSD/PSB conversion pipeline."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import struct
import time
from typing import Iterable, List, Optional
import zlib

from .badge import apply_psd_corner_badge
from .models import ConversionReport
from .parser import parse_psd_file


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def export_rgba_to_png_bytes(rgba: bytes, width: int, height: int) -> bytes:
    """
    Encode an uncompressed 32-bit RGBA buffer into a standard-compliant PNG byte stream
    using Python's built-in `zlib` (zero external image library dependencies required).
    """
    if len(rgba) != width * height * 4:
        raise ValueError(
            f"RGBA buffer size mismatch: got {len(rgba)} bytes for {width}x{height} image"
        )

    raw_scanlines = bytearray()
    stride = width * 4
    for y in range(height):
        raw_scanlines.append(0)  # Filter type 0 (None)
        row_start = y * stride
        raw_scanlines.extend(rgba[row_start : row_start + stride])

    compressed = zlib.compress(bytes(raw_scanlines), level=6)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


class BatchPsdConverter:
    """High-throughput PSD/PSB to PNG converter with optional corner badge overlay."""

    def __init__(self, apply_badge: bool = False, max_workers: int = 4) -> None:
        self.apply_badge = apply_badge
        self.max_workers = max(1, max_workers)

    def convert_file(
        self,
        source_path: str | Path,
        output_path: Optional[str | Path] = None,
    ) -> ConversionReport:
        """Convert a single .PSD or .PSB file to PNG on disk."""
        src = Path(source_path)
        dst = Path(output_path) if output_path is not None else src.with_suffix(".png")
        t0 = time.perf_counter()

        try:
            doc = parse_psd_file(src)
            rgba = doc.composite_rgba
            if self.apply_badge:
                rgba = apply_psd_corner_badge(
                    rgba,
                    doc.header.width,
                    doc.header.height,
                    label=doc.header.format_label,
                )
            png_bytes = export_rgba_to_png_bytes(rgba, doc.header.width, doc.header.height)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(png_bytes)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            return ConversionReport(
                source_path=str(src),
                output_path=str(dst),
                width=doc.header.width,
                height=doc.header.height,
                layer_count=len(doc.layers),
                elapsed_ms=elapsed_ms,
                output_bytes=len(png_bytes),
                badged=self.apply_badge,
                success=True,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            return ConversionReport(
                source_path=str(src),
                output_path=str(dst),
                width=0,
                height=0,
                layer_count=0,
                elapsed_ms=elapsed_ms,
                output_bytes=0,
                badged=self.apply_badge,
                success=False,
                error=str(exc),
            )

    def convert_batch(
        self,
        sources: Iterable[str | Path],
        output_dir: Optional[str | Path] = None,
    ) -> List[ConversionReport]:
        """Convert a sequence of PSD/PSB files concurrently using a thread pool."""
        src_list = [Path(p) for p in sources]
        out_root = Path(output_dir) if output_dir is not None else None

        def _worker(src: Path) -> ConversionReport:
            dst = (out_root / f"{src.stem}.png") if out_root is not None else src.with_suffix(".png")
            return self.convert_file(src, dst)

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            return list(pool.map(_worker, src_list))
