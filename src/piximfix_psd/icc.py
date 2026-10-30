"""8BIM Image Resource Block parser (ICC profiles, DPI resolution, and XMP metadata)."""

from __future__ import annotations

import struct
from typing import Dict, Optional, Tuple

from .binary_reader import BinaryReader, PsdFormatError
from .models import ImageResourceBlock, ResolutionInfo

RESOURCE_RESOLUTION_INFO = 0x03ED  # 1005: ResolutionInfo structure
RESOURCE_ICC_PROFILE = 0x040F      # 1039: Raw ICC profile bytes
RESOURCE_THUMBNAIL_RGB = 0x040C    # 1036: Thumbnail resource (Photoshop 5.0+)
RESOURCE_XMP_METADATA = 0x0424     # 1060: XMP packet


def parse_image_resources(section_bytes: bytes) -> Dict[int, ImageResourceBlock]:
    """Parse Section 3 (Image Resources) of a PSD/PSB stream into a map keyed by resource ID."""
    reader = BinaryReader(section_bytes)
    resources: Dict[int, ImageResourceBlock] = {}

    while reader.remaining >= 4:
        sig = reader.read_ascii(4)
        if sig not in ("8BIM", "MeSa", "PHUT", "DCSR"):
            raise PsdFormatError(f"Invalid Image Resource signature: {sig!r}")
        resource_id = reader.read_u16()
        name = reader.read_pascal_string(padding_multiple=2)
        data_size = reader.read_u32()
        data = reader.read_bytes(data_size)
        if data_size % 2 == 1 and reader.remaining >= 1:
            reader.skip(1)

        resources[resource_id] = ImageResourceBlock(
            signature=sig,
            resource_id=resource_id,
            name=name,
            data=data,
        )

    return resources


def extract_resolution_info(resources: Dict[int, ImageResourceBlock]) -> Optional[ResolutionInfo]:
    """Decode 8BIM 0x03ED ResolutionInfo (fixed-point 16.16 DPI values)."""
    block = resources.get(RESOURCE_RESOLUTION_INFO)
    if block is None or len(block.data) < 16:
        return None

    h_fixed, _h_unit, width_unit, v_fixed, _v_unit, height_unit = struct.unpack(
        ">IHH IHH", block.data[:16]
    )
    h_ppi = round(h_fixed / 65536.0, 2)
    v_ppi = round(v_fixed / 65536.0, 2)
    return ResolutionInfo(
        h_res_ppi=h_ppi,
        v_res_ppi=v_ppi,
        width_unit=width_unit,
        height_unit=height_unit,
    )


def extract_icc_profile(resources: Dict[int, ImageResourceBlock]) -> Optional[bytes]:
    """Extract raw ICC color profile bytes from 8BIM resource 0x040F if present."""
    block = resources.get(RESOURCE_ICC_PROFILE)
    if block is None or len(block.data) == 0:
        return None
    return block.data


def build_resolution_resource_block(h_ppi: float = 300.0, v_ppi: float = 300.0) -> bytes:
    """Build a valid 8BIM 0x03ED ResolutionInfo resource block."""
    h_fixed = int(round(h_ppi * 65536))
    v_fixed = int(round(v_ppi * 65536))
    payload = struct.pack(">IHH IHH", h_fixed, 1, 1, v_fixed, 1, 1)
    header = struct.pack(">4sHBB I", b"8BIM", RESOURCE_RESOLUTION_INFO, 0, 0, len(payload))
    return header + payload
