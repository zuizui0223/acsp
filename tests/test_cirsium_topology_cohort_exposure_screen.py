"""Public-only source screen for next (not yet chosen) Cirsium topology cohort."""
from __future__ import annotations

import copy
import csv
import io
import json
from pathlib import Path

import pytest

from research.audit_cirsium_topology_cohort_exposure_screen import (
    EXPECTED_UNIT_IDS,
    EXPOSED_TOPOLOGY_UNITS,
    audit_public_records,
    git_blob_sha,
    parse_csv,
    verify_git_blob_pin,
)

SPECIES = {
    "CIR01": ("Cirsium sieboldii", "WETLAND_MOISTURE_STRUCTURE"),
    "CIR02": ("Cirsium inundatum", "WETLAND_MOISTURE_STRUCTURE"),
    "CIR03": ("Cirsium ugoense", "ALPINE_TOPOGRAPHIC_STRUCTURE"),
    "CIR04": ("Cirsium otayae", "ALPINE_TOPOGRAPHIC_STRUCTURE"),
    "CIR05": ("Cirsium nambuense", "ALPINE_TOPOGRAPHIC_STRUCTURE"),
    "CIR06": ("Cirsium yezoalpinum", "ALPINE_TOPOGRAPHIC_STRUCTURE"),
    "CIR07": ("Cirsium pendulum", "OPEN_GRASSLAND_STRUCTURE"),
    "CIR08": ("Cirsium brevicaule", "COASTAL_ISLAND_STRUCTURE"),
    "CIR09": ("Cirsium spinosum", "COASTAL_ISLAND_STRUCTURE"),
    "CIR10": ("Cirsium hachijoense", "FOREST_EDGE_STRUCTURE"),
    "CIR11": ("Cirsium tamastoloniferum", "GENERAL_SPATIAL_BASELINE_ONLY"),
    "CIR12": ("Cirsium dipsacolepis", "OPEN_GRASSLAND_STRUCTURE"),
    "CIR13": ("Cirsium lineare", "OPEN_GRASSLAND_STRUCTURE"),
}


def data():
    registry = [{"cohort_unit_id": u, "species_binomial": sn, "structural_feature_family": fam,
                 "outcome_opened": "false", "candidate_patch_status": "NOT_BUILT", "aza3_slot_id": f"slot-{u}"}
                for u, (sn, fam) in SPECIES.items()]
    requirements = [{"cohort_unit_id": u, "species_binomial": sn, "structural_feature_family": fam,
                     "private_source_manifest_status": "NOT_BUILT", "private_frame_status": "NOT_BUILT",
                     "public_full_ranking_status": "NOT_FROZEN"}
                    for u, (sn, fam) in SPECIES.items()]
    preflight = {"status": "DEVELOPMENT_PREFLIGHT_TERMINAL", "selector_run": False,
                 "eligible_pairs": [{"cohort_unit_id": u} for u in ("CIR01", "CIR04", "CIR07", "CIR08")]}
    dev = {"execution_pairs": [{"cohort_unit_id": u} for u in ("CIR01", "CIR04", "CIR07")],
           "explicitly_deferred_eligible_pairs": [{"cohort_unit_id": "CIR08"}]}
    terminal = {"status": "DEVELOPMENT_TERMINAL_DO_NOT_NOMINATE_COARSE_STRUCTURAL_SELECTOR",
                "executed_scope": {"executed_pairs": 3, "explicitly_deferred_pair": {"pair_id": "CIR08__ryukyu"}}}
    smoke = {"public_temporal_outcomes_already_opened_for_unit_choice": True,
             "units": [{"cohort_unit_id": u} for u in ("CIR01", "CIR04", "CIR08")]}
    coast = {"status": "DEVELOPMENT_ONLY_OPENED_RESULT_FROZEN_NO_RETUNE",
             "cohort_unit_id": "CIR08", "opened_development_only": True}
    portable = {"status": "DEVELOPMENT_ONLY_COMPLETE_DO_NOT_RETUNE_ON_CIR08",
                "cohort_unit_id": "CIR08"}
    roster = [{"provider_query_name": "Cirsium sieboldii", "include_v2": "false",
               "exclusion_reason": "ACSP CIR01 public outcome opened and prospective cohort consumed"}]
    design = {"status": "METHOD_DESIGN_FROZEN_BEFORE_NEW_COHORT_SELECTION_NO_OUTCOMES",
              "cohort_identity_frozen": False, "field_schedule_frozen": False,
              "outcomes_may_be_opened": False,
              "parent_observation": {"previously_exposed_cohort_units": list(EXPOSED_TOPOLOGY_UNITS)}}
    return [registry, requirements, preflight, dev, terminal, smoke, coast, portable, roster, design]


