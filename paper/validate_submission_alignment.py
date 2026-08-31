#!/usr/bin/env python3
"""Verify that the submission-facing paper matches the authoritative ACSP product.

This validator is intentionally network-free. It binds the new robust-patch
manuscript and tables to the frozen implementation constants and committed
transfer/observability records while preserving the historical Top-5 paper as
separate provenance.
"""
from __future__ import annotations

import ast
import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
GENERATED = PAPER / "generated"
VALIDATED_SOURCE = ROOT / "acsp" / "validated_robust.py"
RESERVED_TRANSFER = (
    ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2_replication_result_v1.json"
)
FRESH_TRANSFER = (
    ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_result_v1.json"
)
OBSERVABILITY_TERMINAL = (
    ROOT / "validation" / "acsp_provider_eligible_observability_first_activation_terminal_v1.json"
)
TABLE_1 = GENERATED / "table_1_robust_patch_confirmation.csv"
TABLE_2 = GENERATED / "table_2_robust_patch_transfer_boundary.csv"
MANUSCRIPT = PAPER / "MANUSCRIPT_ROBUST_PATCH_DRAFT.md"
PAPER_README = PAPER / "README.md"
HISTORICAL_MANUSCRIPT = PAPER / "MANUSCRIPT_DRAFT.md"
HISTORICAL_TABLE = GENERATED / "table_1_retrospective_validation.csv"


def _load_literal_constants(path: Path) -> dict[str, object]:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, object] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            values[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return values


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _as_int(row: dict[str, str], key: str) -> int:
    value = row.get(key, "")
    _require(value not in (None, ""), f"{key} is blank")
    return int(value)


def _as_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    _require(value not in (None, ""), f"{key} is blank")
    return float(value)


def _same_float(actual: float, expected: float, *, name: str) -> None:
    _require(
        math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12),
        f"{name} drifted: {actual!r} != {expected!r}",
    )


def _validate_primary_table(constants: dict[str, object]) -> None:
    rows = _read_csv(TABLE_1)
    _require(len(rows) == 1, "Primary robust-patch table must contain exactly one row")
    row = rows[0]
    _require(row["analysis_scope"] == "validated_japan_12_region_frame", "Primary scope changed")
    _require(row["product"] == "non-ranked robust candidate patches", "Validated product changed")
    _require(row["comparator"] == "same-size random candidate-patch sets", "Comparator changed")
    _require(row["confirmation_status"] == constants["VALIDATED_ROBUST_STATUS"], "Status changed")
    _require(
        _as_int(row, "declared_taxon_region_pairs") == constants["VALIDATED_ROBUST_CONFIRMATION_PAIRS"],
        "Confirmation pair count changed",
    )
    _require(
        _as_int(row, "declared_folds") == constants["VALIDATED_ROBUST_CONFIRMATION_FOLDS"],
        "Confirmation fold count changed",
    )
    _same_float(
        _as_float(row, "primary_endpoint_km"),
        float(constants["VALIDATED_ROBUST_PRIMARY_RADIUS_KM"]),
        name="primary endpoint",
    )
    _same_float(
        _as_float(row, "mean_lift_over_comparator"),
        float(constants["VALIDATED_ROBUST_MEAN_LIFT_OVER_RANDOM"]),
        name="mean lift",
    )
    ci = constants["VALIDATED_ROBUST_BOOTSTRAP_CI"]
    _same_float(_as_float(row, "bootstrap_ci95_lower"), float(ci[0]), name="CI lower")
    _same_float(_as_float(row, "bootstrap_ci95_upper"), float(ci[1]), name="CI upper")
    _same_float(
        _as_float(row, "sign_flip_p"),
        float(constants["VALIDATED_ROBUST_SIGN_FLIP_P"]),
        name="sign-flip p",
    )
    _same_float(
        _as_float(row, "plant_mean_lift"),
        float(constants["VALIDATED_ROBUST_PLANT_MEAN_LIFT"]),
        name="plant mean lift",
    )
    _same_float(
        _as_float(row, "animal_mean_lift"),
        float(constants["VALIDATED_ROBUST_ANIMAL_MEAN_LIFT"]),
        name="animal mean lift",
    )


