#!/usr/bin/env python3
"""Diagnose HTTP object availability for the four frozen WorldCover COG failures.

The diagnostic is deliberately transport-only. It sends a one-byte range GET to
exactly the four official ESA WorldCover 2021 v200 URLs frozen after the
point-bearing-COG repair. It never downloads a full COG, reads a class value,
changes candidate membership, or opens any biological/field outcome.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from acsp.discovery.providers.worldcover import worldcover_2021_map_url

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_worldcover_required_cog_http_diagnostic_v1.json"
REPAIR_RESULT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_worldcover_pointcog_repair_result_v1.json"
EXPECTED_COGS = ("N24E141", "N24E153", "N27E138", "N27E141")
USER_AGENT = "ACSP-fresh-SENTINEL-v2-WorldCover-source-diagnostic/1.0"


def _load_contracts() -> tuple[dict[str, Any], dict[str, Any]]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    repair = json.loads(REPAIR_RESULT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_REQUIRED_COG_HTTP_DIAGNOSTIC":
        raise ValueError("required-COG diagnostic contract is not frozen")
    if repair.get("status") != "POINT_BEARING_COG_REPAIR_COVERAGE_AUDIT_FROZEN":
        raise ValueError("point-bearing COG repair result is not frozen")
    declared = tuple(contract.get("required_cog_ids") or ())
    if declared != EXPECTED_COGS:
        raise ValueError("required WorldCover COG diagnostic set drifted")
    failures = tuple(sorted((repair.get("remaining_required_worldcover_cog_failures") or {}).keys()))
    if failures != tuple(sorted(EXPECTED_COGS)):
        raise ValueError("repair result and diagnostic COG set disagree")
    provider = contract.get("provider") or {}
    if provider.get("identity") != "ESA_WORLDCOVER" or provider.get("release") != "2021_v200":
        raise ValueError("WorldCover provider identity/release drifted")
    if provider.get("alternate_provider_allowed") is not False:
        raise ValueError("alternate provider must remain forbidden")
    return contract, repair


def _classify_http_status(status: int) -> str:
    code = int(status)
    if code in {200, 206}:
        return "OBJECT_ACCESSIBLE"
    if code == 404:
        return "OBJECT_NOT_PUBLISHED_AT_FROZEN_URL"
    if code == 403:
        return "OBJECT_ACCESS_DENIED_OR_UNAVAILABLE"
    if code == 429 or 500 <= code <= 599:
        return "TRANSIENT_PROVIDER_FAILURE"
    if 400 <= code <= 499:
        return "OTHER_PROVIDER_HTTP_ERROR"
    return "OTHER_PROVIDER_HTTP_ERROR"


def probe_http_range(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    max_attempts: int = 3,
    sleep_func: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Return a source-availability classification without downloading the object."""
    attempts = int(max_attempts)
    if attempts < 1:
        raise ValueError("max_attempts must be >=1")
    last_error_class = ""
    last_error_message = ""
    last_status: int | None = None

    for attempt in range(attempts):
        request = urllib.request.Request(
            str(url),
            headers={
                "User-Agent": USER_AGENT,
                "Range": "bytes=0-0",
                "Accept": "*/*",
            },
            method="GET",
        )
        retry = False
        try:
            with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
                status = int(getattr(response, "status", response.getcode()))
                last_status = status
                classification = _classify_http_status(status)
                if classification == "TRANSIENT_PROVIDER_FAILURE" and attempt + 1 < attempts:
                    retry = True
                else:
                    return {
                        "http_status": status,
                        "classification": classification,
                        "attempts": attempt + 1,
                        "error_class": "",
                        "error_message": "",
                    }
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            last_status = status
            classification = _classify_http_status(status)
            last_error_class = type(exc).__name__
            last_error_message = str(exc)
            if classification == "TRANSIENT_PROVIDER_FAILURE" and attempt + 1 < attempts:
                retry = True
            else:
                return {
                    "http_status": status,
                    "classification": classification,
                    "attempts": attempt + 1,
                    "error_class": last_error_class,
                    "error_message": last_error_message,
                }
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error_class = type(exc).__name__
            last_error_message = str(exc)
            if attempt + 1 < attempts:
                retry = True
            else:
                return {
                    "http_status": None,
                    "classification": "TRANSIENT_PROVIDER_FAILURE",
                    "attempts": attempt + 1,
                    "error_class": last_error_class,
                    "error_message": last_error_message,
                }

        if retry:
            sleep_func(float(2**attempt))

    return {
        "http_status": last_status,
        "classification": "TRANSIENT_PROVIDER_FAILURE",
        "attempts": attempts,
        "error_class": last_error_class,
        "error_message": last_error_message,
    }


def diagnose_required_cogs(
    *,
    probe: Callable[..., dict[str, Any]] = probe_http_range,
) -> dict[str, Any]:
    contract, _ = _load_contracts()
    request_cfg = contract["diagnostic_request"]
    rows: list[dict[str, Any]] = []
    for cog_id in EXPECTED_COGS:
        url = worldcover_2021_map_url(cog_id)
        result = probe(
            url,
            timeout_seconds=float(request_cfg["timeout_seconds"]),
            max_attempts=int(request_cfg["max_attempts"]),
        )
        rows.append({
            "worldcover_cog_id": cog_id,
            "url": url,
            "http_status": result.get("http_status"),
            "classification": str(result.get("classification") or ""),
            "attempts": int(result.get("attempts") or 0),
            "error_class": str(result.get("error_class") or ""),
            "error_message": str(result.get("error_message") or "")[:500],
        })

    counts: dict[str, int] = {}
    for row in rows:
        key = row["classification"]
        counts[key] = counts.get(key, 0) + 1

    if counts.get("TRANSIENT_PROVIDER_FAILURE", 0):
        next_gate = "Do not change ecological rules; repeat only the same frozen source diagnostic after provider transport stabilizes."
    elif counts.get("OBJECT_ACCESSIBLE", 0) == len(EXPECTED_COGS):
        next_gate = "Freeze the source diagnostic; then diagnose rasterio remote-COG transport without changing provider/release or candidate semantics."
    elif counts.get("OBJECT_NOT_PUBLISHED_AT_FROZEN_URL", 0):
        next_gate = "Freeze the source diagnostic; treat unpublished frozen-provider objects as source-indeterminate and define conservative missing-source handling before ecological screening."
    else:
        next_gate = "Freeze the source diagnostic before any further source-mechanics decision."

    return {
        "schema_version": "cirsium-fresh-sentinel-v2-worldcover-required-cog-http-diagnostic-result-v1",
        "status": "REQUIRED_COG_HTTP_DIAGNOSTIC_COMPLETE",
        "provider_identity": "ESA_WORLDCOVER",
        "provider_release": "2021_v200",
        "required_cog_ids": list(EXPECTED_COGS),
        "diagnostic_request_method": "GET_RANGE_BYTES_0_0",
        "results": rows,
        "classification_counts": dict(sorted(counts.items())),
        "full_cog_downloaded": False,
        "worldcover_class_read": False,
        "candidate_membership_changed": False,
        "candidate_order_changed": False,
        "candidate_coordinates_changed": False,
        "alternate_provider_used": False,
        "alternate_release_used": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "private_exact_site_geometry_used": False,
        "p02_result_used": False,
        "human_access_used": False,
        "object_not_published_is_biological_negative": False,
        "transient_provider_failure_is_biological_negative": False,
        "diagnostic_can_authorize_ecological_screening": False,
        "next_gate": next_gate,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose_required_cogs()
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
