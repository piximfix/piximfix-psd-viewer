"""Command-line interface (`piximfix-psd`) for inspecting and converting .PSD / .PSB files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional, Sequence

from .converter import BatchPsdConverter
from .parser import parse_psd_file


def _cmd_inspect(args: argparse.Namespace) -> int:
    doc = parse_psd_file(args.file)
    payload = doc.summary_dict()
    if args.layers:
        payload["layers"] = [
            {
                "name": layer.name,
                "bounds": [layer.left, layer.top, layer.right, layer.bottom],
                "width": layer.width,
                "height": layer.height,
                "opacity": layer.opacity,
                "blend_mode": layer.blend_mode,
                "visible": layer.visible,
            }
            for layer in doc.layers
        ]
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_convert(args: argparse.Namespace) -> int:
    converter = BatchPsdConverter(apply_badge=args.badge)
    report = converter.convert_file(args.input, args.output)
    if not report.success:
        print(f"Error converting {args.input}: {report.error}", file=sys.stderr)
        return 1
    print(
        f"Converted {report.source_path} -> {report.output_path} "
        f"({report.width}x{report.height}, {report.output_bytes} bytes in {report.elapsed_ms} ms)"
    )
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    in_dir = Path(args.input_dir)
    files: List[Path] = sorted(
        list(in_dir.glob("*.psd")) + list(in_dir.glob("*.psb"))
    )
    converter = BatchPsdConverter(apply_badge=args.badge, max_workers=args.workers)
    reports = converter.convert_batch(files, output_dir=args.output_dir)
    succeeded = sum(1 for r in reports if r.success)
    print(f"Batch complete: {succeeded}/{len(reports)} files converted.")
    return 0 if succeeded == len(reports) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="piximfix-psd",
        description="PiximFix PSD/PSB Inspector, Thumbnail Badge Renderer & Batch Converter",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="Inspect PSD/PSB header, resources, and layer tree")
    p_inspect.add_argument("file", help="Path to .psd or .psb file")
    p_inspect.add_argument("--layers", action="store_true", help="Include layer records in JSON output")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_convert = sub.add_parser("convert", help="Convert a single PSD/PSB file to PNG")
    p_convert.add_argument("input", help="Source .psd or .psb path")
    p_convert.add_argument("-o", "--output", help="Destination .png path")
    p_convert.add_argument("--badge", action="store_true", help="Overlay PSD/PSB corner badge")
    p_convert.set_defaults(func=_cmd_convert)

    p_batch = sub.add_parser("batch", help="Batch convert all PSD/PSB files in a directory")
    p_batch.add_argument("input_dir", help="Directory containing .psd/.psb files")
    p_batch.add_argument("-o", "--output-dir", help="Output directory for converted PNGs")
    p_batch.add_argument("--badge", action="store_true", help="Overlay PSD/PSB corner badge")
    p_batch.add_argument("-w", "--workers", type=int, default=4, help="Worker thread count")
    p_batch.set_defaults(func=_cmd_batch)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
