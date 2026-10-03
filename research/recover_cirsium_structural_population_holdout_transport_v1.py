#!/usr/bin/env python3
"""Re-run the frozen structural population holdout with transport-only GBIF retry.

The parent scientific contract is unchanged. This wrapper retries only identical
GBIF requests that fail with HTTP 429/5xx. It does not change taxa, regions,
precision, population clustering, structural sources, selector formulas,
comparators, prefixes, or recovery radii.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

import requests

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import run_cirsium_structural_population_holdout_development_v1 as base

AMENDMENT_PATH = ROOT / "validation" / "cirsium_structural_population_holdout_transport_recovery_amendment_v1.json"
ORIGINAL_FETCH = base.fetch_gbif_species
ATTEMPT_LOG: dict[str, dict[str, Any]] = {}


def _load_amendment() -> dict[str, Any]:
    payload = json.loads(AMENDMENT_PATH.read_text(encoding="utf-8"))
    if payload.get("status") != "FROZEN_TRANSPORT_ONLY_RECOVERY_AFTER_PROVIDER_503":
        raise ValueError("transport recovery amendment is not frozen")
    expected = str(payload["scientific_contract"]["git_blob_sha1"])
    observed = base.git_blob_sha1(base.CONTRACT_PATH)
    if observed != expected:
        raise RuntimeError(f"SCIENTIFIC_CONTRACT_GIT_BLOB_DRIFT:{observed}")
    if payload.get("scientific_semantics_changed") is not False:
        raise ValueError("transport amendment cannot change scientific semantics")
    if payload.get("provider_substitution") is not False or payload.get("provider_relaxation") is not False:
        raise ValueError("transport amendment cannot relax or substitute provider semantics")
    return payload


def _status_code(exc: requests.HTTPError) -> int | None:
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def fetch_gbif_species_with_transport_retry(
    species_name: str,
    *args: Any,
    fetcher: Callable[..., tuple[Any, dict[str, Any]]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    amendment: dict[str, Any] | None = None,
    **kwargs: Any,
):
    """Retry only identical HTTP 429/5xx GBIF requests under the frozen amendment."""
    cfg = (amendment or _load_amendment())["transport_retry"]
    allowed = {int(value) for value in cfg["retryable_http_statuses"]}
    maximum_total_attempts = int(cfg["maximum_total_attempts"])
    delays = [float(value) for value in cfg["sleep_before_retry_seconds"]]
    if maximum_total_attempts < 1 or len(delays) != maximum_total_attempts - 1:
        raise ValueError("transport retry schedule is inconsistent")
    call = fetcher or ORIGINAL_FETCH

    attempts = 0
    retry_statuses: list[int] = []
    while attempts < maximum_total_attempts:
        attempts += 1
        try:
            frame, audit = call(species_name, *args, **kwargs)
            audit = dict(audit)
            audit["transport_attempts"] = int(attempts)
            audit["transport_retry_used"] = bool(attempts > 1)
            audit["transport_retry_http_statuses"] = list(retry_statuses)
            ATTEMPT_LOG[str(species_name)] = {
                "attempts": int(attempts),
                "retry_http_statuses": list(retry_statuses),
                "final_status": "SUCCESS",
            }
            return frame, audit
        except requests.HTTPError as exc:
            status = _status_code(exc)
            if status not in allowed or attempts >= maximum_total_attempts:
                ATTEMPT_LOG[str(species_name)] = {
                    "attempts": int(attempts),
                    "retry_http_statuses": list(retry_statuses),
                    "final_status": "HTTP_ERROR",
                    "final_http_status": status,
                }
                raise
            retry_statuses.append(int(status))
            sleep_fn(delays[attempts - 1])

    raise AssertionError("unreachable transport retry state")


def run(out_dir: Path):
    amendment = _load_amendment()
    ATTEMPT_LOG.clear()

    def patched_fetch(species_name: str, *args: Any, **kwargs: Any):
        return fetch_gbif_species_with_transport_retry(
            species_name,
            *args,
            amendment=amendment,
            **kwargs,
        )

    previous = base.fetch_gbif_species
    base.fetch_gbif_species = patched_fetch
    try:
        curve, summary = base.run(out_dir)
    finally:
        base.fetch_gbif_species = previous

    summary = dict(summary)
    summary["transport_recovery_amendment"] = str(AMENDMENT_PATH.relative_to(ROOT))
    summary["transport_recovery_parent_run_id"] = int(amendment["parent_partial_execution"]["workflow_run_id"])
    summary["transport_recovery_parent_artifact_id"] = int(amendment["parent_partial_execution"]["artifact_id"])
    summary["transport_recovery_scientific_semantics_changed"] = False
    summary["transport_attempt_log"] = dict(sorted(ATTEMPT_LOG.items()))
    return curve, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    curve, summary = run(args.out_dir / "source-cache")
    curve.to_csv(args.out_dir / "population_holdout_curve.csv", index=False)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
