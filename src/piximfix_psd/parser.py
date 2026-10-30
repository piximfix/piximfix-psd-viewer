"""Binary parser and synthetic generator for Adobe Photoshop .PSD (v1) and .PSB (v2) files."""

from __future__ import annotations

from pathlib import Path
import struct
from typing import List, Optional, Sequence, Tuple

from .binary_reader import BinaryReader, PsdFormatError
from .icc import (
    build_resolution_resource_block,
    extract_icc_profile,
    extract_resolution_info,
    parse_image_resources,
)
from .models import (
    ChannelInfo,
    ColorMode,
    CompressionMethod,
    LayerRecord,
    PsdDocument,
    PsdHeader,
)
from .rle import (
    decode_packbits_row,
    encode_packbits_row,
    interleave_planar_channels_to_rgba,
)


def parse_psd_header(reader: BinaryReader) -> PsdHeader:
    """Parse the 26-byte File Header section of a PSD or PSB stream."""
    if reader.remaining < 26:
        raise PsdFormatError("Stream is shorter than 26-byte PSD header")

    signature = reader.read_ascii(4)
    if signature != "8BPS":
        raise PsdFormatError(f"Invalid PSD signature {signature!r}; expected '8BPS'")

    version = reader.read_u16()
    if version not in (1, 2):
        raise PsdFormatError(f"Unsupported PSD version {version}; expected 1 (PSD) or 2 (PSB)")

    reserved = reader.read_bytes(6)
    if reserved != b"\x00" * 6:
        raise PsdFormatError("Non-zero reserved bytes in PSD header")

    channels = reader.read_u16()
    if not (1 <= channels <= 56):
        raise PsdFormatError(f"Invalid channel count {channels}; must be 1..56")

    height = reader.read_u32()
    width = reader.read_u32()
    max_dim = 300_000 if version == 2 else 30_000
    if not (1 <= height <= max_dim and 1 <= width <= max_dim):
        raise PsdFormatError(
            f"Invalid canvas dimensions {width}x{height} for version {version}"
        )

    depth = reader.read_u16()
    if depth not in (1, 8, 16, 32):
        raise PsdFormatError(f"Unsupported bit depth {depth}")

    raw_mode = reader.read_u16()
    try:
        color_mode = ColorMode(raw_mode)
    except ValueError as exc:
        raise PsdFormatError(f"Unknown PSD color mode {raw_mode}") from exc

    return PsdHeader(
        signature=signature,
        version=version,
        channels=channels,
        height=height,
        width=width,
        depth=depth,
        color_mode=color_mode,
    )


def _parse_layer_records(reader: BinaryReader, is_psb: bool) -> List[LayerRecord]:
    """Parse Layer Info records inside Section 4 (Layer and Mask Information)."""
    layer_info_len = reader.read_length_field(is_psb)
    if layer_info_len == 0:
        return []

    end_offset = reader.position + layer_info_len
    raw_layer_count = reader.read_i16()
    layer_count = abs(raw_layer_count)

    layers: List[LayerRecord] = []
    for _ in range(layer_count):
        top = reader.read_i32()
        left = reader.read_i32()
        bottom = reader.read_i32()
        right = reader.read_i32()
        num_channels = reader.read_u16()

        channels: List[ChannelInfo] = []
        for _ch in range(num_channels):
            ch_id = reader.read_i16()
            ch_len = reader.read_length_field(is_psb)
            channels.append(ChannelInfo(channel_id=ch_id, data_length=ch_len))

        blend_sig = reader.read_ascii(4)
        if blend_sig != "8BIM":
            raise PsdFormatError(f"Invalid layer blend mode signature {blend_sig!r}")
        blend_mode = reader.read_ascii(4)
        opacity = reader.read_u8()
        clipping = reader.read_u8()
        flags = reader.read_u8()
        _filler = reader.read_u8()

        extra_len = reader.read_u32()
        extra_end = reader.position + extra_len

        # Layer mask data
        mask_len = reader.read_u32()
        reader.skip(mask_len)

        # Layer blending ranges
        ranges_len = reader.read_u32()
        reader.skip(ranges_len)

        # Layer name (Pascal string padded to 4 bytes)
        layer_name = reader.read_pascal_string(padding_multiple=4)

        is_group_start = False
        is_group_end = False

        # Scan additional layer information blocks (e.g. lsct section divider)
        while reader.position + 12 <= extra_end:
            sig = reader.read_ascii(4)
            if sig not in ("8BIM", "8B64"):
                break
            key = reader.read_ascii(4)
            block_len = reader.read_u32()
            block_end = reader.position + block_len
            if key == "lsct" and block_len >= 4:
                divider_type = reader.read_u32()
                if divider_type in (1, 2):
                    is_group_start = True
                elif divider_type == 3:
                    is_group_end = True
            reader.seek(block_end)
            if block_len % 2 == 1 and reader.position < extra_end:
                reader.skip(1)

        reader.seek(extra_end)

        layers.append(
            LayerRecord(
                name=layer_name,
                top=top,
                left=left,
                bottom=bottom,
                right=right,
                channels=channels,
                blend_mode=blend_mode,
                opacity=opacity,
                clipping=clipping,
                flags=flags,
                is_group_start=is_group_start,
                is_group_end=is_group_end,
            )
        )

    reader.seek(end_offset)
    return layers