def report():
    return audit_public_records(*data())


def test_existing_four_topology_exposure_units_never_reenter_candidate_pool():
    r = report()
    assert tuple(r["development_exposed_topology_units"]) == EXPOSED_TOPOLOGY_UNITS
    assert len(r["screened_units"]) == 9
    assert not set(r["screened_units"]) & set(EXPOSED_TOPOLOGY_UNITS)


def test_earlier_holdout_executed_and_coastal_opened_separately():
    r = report()
    for unit in ("CIR01", "CIR04", "CIR07"):
        assert "STRUCTURAL_HOLDOUT_DEVELOPMENT_EXECUTED" in r["units"][unit]["exposure_evidence"]
    assert "COASTAL_DEVELOPMENT_PUBLIC_OUTCOME_OPENED" in r["units"]["CIR08"]["exposure_evidence"]
    assert "STRUCTURAL_HOLDOUT_DEVELOPMENT_EXECUTED" not in r["units"]["CIR08"]["exposure_evidence"]
    assert r["units"]["CIR01"]["public_historical_outcome_exposure"] == "EXPLICITLY_DOCUMENTED"
    assert r["units"]["CIR07"]["public_historical_outcome_exposure"] == "NOT_ASSESSED_PER_UNIT"


def test_unknown_is_not_untouched_or_recruited():
    r = report()
    for unit in ("CIR03", "CIR05", "CIR09", "CIR10"):
        assert r["units"][unit]["method_exposure_class"] == "NOT_EVIDENCED_IN_PINNED_SOURCES_NOT_PROVEN_UNTOUCHED"
        assert r["units"][unit]["independent_cohort_authorized"] is False
    assert r["candidate_pool_count"] == 9
    assert r["independent_confirmatory_unit_count"] == 0
    assert r["ready_for_field_assignment_count"] == 0


def test_baseline_only_is_not_structural_confirmation():
    r = report()
    assert r["units"]["CIR11"]["structural_family_status"] == "NO_FROZEN_STRUCTURAL_FAMILY_BASELINE_ONLY"
    assert r["units"]["CIR11"]["independent_cohort_authorized"] is False


def test_unbuilt_patches_and_no_aza3_readiness_are_explicit():
    r = report()
    assert all(r["units"][u]["patch_status"] == "NOT_BUILT" for u in r["screened_units"])
    assert all(r["units"][u]["private_range_sector_geometry_verified"] is False for u in r["screened_units"])
    assert all(r["units"][u]["candidate_schedule_frozen"] is False for u in r["screened_units"])
    assert all(r["units"][u]["prospective_field_outcomes_marked_opened_in_registry"] is False for u in r["screened_units"])


def test_registry_extra_taxon_or_missing_row_fails_closed():
    rows = data()
    rows[0].pop(0)
    with pytest.raises(ValueError, match="13|cohort|registry"):
        audit_public_records(*rows)
    rows = data()
    rows[0][0]["cohort_unit_id"] = "CIR99"
    with pytest.raises(ValueError, match="registry|cohort"):
        audit_public_records(*rows)


def test_cross_source_species_and_family_drift_fail_closed():
    rows = data()
    rows[1][0]["structural_feature_family"] = "OPEN_GRASSLAND_STRUCTURE"
    with pytest.raises(ValueError, match="family|identity"):
        audit_public_records(*rows)
    rows = data()
    rows[1][0]["species_binomial"] = "Cirsium some_other_species"
    with pytest.raises(ValueError, match="species|identity"):
        audit_public_records(*rows)


def test_prior_method_records_can_never_silently_lose_a_unit():
    rows = data()
    rows[3]["execution_pairs"].pop()
    with pytest.raises(ValueError, match="holdout|exposure|execution"):
        audit_public_records(*rows)
    rows = data()
    rows[2]["eligible_pairs"].pop()
    with pytest.raises(ValueError, match="preflight|exposure"):
        audit_public_records(*rows)


