from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.audit_cirsium_fresh_sentinel_v2_chunk_logs import (
    PAIRS,
    audit_chunk_log_pairs,
)


def _make_log(unit: str, *, changed_chunk: bool = False, changed_software: bool = False) -> str:
    count = 81 if unit == "CIR06" else 237
    rows = []
    for i in range(count):
        rows.append({
            "chunk_index": i,
            "candidate_rows_input": 100,
            "source_complete_rows": 80,
            "provider_unavailable_rows": 0,
            "terrain_vector_unavailable_rows": 20,
            "gsi_attribution": "GSI DEM5A" if not changed_chunk or i != 0 else "GSI DEM10B",
            "status": "SOURCE_ACQUIRED",
        })
    data = {"terrain_feature_digest_sha256": "a" * 64, "chunk_audits": rows}
    lines = [
        "##[group]Runner Image",
        "Image: ubuntu-24.04",
        "Version: 20261004.327.1",
        "##[endgroup]",
        "Successfully installed numpy-2.4.6 pandas-3.0.6 " + (
            "rasterio-9.9.9" if changed_software else "rasterio-1.4.4"
        ),
        *json.dumps(data, indent=2).splitlines(),
    ]
    return "\n".join("2026-10-08T04:00:00.0000000Z " + row for row in lines)


def _pairs(tmp_path: Path) -> dict[str, tuple[Path, Path]]:
    rows = {}
    for unit in PAIRS:
        old = tmp_path / f"{unit}_old.log"
        new = tmp_path / f"{unit}_new.log"
        old.write_text(_make_log(unit), encoding="utf-8")
        new.write_text(_make_log(unit), encoding="utf-8")
        rows[unit] = (old, new)
    return rows


def test_exact_chunk_metadata_and_package_parity(tmp_path: Path) -> None:
    result = audit_chunk_log_pairs(_pairs(tmp_path))
    assert result["status"] == "CHUNK_METADATA_REPLAY_IDENTICAL_SOURCE_CONTENT_DRIFT_UNRESOLVED"
    assert result["units"]["CIR06"]["chunk_count"] == 81
    assert result["units"]["CIR13"]["chunk_count"] == 237
    assert result["units"]["CIR06"]["matching_chunk_audit_count"] == 81
    assert result["units"]["CIR13"]["matching_chunk_audit_count"] == 237
    assert result["units"]["CIR06"]["installed_package_versions_identical"] is True
    assert result["units"]["CIR13"]["runner_image_version_identical"] is True
    assert result["claim_boundary"]["source_tile_png_bytes_equal_verified"] is False
    assert result["claim_boundary"]["source_mosaic_bytes_equal_verified"] is False
    assert result["claim_boundary"]["source_drift_mechanism_identified"] is False


def test_one_changed_chunk_attribution_cannot_appear_identical(tmp_path: Path) -> None:
    paths = _pairs(tmp_path)
    paths["CIR06"][1].write_text(_make_log("CIR06", changed_chunk=True), encoding="utf-8")
    result = audit_chunk_log_pairs(paths)
    assert result["units"]["CIR06"]["matching_chunk_audit_count"] == 80
    assert result["units"]["CIR06"]["all_chunk_audits_identical"] is False
    assert result["claim_boundary"]["all_source_chunk_attributions_and_completion_counts_identical"] is False


def test_package_change_is_separate_from_chunk_change(tmp_path: Path) -> None:
    paths = _pairs(tmp_path)
    paths["CIR13"][1].write_text(_make_log("CIR13", changed_software=True), encoding="utf-8")
    result = audit_chunk_log_pairs(paths)
    assert result["units"]["CIR13"]["installed_package_versions_identical"] is False
    assert result["units"]["CIR13"]["all_chunk_audits_identical"] is True


def test_invalid_chunk_denominator_fails_closed(tmp_path: Path) -> None:
    paths = _pairs(tmp_path)
    path = paths["CIR06"][0]
    path.write_text(
        path.read_text().replace('"source_complete_rows": 80', '"source_complete_rows": 81', 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="denominator not preserved"):
        audit_chunk_log_pairs(paths)


def test_missing_or_extra_cohort_fails_closed(tmp_path: Path) -> None:
    paths = _pairs(tmp_path)
    paths.pop("CIR06")
    with pytest.raises(ValueError, match="exactly CIR06 and CIR13"):
        audit_chunk_log_pairs(paths)


def test_log_report_never_contains_input_logs_or_coordinates(tmp_path: Path) -> None:
    result = audit_chunk_log_pairs(_pairs(tmp_path))
    encoded = json.dumps(result)
    for literal in ("latitude", "longitude", "candidate_cell_id", "zone_member_site_ids"):
        assert literal not in encoded
