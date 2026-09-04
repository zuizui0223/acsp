#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from acsp.structural_support import BASELINE_FAMILY, FAMILY_COMPONENTS

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "validation" / "cirsium_structural_selector_execution_freeze_v1.json"
FAMILY_CONTRACT = ROOT / "validation" / "cirsium_structural_selector_family_contract_v1.json"
COHORT = ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"


def validate() -> dict[str, object]:
    execution = json.loads(EXECUTION.read_text(encoding="utf-8"))
    family_contract = json.loads(FAMILY_CONTRACT.read_text(encoding="utf-8"))
    with COHORT.open(encoding="utf-8", newline="") as handle:
        cohort = list(csv.DictReader(handle))

    assert execution["status"] == "ALGORITHM_FROZEN_PRIVATE_FRAMES_NOT_YET_EXECUTED"
    assert execution["field_outcomes_opened"] is False
    assert execution["private_candidate_frames_built"] is False
    assert execution["public_patch_manifest_built"] is False
    assert execution["cohort_size"] == len(cohort) == 13
    assert execution["feature_weights_fitted"] is False
    assert execution["field_outcome_columns_allowed_in_generation"] is False
    assert execution["post_outcome_family_switch_allowed"] is False
    assert execution["matched_candidate_count_within_unit"] is True
    assert execution["matched_field_effort_claim"] is False

    code_components = {family: list(columns) for family, columns in FAMILY_COMPONENTS.items()}
    code_components[BASELINE_FAMILY] = []
    assert execution["family_components"] == code_components

    contract_families = set(family_contract["families"])
    assert set(execution["family_components"]) <= contract_families
    assert family_contract["no_post_outcome_feature_family_switch"] is True

    method_counts = Counter(row["method_arm"] for row in cohort)
    assert method_counts == Counter(
        {"STRUCTURAL_LOCAL": 8, "STRUCTURAL_SENTINEL": 4, "SPATIAL_BASELINE_ONLY": 1}
    )
    for row in cohort:
        family = row["structural_feature_family"]
        arm = row["method_arm"]
        assert family in execution["family_components"]
        assert arm in execution["method_sets"]
        if arm == "SPATIAL_BASELINE_ONLY":
            assert family == BASELINE_FAMILY
        else:
            assert execution["family_components"][family]
        assert row["outcome_opened"] == "false"
        assert row["candidate_patch_status"] == "NOT_BUILT"

    policy = execution["public_sensitive_coordinate_policy"]
    assert policy["exact_coordinates_written"] is False
    assert policy["raw_candidate_ids_written"] is False
    assert policy["private_salt_committed"] is False
    assert "HMAC-SHA256" in policy["public_patch_identifier"]

    return {
        "status": "OK",
        "cohort_size": len(cohort),
        "method_arm_counts": dict(method_counts),
        "family_count": len(execution["family_components"]),
        "algorithm_frozen": True,
        "real_candidate_patches_built": False,
        "field_outcomes_opened": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
