"""
PiximFix PSD Viewer & Batch Conversion Engine.

Provides zero-dependency binary parsing for Adobe Photoshop .PSD (v1) and .PSB (v2)
documents, 8BIM image resource inspection, layer tree traversal, PackBits RLE
decompression, PSD corner badge overlay rendering, and batch export pipelines.
"""

from .models import (
    BlendMode,
    ChannelInfo,
    ColorMode,
    CompressionMethod,
    ConversionReport,
    ImageResourceBlock,
    LayerRecord,
    PsdDocument,
    PsdHeader,
    ResolutionInfo,
)
from .parser import build_synthetic_psd, parse_psd_bytes, parse_psd_file
from .converter import BatchPsdConverter, export_rgba_to_png_bytes
from .badge import apply_psd_corner_badge

__version__ = "1.1.0"

__all__ = [
    "BlendMode",
    "ChannelInfo",
    "ColorMode",
    "CompressionMethod",
    "ConversionReport",
    "ImageResourceBlock",
    "LayerRecord",
    "PsdDocument",
    "PsdHeader",
    "ResolutionInfo",
    "apply_psd_corner_badge",
    "build_synthetic_psd",
    "export_rgba_to_png_bytes",
    "parse_psd_bytes",
    "parse_psd_file",
    "BatchPsdConverter",
]