def _validate_transfer_table(constants: dict[str, object]) -> None:
    table_rows = _read_csv(TABLE_2)
    _require(len(table_rows) == 4, "Transfer table must contain exactly four declared experiments")
    rows = {row["experiment_id"]: row for row in table_rows}
    expected_ids = {
        "japan_robust_confirmation",
        "country_framed_reserved_replication",
        "country_framed_fresh_confirmation",
        "provider_eligible_observability_first_activation",
    }
    _require(set(rows) == expected_ids, "Transfer table experiment set changed")

    japan = rows["japan_robust_confirmation"]
    _require(_as_int(japan, "declared_units") == constants["VALIDATED_ROBUST_CONFIRMATION_PAIRS"], "Japan units changed")
    _same_float(
        _as_float(japan, "mean_robust_minus_random_recall"),
        float(constants["VALIDATED_ROBUST_MEAN_LIFT_OVER_RANDOM"]),
        name="Japan transfer-table lift",
    )
    _require(japan["promotion_status"] == "validated_product", "Japan promotion status changed")

    reserved_record = json.loads(RESERVED_TRANSFER.read_text(encoding="utf-8"))
    reserved = rows["country_framed_reserved_replication"]
    reserved_results = reserved_record["results"]
    _require(_as_int(reserved, "declared_units") == int(reserved_results["declared_taxa"]), "Reserved declared taxa changed")
    _require(
        _as_int(reserved, "candidate_generation_success")
        == int(reserved_results["candidate_generation_success_taxa"]),
        "Reserved candidate-generation count changed",
    )
    _require(
        _as_int(reserved, "temporally_evaluable") == int(reserved_results["temporally_evaluable_taxa"]),
        "Reserved temporal count changed",
    )
    _require(
        _as_int(reserved, "integrated_evaluable") == int(reserved_results["integrated_evaluable_taxa"]),
        "Reserved integrated count changed",
    )
    _same_float(
        _as_float(reserved, "mean_robust_minus_random_recall"),
        float(reserved_results["mean_robust_minus_random_recall"]),
        name="Reserved mean lift",
    )
    _same_float(
        _as_float(reserved, "ci95_lower"),
        float(reserved_results["taxon_bootstrap_95pct_ci"][0]),
        name="Reserved CI lower",
    )
    _same_float(
        _as_float(reserved, "ci95_upper"),
        float(reserved_results["taxon_bootstrap_95pct_ci"][1]),
        name="Reserved CI upper",
    )
    _require(reserved["terminal_status"] == reserved_record["status"], "Reserved terminal status changed")
    _require(reserved_record["replication_gate_passed"] is False, "Reserved result was reclassified")
    _require(reserved["promotion_status"] == "not_promoted", "Reserved extension was promoted")

    fresh_record = json.loads(FRESH_TRANSFER.read_text(encoding="utf-8"))
    fresh = rows["country_framed_fresh_confirmation"]
    _require(_as_int(fresh, "declared_units") == int(fresh_record["declared_taxa"]), "Fresh declared taxa changed")
    _require(
        _as_int(fresh, "candidate_generation_success")
        == int(fresh_record["candidate_generation_success_taxa"]),
        "Fresh candidate-generation count changed",
    )
    _require(
        _as_int(fresh, "temporally_evaluable") == int(fresh_record["temporally_evaluable_taxa"]),
        "Fresh temporal count changed",
    )
    _require(
        _as_int(fresh, "integrated_evaluable") == int(fresh_record["integrated_evaluable_taxa"]),
        "Fresh integrated count changed",
    )
    _same_float(
        _as_float(fresh, "mean_robust_minus_random_recall"),
        float(fresh_record["mean_robust_minus_random_recall"]),
        name="Fresh mean lift",
    )
    _same_float(
        _as_float(fresh, "ci95_lower"),
        float(fresh_record["taxon_bootstrap_95pct_ci"][0]),
        name="Fresh CI lower",
    )
    _same_float(
        _as_float(fresh, "ci95_upper"),
        float(fresh_record["taxon_bootstrap_95pct_ci"][1]),
        name="Fresh CI upper",
    )
    _require(fresh_record["fresh_confirmation_gate_passed"] is False, "Fresh result was reclassified")
    _require(fresh["promotion_status"] == "not_promoted", "Fresh extension was promoted")

    terminal_record = json.loads(OBSERVABILITY_TERMINAL.read_text(encoding="utf-8"))
    provider = rows["provider_eligible_observability_first_activation"]
    observed = terminal_record["observed_execution"]
    statuses = terminal_record["two_axis_description"]
    _require(_as_int(provider, "provider_candidate_rows") == int(observed["candidate_rows"]), "Provider candidate rows changed")
    _require(
        _as_int(provider, "provider_historical_queries") == int(observed["historical_unique_species_queries"]),
        "Provider query count changed",
    )
    _require(_as_int(provider, "provider_errors") == int(observed["historical_provider_error_count"]), "Provider error count changed")
    _require(provider["terminal_status"] == terminal_record["original_terminal_status"]["status"], "Provider status changed")
    _require(statuses["supply_status"] == "protocol_abort", "Provider abort was reclassified")
    _require(statuses["hypothesis_status"] == "unavailable", "Unavailable hypothesis was reclassified")
    _require(statuses["promotion_status"] == "not_promoted", "Provider experiment was promoted")
    _require(observed["heldout_2021_2025_opened"] is False, "Provider heldout was opened")
    _require(provider["promotion_status"] == statuses["promotion_status"], "Provider table promotion status changed")
    _require(provider["heldout_status"] == "2021-2025 heldout unopened", "Provider table heldout status changed")
    _require(
        provider["interpretation"]
        == "HTTP 429 provider failures stopped the one-shot freeze; the observability hypothesis remained unavailable rather than negative.",
        "Provider table interpretation changed",
    )


