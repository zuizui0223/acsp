from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2_replication.json"
V2_PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2.json"
SOURCE_PATH = ROOT / "validation" / "geographic_framing_development_v4" / "predeclared_taxon_region_pairs.csv"
EXPECTED_FINGERPRINT = "66d5eba6d5e92e89bcf941b40aa0cec91f39479c25bb8c5e1a0f403b50d3a94c"
EXPECTED_V2_FINGERPRINT = "7535e749d3cc04c8d49db13957da53685a5050eec7d1e9e2d6624348332a56f9"


def load_protocol(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint"))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != calculated:
        raise AssertionError(f"protocol fingerprint mismatch: {stored} != {calculated}")
    payload["protocol_fingerprint"] = stored
    return payload


def cohort_for_offset(frame: pd.DataFrame, offset: int) -> pd.DataFrame:
    rows = []
    for region in range(1, 13):
        wanted = (region + offset) % 4
        for group in ("plant", "animal"):
            hit = frame[
                (pd.to_numeric(frame["region_cell_index"]) == region)
                & (frame["taxon_group"].astype(str) == group)
                & (pd.to_numeric(frame["record_count_stratum"]) == wanted)
            ]
            if len(hit) != 1:
                raise AssertionError(
                    f"expected one v4 row for region={region}, group={group}, stratum={wanted}; found {len(hit)}"
                )
            rows.append(hit.iloc[0])
    return pd.DataFrame(rows).reset_index(drop=True)


class ReplicationContractTests(unittest.TestCase):
    def test_protocol_is_conditional_and_fingerprinted_before_v2_outcome(self):
        protocol = load_protocol(PROTOCOL_PATH)
        self.assertEqual(protocol["protocol_fingerprint"], EXPECTED_FINGERPRINT)
        self.assertEqual(protocol["status"], "conditional_predeclared_before_v2_outcome_execute_only_if_v2_passes")
        self.assertEqual(protocol["upstream_v2"]["authoritative_protocol_fingerprint"], EXPECTED_V2_FINGERPRINT)
        self.assertEqual(protocol["upstream_v2"]["execution_trigger"], "all_v2_development_gates_pass")
        self.assertFalse(protocol["upstream_v2"]["execute_if_v2_fails"])
        self.assertFalse(protocol["cohort"]["identities_opened_by_preregistration"])
        self.assertFalse(protocol["decision"]["retuning_on_replication_taxa_allowed"])

    def test_replication_method_matches_authoritative_v2_scientific_constants(self):
        replication = load_protocol(PROTOCOL_PATH)
        v2 = json.loads(V2_PROTOCOL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(v2["protocol_fingerprint"], EXPECTED_V2_FINGERPRINT)
        method = replication["method_identity"]
        self.assertEqual(method["change_from_authoritative_v2"], "cohort_identity_rule_only")
        self.assertEqual(method["framing_historical_year_range"], v2["framing"]["historical_year_range"])
        self.assertEqual(method["heldout_year_range"], v2["framing"]["heldout_year_range"])
        self.assertEqual(method["historical_country_min_count"], v2["framing"]["historical_country_min_count"])
        self.assertEqual(method["country_selection_seed"], v2["framing"]["country_selection_seed"])
        self.assertEqual(method["country_geometry_provider_freeze_fingerprint"], v2["provider"]["freeze_fingerprint"])
        self.assertEqual(method["regional_lattice_freeze_fingerprint"], v2["provider"]["regional_lattice_freeze_fingerprint"])
        self.assertEqual(method["lattice_step_deg"], v2["provider"]["lattice_step_deg"])
        self.assertEqual(method["points_per_tile"], v2["provider"]["points_per_tile"])
        self.assertEqual(method["support_fraction"], v2["robust_core"]["support_fraction"])
        self.assertEqual(method["support_world_dtype"], v2["robust_core"]["support_world_dtype"])
        self.assertEqual(method["patch_merge_distance_m"], v2["robust_core"]["patch_merge_distance_m"])
        self.assertEqual(method["terrain_features"], v2["robust_core"]["terrain_features"])
        self.assertEqual(method["prototype_scope"], v2["robust_core"]["prototype_scope"])
        self.assertEqual(method["primary_recovery_radius_km"], v2["evaluation"]["primary_recovery_radius_km"])
        self.assertEqual(method["random_baseline_repetitions"], v2["evaluation"]["random_baseline_repetitions"])
        self.assertEqual(method["random_seed"], v2["evaluation"]["random_seed"])
        self.assertEqual(replication["replication_gate"], v2["development_gate"])

    def test_four_v4_integration_subsets_are_disjoint_and_exhaustive(self):
        frame = pd.read_csv(SOURCE_PATH)
        cohorts = {
            "v1": cohort_for_offset(frame, -1),
            "v1_1": cohort_for_offset(frame, 0),
            "v2": cohort_for_offset(frame, 1),
            "replication": cohort_for_offset(frame, 2),
        }
        keys = {name: set(part["speciesKey"].astype(int)) for name, part in cohorts.items()}
        for name, part in cohorts.items():
            self.assertEqual(len(part), 24, name)
            self.assertEqual(part["speciesKey"].nunique(), 24, name)
            self.assertEqual(part["taxon_group"].value_counts().to_dict(), {"plant": 12, "animal": 12}, name)
            self.assertEqual(
                part["record_count_stratum"].astype(int).value_counts().sort_index().to_dict(),
                {0: 6, 1: 6, 2: 6, 3: 6},
                name,
            )
        names = list(keys)
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                self.assertFalse(keys[left] & keys[right], f"{left} overlaps {right}")
        union = set().union(*keys.values())
        self.assertEqual(len(union), 96)
        self.assertEqual(union, set(frame["speciesKey"].astype(int)))


if __name__ == "__main__":
    unittest.main()
