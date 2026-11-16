"""Synthetic fail-closed tests plus original public-source receipt invariants."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research import audit_cirsium_three_run_gsi_fingerprints as audit


def _h(character: str) -> str:
    return character * 64


def _fixture():
    units = {
        u: {
            "fine_grid_candidate_count": 200,
            "gsi_source_complete_count": 180,
            "structural_source_complete_count": 160,
            "transferred_2p5pct_retained_cell_count": 4,
            "complete_link_patch_count": 2,
            "structural_order_sha256": _h("e"),
            "private_patch_sha256": _h("d"),
        } for u in audit.UNITS
    }
    frozen = {
        "status": "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED",
        "source_workflow_run": 37647225829,
        "units": units,
    }
    patterns = {
        "CIR02": [0, 0, 1],
        "CIR06": [0, 1, 0],
        "CIR12": [0, 0, 1],
        "CIR13": [0, 1, 1],
    }
    logs = {}
    for u in audit.UNITS:
        for idx, label in enumerate(audit.RUNS):
            shifted = bool(patterns[u][idx])
            blocks = [
                {
                    "schema_version": audit.SCHEMAS["grid"],
                    "status": audit.EXPECTED_STATUSES["grid"],
                    "cohort_unit_id": u,
                    "fine_grid_cell_count": 200,
                    "private_grid_sha256": _h("a"),
                    "field_outcomes_opened": False,
                },
                {
                    "schema_version": audit.SCHEMAS["gsi"],
                    "status": audit.EXPECTED_STATUSES["gsi"],
                    "cohort_unit_id": u,
                    "candidate_rows": 200,
                    "source_complete_rows": 180,
                    "provider_unavailable_rows": 10,
                    "terrain_vector_unavailable_rows": 10,
                    "chunk_count": 1,
                    "chunk_audits": [{"chunk_index": 0, "candidate_rows_input": 200, "source_complete_rows": 180}],
                    "terrain_feature_digest_sha256": _h("8" if shifted else "7"),
                    "private_gsi_frame_sha256": _h("9" if shifted else "6"),
                    "field_outcomes_opened": False,
                },
                {
                    "schema_version": audit.SCHEMAS["structural"],
                    "status": audit.EXPECTED_STATUSES["structural"],
                    "cohort_unit_id": u,
                    "candidate_rows": 200,
                    "source_complete_rows": 160,
                    "source_state_digest_sha256": _h("b"),
                    "private_structural_order_sha256": _h("c" if shifted else "e"),
                    "field_outcomes_opened": False,
                },
                {
                    "schema_version": audit.SCHEMAS["patch"],
                    "status": audit.EXPECTED_STATUSES["patch"],
                    "cohort_unit_id": u,
                    "source_complete_structural_order_rows": 160,
                    "retained_support_cell_count": 4,
                    "patch_count": 2,
                    "support_fraction": 0.025,
                    "patch_merge_distance_m": 1000.0,
                    "private_patch_sha256": _h("d"),
                    "field_outcomes_opened": False,
                },
            ]
            lines = []
            for block in blocks:
                for line in json.dumps(block, indent=2).splitlines():
                    lines.append("2026-10-08T00:00:00.0000000Z " + line)
            if label == "strict_audit_250" and shifted:
                lines.append("2026-10-08T00:00:00.0000000Z " + audit.FAIL_TEXT)
            logs[(label, u)] = "\n".join(lines) + "\n"
    return logs, frozen


def test_three_run_source_lock_and_two_fingerprint_modes():
    logs, frozen = _fixture()
    result = audit.audit_three_runs(logs, frozen)
    assert result["summary"]["historical_unit_jobs"] == 12
    assert result["summary"]["all_twelve_final_patch_files_match_original"] is True
    assert [result["units"][u]["gsi_feature_pattern_in_run_order"] for u in audit.UNITS] == [
        [0, 0, 1], [0, 1, 0], [0, 0, 1], [0, 1, 1]
    ]
    assert all(result["units"][u]["gsi_chunk_metadata_identical_all_three"] for u in audit.UNITS)
    assert result["boundaries"]["numerical_cpu_causality_proven"] is False


def test_unrelated_raw_stdout_is_ignored():
    logs, frozen = _fixture()
    key = ("replay_249", "CIR02")
    logs[key] = "random text with field names and imaginary coordinates\n" + logs[key]
    result = audit.audit_three_runs(logs, frozen)
    assert result["summary"]["historical_unit_jobs"] == 12
    assert "coordinates" not in json.dumps(result["units"]).lower()


@pytest.mark.parametrize("change,match", [
    ("patch_sha", "fixed metadata or final patch drift"),
    ("source_state", "fixed metadata or final patch drift"),
    ("chunk_rows", "GSI per-chunk audit drift"),
    ("original_rank", "original rank SHA"),
    ("candidate_count", "GSI denominator not preserved"),
    ("opened_field", "field-outcome gate"),
    ("missing_stage", "missing complete source stage"),
    ("wrong_threshold", "frozen 2.5%/1-km"),
    ("missing_log", "missing original job log"),
])
def test_fail_closed_on_mismatch(change: str, match: str):
    logs, frozen = _fixture()
    key = ("replay_249", "CIR02")
    if change == "patch_sha":
        logs[key] = logs[key].replace(_h("d"), _h("f"))
    elif change == "source_state":
        logs[key] = logs[key].replace(_h("b"), _h("f"))
    elif change == "chunk_rows":
        logs[key] = logs[key].replace('"candidate_rows_input": 200', '"candidate_rows_input": 199')
    elif change == "original_rank":
        key = ("original_247", "CIR02")
        logs[key] = logs[key].replace(_h("e"), _h("f"))
    elif change == "candidate_count":
        logs[key] = logs[key].replace('"fine_grid_cell_count": 200', '"fine_grid_cell_count": 201')
    elif change == "opened_field":
        logs[key] = logs[key].replace('"field_outcomes_opened": false', '"field_outcomes_opened": true', 1)
    elif change == "missing_stage":
        needle = '"schema_version": "' + audit.SCHEMAS["gsi"] + '"'
        logs[key] = logs[key].replace(needle, '"schema_version": "missing-source"')
    elif change == "wrong_threshold":
        logs[key] = logs[key].replace('"support_fraction": 0.025', '"support_fraction": 0.05')
    else:
        del logs[key]
    with pytest.raises(ValueError, match=match):
        audit.audit_three_runs(logs, frozen)


def test_pr250_failure_gate_must_agree_with_hash():
    logs, frozen = _fixture()
    key = ("strict_audit_250", "CIR02")
    logs[key] = logs[key].replace(audit.FAIL_TEXT, "")
    with pytest.raises(ValueError, match="PR250 fail-closed status"):
        audit.audit_three_runs(logs, frozen)


def test_original_public_frozen_snapshot_is_integrally_consistent():
    frozen = json.loads(audit.ORIGINAL_PATCH_RECEIPT.read_text(encoding="utf-8"))
    saved = json.loads(
        (audit.ROOT / "validation" / "cirsium_three_run_gsi_fingerprints_20261116.json").read_text(encoding="utf-8")
    )
    assert saved["run_order"] == list(audit.RUNS)
    assert saved["workflow_run_ids"] == {k: v[0] for k, v in audit.RUNS.items()}
    assert saved["source_receipt"] == str(audit.ORIGINAL_PATCH_RECEIPT.relative_to(audit.ROOT))
    assert saved["summary"]["all_twelve_final_patch_files_match_original"] is True
    assert saved["summary"]["all_twelve_full_orders_match_original"] is False
    assert set(saved["units"]) == set(audit.UNITS)
    for unit in audit.UNITS:
        expected = frozen["units"][unit]
        actual = saved["units"][unit]
        assert actual["candidate_rows"] == expected["fine_grid_candidate_count"]
        assert actual["gsi_source_complete_rows"] == expected["gsi_source_complete_count"]
        assert actual["original_frozen_patch_sha256"] == expected["private_patch_sha256"]
        assert actual["runs"]["original_247"]["structural_order_sha256"] == expected["structural_order_sha256"]
        assert all(v["final_patch_sha256"] == expected["private_patch_sha256"] for v in actual["runs"].values())
        assert all(v["source_state_sha256"] == actual["runs"]["original_247"]["source_state_sha256"]
                   for v in actual["runs"].values())
        assert all(v["grid_sha256"] == actual["runs"]["original_247"]["grid_sha256"]
                   for v in actual["runs"].values())
        assert actual["distinct_gsi_feature_signatures"] == 2
    serialized = json.dumps(saved, ensure_ascii=False)
    for sensitive in ["candidate_cell_id", "zone_member_site_ids", "longitude", "latitude"]:
        assert sensitive not in serialized
