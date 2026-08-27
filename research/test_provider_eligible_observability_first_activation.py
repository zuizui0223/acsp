from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

import predeclare_provider_eligible_observability_confirmation as prereg
import run_provider_eligible_observability_first_activation as run


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/provider-eligible-observability-first-activation.yml"
MARKER = ROOT / "validation/activate_provider_eligible_observability_first_v1.marker"


class ProviderEligibleFirstActivationTests(unittest.TestCase):
    def test_workflow_is_dormant_marker_only_and_run_one_guarded(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Provider-eligible observability first activation", text)
        self.assertIn("branches: [main]", text)
        self.assertIn(
            "- validation/activate_provider_eligible_observability_first_v1.marker",
            text,
        )
        self.assertNotIn("\n  pull_request:", text)
        self.assertNotIn("\n  schedule:", text)
        self.assertNotIn("\n  workflow_dispatch:", text)
        self.assertIn('os.environ["RUN_NUMBER"] == "1"', text)
        self.assertIn(
            "preregistration_merge_commit=91ff432e3da7cf3b26efa16a5c60219715feff89",
            text,
        )
        self.assertFalse(MARKER.exists(), "implementation PR must not contain activation marker")

    def test_runner_is_bound_to_authoritative_preregistration(self) -> None:
        self.assertEqual(
            run.EXPECTED_PREREG_MERGE_COMMIT,
            "91ff432e3da7cf3b26efa16a5c60219715feff89",
        )
        observed = prereg.validate_static_preregistration()
        self.assertEqual(
            observed["protocol_fingerprint"],
            "4afd35c96178934f33f1e1336871df59972ffc6f487c6f11b9abedd690ea442d",
        )
        self.assertEqual(
            observed["execution_contract_fingerprint"],
            "f17ccb3308baad021ce95ccf24bfe3ded782f4286469d82bfd1c3fc9f9f867ac",
        )

    def test_stage1_qcut_is_after_exclusion_filter_and_has_every_stratum(self) -> None:
        synthetic = pd.DataFrame(
            {
                "speciesKey": [900000001 + i for i in range(12)],
                "scientific_name": [f"Synthetic unused species {i}" for i in range(12)],
                "coordinate_records": [20 + i * 5 for i in range(12)],
            }
        )

        def provider(bounds, kingdom_key, facet_limit, minimum_records):
            self.assertEqual(facet_limit, 400)
            self.assertEqual(minimum_records, 20)
            return synthetic.copy()

        snapshot = run.build_candidate_snapshot(frame_provider=provider)
        self.assertEqual(len(snapshot), 12 * 2 * 12)
        for region in range(1, 13):
            for group in ("plant", "animal"):
                cell = snapshot[
                    snapshot["region_cell_index"].eq(region)
                    & snapshot["taxon_group"].eq(group)
                ]
                self.assertEqual(set(cell["record_count_stratum"].astype(int)), {0, 1, 2, 3})

    def test_stage2_pure_audit_distinguishes_supported_unsupported_no_country_and_error(self) -> None:
        candidates = pd.DataFrame(
            [
                {
                    "region_cell_index": 1,
                    "geographic_stratum": "g",
                    "region_name": "r",
                    "west": 0.0,
                    "south": 0.0,
                    "east": 1.0,
                    "north": 1.0,
                    "taxon_group": "plant",
                    "record_count_stratum": 0,
                    "speciesKey": key,
                    "scientific_name": name,
                    "coordinate_records": 100,
                }
                for key, name in (
                    (1, "Supported"),
                    (2, "Unsupported"),
                    (3, "No country"),
                    (4, "Provider error"),
                )
            ]
        )
        historical = {
            1: {"speciesKey": 1, "counts": {"JP": 10}, "error": ""},
            2: {"speciesKey": 2, "counts": {"HK": 10}, "error": ""},
            3: {"speciesKey": 3, "counts": {"JP": 4}, "error": ""},
            4: {"speciesKey": 4, "counts": {}, "error": "SyntheticError: stop"},
        }
        audit = run.build_eligibility_snapshot(candidates, historical).set_index("speciesKey")
        self.assertEqual(audit.loc[1, "eligibility_status"], "provider_eligible_before_final_selection")
        self.assertTrue(bool(audit.loc[1, "provider_eligible"]))
        self.assertEqual(audit.loc[1, "selected_country_code"], "JP")
        self.assertEqual(audit.loc[2, "eligibility_status"], "preselection_ineligible_provider_coverage")
        self.assertFalse(bool(audit.loc[2, "provider_eligible"]))
        self.assertEqual(audit.loc[2, "selected_country_code"], "HK")
        self.assertEqual(audit.loc[3, "eligibility_status"], "preselection_ineligible_no_historical_country")
        self.assertEqual(audit.loc[4, "eligibility_status"], "historical_provider_error_abort")

    def test_stage3_selects_exact_hash_min_per_cell_offline_without_score_ranking(self) -> None:
        rows = []
        expected = {}
        cfg = prereg.protocol()
        seed = int(cfg["cohort"]["selection_seed"])
        key = 100000
        for region in range(1, 13):
            for group in ("plant", "animal"):
                for stratum in range(4):
                    candidates = []
                    for count in (5, 999999):
                        key += 1
                        row = {
                            "region_cell_index": region,
                            "geographic_stratum": "g",
                            "region_name": f"r{region}",
                            "west": 0.0,
                            "south": 0.0,
                            "east": 1.0,
                            "north": 1.0,
                            "taxon_group": group,
                            "record_count_stratum": stratum,
                            "speciesKey": key,
                            "scientific_name": f"Synthetic {key}",
                            "coordinate_records": 100,
                            "selected_country_code": "JP",
                            "selected_country_alpha3": "JPN",
                            "country_selection_basis": "synthetic",
                            "historical_selected_country_count": count,
                            "country_frame_observability_score": prereg.observability_score(count),
                            "provider_eligible": True,
                            "eligibility_status": "provider_eligible_before_final_selection",
                            "historical_country_counts_json": '{"JP":10}',
                            "failure_reason": "",
                        }
                        candidates.append(row)
                        rows.append(row)
                    expected[(region, group, stratum)] = min(
                        candidates,
                        key=lambda row: (
                            prereg.identity_hash(
                                seed,
                                region,
                                group,
                                stratum,
                                int(row["speciesKey"]),
                            ),
                            int(row["speciesKey"]),
                            str(row["scientific_name"]),
                        ),
                    )["speciesKey"]

        chosen = run.select_final_96(pd.DataFrame(rows))
        self.assertEqual(len(chosen), 96)
        self.assertEqual(chosen["speciesKey"].nunique(), 96)
        for row in chosen.itertuples(index=False):
            self.assertEqual(
                int(row.speciesKey),
                int(expected[(int(row.region_cell_index), str(row.taxon_group), int(row.record_count_stratum))]),
            )

    def test_stage3_collision_aborts_instead_of_replacing(self) -> None:
        rows = []
        for region in range(1, 13):
            for group in ("plant", "animal"):
                for stratum in range(4):
                    key = region * 10000 + (0 if group == "plant" else 5000) + stratum
                    if region == 1 and group == "plant" and stratum in (0, 1):
                        key = 777777
                    rows.append(
                        {
                            "region_cell_index": region,
                            "taxon_group": group,
                            "record_count_stratum": stratum,
                            "speciesKey": key,
                            "scientific_name": f"Synthetic {key}",
                            "provider_eligible": True,
                            "eligibility_status": "provider_eligible_before_final_selection",
                            "historical_selected_country_count": 10,
                            "country_frame_observability_score": prereg.observability_score(10),
                        }
                    )
        with self.assertRaises(run.FirstActivationAborted):
            run.select_final_96(pd.DataFrame(rows))

    def test_geometry_attachment_never_changes_selected_country_or_identity(self) -> None:
        selection = pd.DataFrame(
            [
                {
                    "speciesKey": 123,
                    "scientific_name": "Synthetic",
                    "selected_country_code": "JP",
                    "selected_country_alpha3": "JPN",
                }
            ]
        )
        result = run.attach_geometry(
            selection,
            {
                "JP": {
                    "country_code": "JP",
                    "alpha3": "JPN",
                    "source_id": "geoBoundaries-gbOpen-ADM0-simplified",
                    "source_version": "v6.0.0@x",
                    "canonical_sha256": "a" * 64,
                    "error": "",
                }
            },
        )
        self.assertEqual(int(result.iloc[0]["speciesKey"]), 123)
        self.assertEqual(result.iloc[0]["selected_country_code"], "JP")
        self.assertEqual(result.iloc[0]["selected_country_alpha3"], "JPN")
        self.assertEqual(result.iloc[0]["geometry_canonical_sha256"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
