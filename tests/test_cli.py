"""Unit tests for the `piximfix-psd` CLI commands (`inspect`, `convert`, `batch`)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from piximfix_psd.cli import main
from piximfix_psd.parser import build_synthetic_psd


def test_cli_inspect_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    psd_file = tmp_path / "sample.psd"
    psd_file.write_bytes(
        build_synthetic_psd(width=20, height=15, layer_names=["BG", "Headline"])
    )

    rc = main(["inspect", str(psd_file), "--layers"])
    assert rc == 0
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert payload["width"] == 20
    assert payload["height"] == 15
    assert payload["layer_count"] == 2
    assert len(payload["layers"]) == 2


def test_cli_convert_and_batch(tmp_path: Path) -> None:
    psd_file = tmp_path / "banner.psd"
    out_png = tmp_path / "banner_out.png"
    psd_file.write_bytes(build_synthetic_psd(width=28, height=28))

    rc = main(["convert", str(psd_file), "-o", str(out_png), "--badge"])
    assert rc == 0
    assert out_png.exists()

    batch_out = tmp_path / "batch_exports"
    rc_batch = main(["batch", str(tmp_path), "-o", str(batch_out), "--badge", "-w", "2"])
    assert rc_batch == 0
    assert (batch_out / "banner.png").exists()
