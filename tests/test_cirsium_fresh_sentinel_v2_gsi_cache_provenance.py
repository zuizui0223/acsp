from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.audit_cirsium_fresh_sentinel_v2_gsi_cache_provenance import (
    audit_gsi_cache_provenance,
    main,
)


def _cache(tmp_path: Path) -> Path:
    cache = tmp_path / "private-gsi-cache"
    for rel, contents in (
        ("gsi_dem_tiles/dem5a_png/15/300/401.png", b"raw-first-tile"),
        ("gsi_dem_tiles/dem5a_png/15/300/402.png", b"raw-second-tile"),
        ("app_layers/gsi_a2b3c4d5.tif", b"private-mosaic"),
    ):
        path = cache / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    return cache


def test_gsi_source_inventory_is_coordinate_free_and_read_only(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    original_contents = (cache / "app_layers/gsi_a2b3c4d5.tif").read_bytes()
    result = audit_gsi_cache_provenance(cache, unit_id="CIR06")
    assert result["tile_file_count"] == 2
    assert result["mosaic_file_count"] == 1
    assert result["tile_total_bytes"] > 0
    assert result["mosaic_total_bytes"] == len(original_contents)
    assert len(result["tile_inventory_sha256"]) == 64
    assert len(result["mosaic_inventory_sha256"]) == 64
    assert result["coordinate_bearing_filenames_exported"] is False
    assert result["files_read_only"] is True
    assert result["field_selector_validation"] is False
    assert (cache / "app_layers/gsi_a2b3c4d5.tif").read_bytes() == original_contents
    serialized = json.dumps(result)
    for token in ("300/401.png", "300/402.png", "gsi_a2b3c4d5.tif", "longitude", "latitude"):
        assert token not in serialized


def test_inventory_changes_when_tile_bytes_change_but_mosaic_does_not(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    first = audit_gsi_cache_provenance(cache, unit_id="CIR02")
    (cache / "gsi_dem_tiles/dem5a_png/15/300/402.png").write_bytes(b"changed-tile-data")
    second = audit_gsi_cache_provenance(cache, unit_id="CIR02")
    assert first["tile_inventory_sha256"] != second["tile_inventory_sha256"]
    assert first["mosaic_inventory_sha256"] == second["mosaic_inventory_sha256"]


def test_inventory_changes_when_mosaic_bytes_change_but_tiles_do_not(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    first = audit_gsi_cache_provenance(cache, unit_id="CIR13")
    (cache / "app_layers/gsi_a2b3c4d5.tif").write_bytes(b"changed-mosaic")
    second = audit_gsi_cache_provenance(cache, unit_id="CIR13")
    assert first["tile_inventory_sha256"] == second["tile_inventory_sha256"]
    assert first["mosaic_inventory_sha256"] != second["mosaic_inventory_sha256"]


def test_empty_category_is_not_a_successful_source_inventory(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    for p in (cache / "gsi_dem_tiles").rglob("*.png"):
        p.unlink()
    with pytest.raises(ValueError, match="missing required GSI"):
        audit_gsi_cache_provenance(cache, unit_id="CIR12")


def test_cli_never_overwrites_a_public_safe_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    cache = _cache(tmp_path)
    out = tmp_path / "public-summary.json"
    monkeypatch.setattr(sys, "argv", [
        "audit", "--unit-id", "CIR06", "--cache-dir", str(cache),
        "--public-safe-summary-json", str(out),
    ])
    assert main() == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["tile_file_count"] == 2
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        main()


def test_public_repo_cache_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside the repository"):
        audit_gsi_cache_provenance(Path(__file__).resolve().parents[1], unit_id="CIR06")
