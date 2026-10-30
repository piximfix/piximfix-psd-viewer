"""Data models representing Adobe Photoshop (.PSD / .PSB) binary structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple


class ColorMode(IntEnum):
    """Photoshop file header color modes."""

    BITMAP = 0
    GRAYSCALE = 1
    INDEXED = 2
    RGB = 3
    CMYK = 4
    MULTICHANNEL = 7
    DUOTONE = 8
    LAB = 9


class CompressionMethod(IntEnum):
    """Photoshop channel image data compression methods."""

    RAW = 0
    RLE_PACKBITS = 1
    ZIP_WITHOUT_PREDICTION = 2
    ZIP_WITH_PREDICTION = 3


class BlendMode:
    """Standard 4-byte ASCII blend mode keys in Photoshop layer records."""

    PASS_THROUGH = "pass"
    NORMAL = "norm"
    DISSOLVE = "diss"
    DARKEN = "dark"
    MULTIPLY = "mul "
    COLOR_BURN = "idiv"
    LINEAR_BURN = "lbrn"
    LIGHTEN = "lite"
    SCREEN = "scrn"
    COLOR_DODGE = "div "
    LINEAR_DODGE = "lddg"
    OVERLAY = "over"
    SOFT_LIGHT = "sLit"
    HARD_LIGHT = "hLit"
    DIFFERENCE = "diff"
    EXCLUSION = "smud"


@dataclass(frozen=True)
class PsdHeader:
    """26-byte File Header Section of a PSD (v1) or PSB (v2) document."""

    signature: str
    version: int
    channels: int
    height: int
    width: int
    depth: int
    color_mode: ColorMode

    @property
    def is_psb(self) -> bool:
        """Return True if the document is a 64-bit Large Document Format (.PSB)."""
        return self.version == 2

    @property
    def format_label(self) -> str:
        """Return 'PSB' for version 2 or 'PSD' for version 1."""
        return "PSB" if self.is_psb else "PSD"

    @property
    def megapixels(self) -> float:
        """Return total canvas area in megapixels."""
        return round((self.width * self.height) / 1_000_000.0, 4)


@dataclass(frozen=True)
class ResolutionInfo:
    """Parsed 8BIM 0x03ED ResolutionInfo structure."""

    h_res_ppi: float
    v_res_ppi: float
    width_unit: int = 1
    height_unit: int = 1


@dataclass(frozen=True)
class ImageResourceBlock:
    """Single 8BIM Image Resource Block from Section 3 of a PSD file."""

    signature: str
    resource_id: int
    name: str
    data: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.data)


@dataclass(frozen=True)
class ChannelInfo:
    """Channel id and byte length entry inside a Layer Record."""

    channel_id: int
    data_length: int


@dataclass
class LayerRecord:
    """Metadata and bounding box for a single Photoshop layer."""

    name: str
    top: int
    left: int
    bottom: int
    right: int
    channels: List[ChannelInfo]
    blend_mode: str = BlendMode.NORMAL
    opacity: int = 255
    clipping: int = 0
    flags: int = 0
    is_group_start: bool = False
    is_group_end: bool = False
    children: List["LayerRecord"] = field(default_factory=list)

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def visible(self) -> bool:
        """Bit 1 of layer flags indicates 'invisible' in the PSD specification."""
        return (self.flags & 0x02) == 0

    @property
    def opacity_percent(self) -> float:
        return round((self.opacity / 255.0) * 100.0, 1)


@dataclass
class PsdDocument:
    """Complete parsed representation of a PSD or PSB file."""

    header: PsdHeader
    color_mode_data: bytes
    resources: Dict[int, ImageResourceBlock]
    layers: List[LayerRecord]
    compression: CompressionMethod
    composite_rgba: bytes
    resolution: Optional[ResolutionInfo] = None
    icc_profile_bytes: Optional[bytes] = None

    @property
    def has_icc_profile(self) -> bool:
        return self.icc_profile_bytes is not None and len(self.icc_profile_bytes) > 0

    def summary_dict(self) -> Dict[str, object]:
        """Return a serializable dictionary of document metadata."""
        return {
            "format": self.header.format_label,
            "version": self.header.version,
            "width": self.header.width,
            "height": self.header.height,
            "channels": self.header.channels,
            "depth": self.header.depth,
            "color_mode": self.header.color_mode.name,
            "megapixels": self.header.megapixels,
            "compression": self.compression.name,
            "layer_count": len(self.layers),
            "resource_count": len(self.resources),
            "has_icc_profile": self.has_icc_profile,
            "resolution_ppi": (
                (self.resolution.h_res_ppi, self.resolution.v_res_ppi)
                if self.resolution
                else None
            ),
        }


@dataclass(frozen=True)
class ConversionReport:
    """Telemetry report returned after converting a single PSD/PSB file."""

    source_path: str
    output_path: str
    width: int
    height: int
    layer_count: int
    elapsed_ms: float
    output_bytes: int
    badged: bool
    success: bool
    error: Optional[str] = None
