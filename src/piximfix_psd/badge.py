"""Crisp PSD/PSB corner badge renderer for Windows Explorer thumbnail previews."""

from __future__ import annotations

from typing import Dict, List, Tuple

# 3x5 bitmap glyphs for 'P', 'S', 'D', 'B'
_GLYPHS_3X5: Dict[str, List[str]] = {
    "P": [
        "111",
        "101",
        "111",
        "100",
        "100",
    ],
    "S": [
        "111",
        "100",
        "111",
        "001",
        "111",
    ],
    "D": [
        "110",
        "101",
        "101",
        "101",
        "110",
    ],
    "B": [
        "110",
        "101",
        "110",
        "101",
        "110",
    ],
}


def apply_psd_corner_badge(
    rgba_bytes: bytes,
    width: int,
    height: int,
    label: str = "PSD",
    badge_rgb: Tuple[int, int, int] = (0, 120, 215),
) -> bytes:
    """
    Render an Adobe-style corner pill badge ('PSD' or 'PSB') into the bottom-right
    corner of an RGBA image buffer.
    """
    if width < 12 or height < 8:
        return rgba_bytes

    buf = bytearray(rgba_bytes)
    text = (label.upper() or "PSD")[:3]
    scale = max(1, min(width, height) // 32)

    glyph_w = 3 * scale
    glyph_h = 5 * scale
    spacing = 1 * scale
    pad_x = 2 * scale
    pad_y = 1 * scale

    badge_w = len(text) * glyph_w + max(0, len(text) - 1) * spacing + 2 * pad_x
    badge_h = glyph_h + 2 * pad_y

    if badge_w >= width or badge_h >= height:
        return bytes(buf)

    x0 = width - badge_w - scale
    y0 = height - badge_h - scale

    # Fill rounded badge background
    br, bg, bb = badge_rgb
    for py in range(y0, y0 + badge_h):
        for px in range(x0, x0 + badge_w):
            idx = (py * width + px) * 4
            buf[idx] = br
            buf[idx + 1] = bg
            buf[idx + 2] = bb
            buf[idx + 3] = 255

    # Draw white bitmap characters
    cursor_x = x0 + pad_x
    cursor_y = y0 + pad_y
    for ch in text:
        pattern = _GLYPHS_3X5.get(ch, _GLYPHS_3X5["P"])
        for row_idx, row_bits in enumerate(pattern):
            for col_idx, bit in enumerate(row_bits):
                if bit == "1":
                    for sy in range(scale):
                        for sx in range(scale):
                            px = cursor_x + col_idx * scale + sx
                            py = cursor_y + row_idx * scale + sy
                            if 0 <= px < width and 0 <= py < height:
                                idx = (py * width + px) * 4
                                buf[idx] = 255
                                buf[idx + 1] = 255
                                buf[idx + 2] = 255
                                buf[idx + 3] = 255
        cursor_x += glyph_w + spacing

    return bytes(buf)