def _validate_text_boundaries() -> None:
    manuscript = MANUSCRIPT.read_text(encoding="utf-8")
    readme = PAPER_README.read_text(encoding="utf-8")
    allowed_negated_boundaries = (
        (
            "The supported conclusion is therefore neither “ACSP works only in Japan” nor “ACSP is globally "
            "validated.”"
        ),
        (
            "Conversely, this study does not establish that ACSP is superior to SDM, GRTS, biosurvey, or all "
            "survey-design methods."
        ),
    )
    required_manuscript_tokens = (
        "non-ranked set of bounded robust candidate patches",
        "96 taxon–region pairs",
        "480 declared folds",
        "0.08559",
        "[0.05119, 0.12165]",
        "3.33 × 10⁻⁵",
        "34/48",
        "29 of 3,161",
        "not globally validated",
        "not occupancy probability",
        "*Campanula microdonta* is used only as transparent method-development provenance",
        "hypothesis status was unavailable rather than negative",
    )
    for token in required_manuscript_tokens:
        _require(token in manuscript, f"Submission manuscript lost required boundary: {token}")

    claim_text = manuscript
    for boundary in allowed_negated_boundaries:
        _require(boundary in manuscript, f"Submission manuscript lost required negated boundary: {boundary}")
        claim_text = claim_text.replace(boundary, "")

    forbidden_sentences = (
        "ACSP is globally validated",
        "ACSP is superior to SDM",
        "candidate patches are occupancy probabilities",
        "Campanula microdonta is an independent confirmation",
    )
    for sentence in forbidden_sentences:
        _require(sentence not in claim_text, f"Submission manuscript contains forbidden claim: {sentence}")

    required_readme_tokens = (
        "Current submission-facing robust candidate-patch package",
        "MANUSCRIPT_ROBUST_PATCH_DRAFT.md",
        "Historical finite Top-5 package",
        "preserved provenance",
    )
    for token in required_readme_tokens:
        _require(token in readme, f"Paper README lost package separation: {token}")

    _require(HISTORICAL_MANUSCRIPT.exists(), "Historical Top-5 manuscript was removed")
    _require(HISTORICAL_TABLE.exists(), "Historical Top-5 confirmation table was removed")


def run() -> dict[str, object]:
    constants = _load_literal_constants(VALIDATED_SOURCE)
    required_constants = {
        "VALIDATED_ROBUST_SUPPORT_FRACTION",
        "VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M",
        "VALIDATED_ROBUST_PRIMARY_RADIUS_KM",
        "VALIDATED_ROBUST_CONFIRMATION_PAIRS",
        "VALIDATED_ROBUST_CONFIRMATION_FOLDS",
        "VALIDATED_ROBUST_MEAN_LIFT_OVER_RANDOM",
        "VALIDATED_ROBUST_BOOTSTRAP_CI",
        "VALIDATED_ROBUST_SIGN_FLIP_P",
        "VALIDATED_ROBUST_ANIMAL_MEAN_LIFT",
        "VALIDATED_ROBUST_PLANT_MEAN_LIFT",
        "VALIDATED_ROBUST_STATUS",
    }
    missing = required_constants - set(constants)
    _require(not missing, f"Authoritative validated constants missing: {sorted(missing)}")
    _same_float(
        float(constants["VALIDATED_ROBUST_SUPPORT_FRACTION"]),
        0.025,
        name="validated support fraction",
    )
    _same_float(
        float(constants["VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M"]),
        1000.0,
        name="validated patch merge distance",
    )
    _validate_primary_table(constants)
    _validate_transfer_table(constants)
    _validate_text_boundaries()
    return {
        "status": "submission_alignment_passed",
        "authoritative_product": "non-ranked robust candidate patches",
        "validated_scope": "fixed Japanese 12-region frame",
        "confirmation_pairs": constants["VALIDATED_ROBUST_CONFIRMATION_PAIRS"],
        "confirmation_folds": constants["VALIDATED_ROBUST_CONFIRMATION_FOLDS"],
        "historical_top5_package_preserved": True,
        "global_product_promoted": False,
    }


def main() -> int:
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