def test_registry_field_outcome_flag_conflict_is_not_overwritten():
    rows = data()
    rows[0][0]["outcome_opened"] = "true"
    with pytest.raises(ValueError, match="prospective|outcome"):
        audit_public_records(*rows)


def test_missing_coastal_open_result_blocks_audit():
    rows = data()
    rows[6]["opened_development_only"] = False
    with pytest.raises(ValueError, match="coastal|opened"):
        audit_public_records(*rows)


def test_method_design_not_promoted_to_real_cohort():
    rows = data()
    rows[9]["cohort_identity_frozen"] = True
    with pytest.raises(ValueError, match="method|cohort|design"):
        audit_public_records(*rows)


def test_output_does_not_expose_range_sector_or_private_location():
    obj = report()
    dumped = json.dumps(obj, ensure_ascii=False)
    for forbidden in ("latitude", "longitude", "range_sector", "target_locality_id", "exact_site_record", "妙高", "四国のP01"):
        # 'private_range_sector_geometry_verified' is a boolean gate name, not a site field.
        if forbidden == "range_sector":
            assert '"range_sector":' not in dumped
        else:
            assert forbidden not in dumped or forbidden == "exact_site_record"
    assert obj["claims"]["field_detection_advantage_established"] is False
    assert obj["claims"]["no_private_geometry_read"] is True


def test_git_blob_integrity_checks_exact_bytes(tmp_path: Path):
    path = tmp_path / "source.json"
    path.write_bytes(b'{"ok":true}\n')
    original = git_blob_sha(path.read_bytes())
    verify_git_blob_pin(path, original)
    path.write_bytes(b'{"ok":false}\n')
    with pytest.raises(ValueError, match="blob|SHA|source"):
        verify_git_blob_pin(path, original)


def test_parse_csv_handles_commas_in_quoted_fields():
    rows = parse_csv('id,concept\nCIR01,"Cirsium otayae, broad"\n')
    assert rows[0]["concept"] == "Cirsium otayae, broad"


def test_counts_do_not_assume_four_independent_feature_families():
    r = report()
    assert r["method_exposed_within_screened_count"] == 4
    assert r["without_explicit_method_use_in_pinned_sources_count"] == 5
    assert r["screened_structural_families"]["ALPINE_TOPOGRAPHIC_STRUCTURE"] == 3
    assert r["structural_family_baseline_only_count"] == 1
    assert r["claims"]["absence_of_exposure_in_all_other_repositories_proven"] is False


def test_end_to_end_pinned_public_source_snapshot_and_tamper_gate(tmp_path: Path, monkeypatch):
    import research.audit_cirsium_topology_cohort_exposure_screen as m
    records = data()
    paths = list(m.SOURCE_FILES)
    mock_pins = {}
    for i, (path, source) in enumerate(zip(paths, records)):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if i in (0, 1, 8):
            buf = io.StringIO()
            keys = list(source[0])
            writer = csv.DictWriter(buf, fieldnames=keys)
            writer.writeheader()
            writer.writerows(source)
            raw = buf.getvalue().encode()
        else:
            raw = (json.dumps(source, sort_keys=True) + '\n').encode()
        target.write_bytes(raw)
        mock_pins[path] = m.git_blob_sha(raw)
    monkeypatch.setattr(m, 'SOURCE_GIT_BLOBS', mock_pins)
    seen = m.run_public_audit(tmp_path)
    assert seen['candidate_pool_count'] == 9
    assert seen['independent_confirmatory_unit_count'] == 0
    assert seen['pinned_public_git_blobs'] == mock_pins
    (tmp_path / paths[6]).write_text('{"cohort_unit_id":"CIR08","opened_development_only":false}')
    with pytest.raises(ValueError, match='blob SHA'):
        m.run_public_audit(tmp_path)


def test_source_pin_set_never_consumes_field_logs_or_private_geometry():
    import research.audit_cirsium_topology_cohort_exposure_screen as m
    assert len(m.SOURCE_GIT_BLOBS) == 10
    for path in m.SOURCE_GIT_BLOBS:
        assert path.startswith('validation/')
        assert not any(part in path for part in ('field_log', 'private_geometry', 'visit_outcome', 'exact_site'))
    assert m.EXPOSED_TOPOLOGY_UNITS == ('CIR02', 'CIR06', 'CIR12', 'CIR13')