def _parse_composite_image_data(
    reader: BinaryReader,
    header: PsdHeader,
) -> Tuple[CompressionMethod, bytes]:
    """Parse Section 5 (Image Data Section) into composite RGBA bytes."""
    raw_comp = reader.read_u16()
    try:
        compression = CompressionMethod(raw_comp)
    except ValueError as exc:
        raise PsdFormatError(f"Unsupported compression method {raw_comp}") from exc

    width = header.width
    height = header.height
    channels = header.channels
    bytes_per_channel_row = width * max(1, header.depth // 8)

    planes: List[bytes] = []

    if compression == CompressionMethod.RAW:
        plane_size = bytes_per_channel_row * height
        for _ in range(channels):
            planes.append(reader.read_bytes(plane_size))
    elif compression == CompressionMethod.RLE_PACKBITS:
        total_rows = channels * height
        row_byte_counts: List[int] = []
        for _ in range(total_rows):
            count = reader.read_u32() if header.is_psb else reader.read_u16()
            row_byte_counts.append(count)

        row_idx = 0
        for _ch in range(channels):
            channel_buf = bytearray()
            for _y in range(height):
                encoded_len = row_byte_counts[row_idx]
                row_idx += 1
                encoded_row = reader.read_bytes(encoded_len)
                decoded_row = decode_packbits_row(encoded_row, bytes_per_channel_row)
                channel_buf.extend(decoded_row)
            planes.append(bytes(channel_buf))
    else:
        raise PsdFormatError(f"Compression method {compression.name} not supported in composite section")

    composite_rgba = interleave_planar_channels_to_rgba(
        planes, width=width, height=height, color_mode=int(header.color_mode)
    )
    return compression, composite_rgba


def parse_psd_bytes(data: bytes) -> PsdDocument:
    """Parse a complete PSD (v1) or PSB (v2) byte buffer into a `PsdDocument`."""
    reader = BinaryReader(data)
    header = parse_psd_header(reader)

    # Section 2: Color Mode Data
    color_mode_len = reader.read_u32()
    color_mode_data = reader.read_bytes(color_mode_len)

    # Section 3: Image Resources
    resources_len = reader.read_u32()
    resources_raw = reader.read_bytes(resources_len)
    resources = parse_image_resources(resources_raw)
    resolution = extract_resolution_info(resources)
    icc_profile = extract_icc_profile(resources)

    # Section 4: Layer and Mask Information
    layer_mask_len = reader.read_length_field(header.is_psb)
    layer_mask_end = reader.position + layer_mask_len
    layers: List[LayerRecord] = []
    if layer_mask_len > 0:
        layers = _parse_layer_records(reader, header.is_psb)
        reader.seek(layer_mask_end)

    # Section 5: Composite Image Data
    compression, composite_rgba = _parse_composite_image_data(reader, header)

    return PsdDocument(
        header=header,
        color_mode_data=color_mode_data,
        resources=resources,
        layers=layers,
        compression=compression,
        composite_rgba=composite_rgba,
        resolution=resolution,
        icc_profile_bytes=icc_profile,
    )


def parse_psd_file(path: str | Path) -> PsdDocument:
    """Read and parse a .PSD or .PSB file from disk."""
    file_path = Path(path)
    return parse_psd_bytes(file_path.read_bytes())


def build_synthetic_psd(
    width: int = 16,
    height: int = 16,
    channels: int = 4,
    version: int = 1,
    color_mode: ColorMode = ColorMode.RGB,
    compression: CompressionMethod = CompressionMethod.RLE_PACKBITS,
    layer_names: Optional[Sequence[str]] = None,
    dpi: float = 300.0,
) -> bytes:
    """
    Construct a spec-compliant binary .PSD (version=1) or .PSB (version=2) buffer
    for automated unit testing, benchmarking, and CLI verification.
    """
    is_psb = version == 2
    header_bytes = struct.pack(
        ">4sH6sHIIHH",
        b"8BPS",
        version,
        b"\x00" * 6,
        channels,
        height,
        width,
        8,
        int(color_mode),
    )

    # Section 2: Empty Color Mode Data
    section2 = struct.pack(">I", 0)

    # Section 3: Image Resources (300 DPI ResolutionInfo)
    res_block = build_resolution_resource_block(dpi, dpi)
    section3 = struct.pack(">I", len(res_block)) + res_block

    # Section 4: Layer and Mask Information
    names = list(layer_names) if layer_names is not None else ["Background", "Logo Overlay"]
    layer_records_buf = bytearray()
    channel_payloads_buf = bytearray()

    for name in names:
        layer_records_buf.extend(struct.pack(">iiiiH", 0, 0, height, width, 4))
        for ch_id in (0, 1, 2, -1):
            ch_data = b"\x00\x00" + (b"\x80" * (width * height))
            if is_psb:
                layer_records_buf.extend(struct.pack(">hQ", ch_id, len(ch_data)))
            else:
                layer_records_buf.extend(struct.pack(">hI", ch_id, len(ch_data)))
            channel_payloads_buf.extend(ch_data)

        layer_records_buf.extend(b"8BIMnorm")
        layer_records_buf.extend(struct.pack(">BBBB", 255, 0, 0, 0))

        # Pascal string padded to 4 bytes
        encoded_name = name.encode("latin1")[:255]
        pascal_len = 1 + len(encoded_name)
        pad = (4 - (pascal_len % 4)) % 4
        pascal_bytes = bytes([len(encoded_name)]) + encoded_name + (b"\x00" * pad)

        extra_data = struct.pack(">II", 0, 0) + pascal_bytes
        layer_records_buf.extend(struct.pack(">I", len(extra_data)) + extra_data)

    layer_info_body = struct.pack(">h", len(names)) + bytes(layer_records_buf) + bytes(channel_payloads_buf)
    if len(layer_info_body) % 2 == 1:
        layer_info_body += b"\x00"

    if is_psb:
        layer_info_section = struct.pack(">Q", len(layer_info_body)) + layer_info_body
        section4 = struct.pack(">Q", len(layer_info_section)) + layer_info_section
    else:
        layer_info_section = struct.pack(">I", len(layer_info_body)) + layer_info_body
        section4 = struct.pack(">I", len(layer_info_section)) + layer_info_section

    # Section 5: Composite Image Data
    planes: List[List[bytes]] = []
    for ch in range(channels):
        rows: List[bytes] = []
        for y in range(height):
            if ch == 3:
                row = bytes([255] * width)
            else:
                row = bytes([((x * 17 + y * 31 + ch * 67) & 0xFF) for x in range(width)])
            rows.append(row)
        planes.append(rows)

    if compression == CompressionMethod.RAW:
        section5 = bytearray(struct.pack(">H", int(CompressionMethod.RAW)))
        for ch_rows in planes:
            for row in ch_rows:
                section5.extend(row)
    else:
        section5 = bytearray(struct.pack(">H", int(CompressionMethod.RLE_PACKBITS)))
        encoded_rows: List[bytes] = []
        for ch_rows in planes:
            for row in ch_rows:
                encoded_rows.append(encode_packbits_row(row))
        for enc in encoded_rows:
            if is_psb:
                section5.extend(struct.pack(">I", len(enc)))
            else:
                section5.extend(struct.pack(">H", len(enc)))
        for enc in encoded_rows:
            section5.extend(enc)

    return header_bytes + section2 + section3 + section4 + bytes(section5)
