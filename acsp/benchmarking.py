"""Shared, current benchmark helpers.

Kept in the package so the national hierarchical benchmark does not depend on
historical, region-specific research runners stored under ``legacy/``.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests


_TRANSIENT_HTTP_STATUS = {429, 500, 502, 503, 504}


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = 60,
    attempts: int = 8,
) -> dict[str, Any]:
    """Fetch JSON with bounded retries for transient network/GBIF failures.

    Retry only conditions that can plausibly recover without changing the
    scientific request: rate limiting, 5xx responses, timeouts, connection
    failures, and a transient malformed/empty JSON response. Permanent 4xx
    errors are raised immediately so protocol mistakes are not hidden.
    """
    last_error: Exception | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(total_attempts):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            if response.status_code in _TRANSIENT_HTTP_STATUS:
                response.raise_for_status()
            elif response.status_code >= 400:
                response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status not in _TRANSIENT_HTTP_STATUS:
                raise
            last_error = exc
        except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
            last_error = exc
        except requests.RequestException:
            # Non-transient request failures should not be masked by retries.
            raise
        if attempt + 1 < total_attempts:
            time.sleep(min(30.0, 1.0 * (2 ** attempt)))
    assert last_error is not None
    raise last_error


def coverage_at_radius(candidates: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    """Recompute held-out identifiers covered at the requested radius."""
    out = candidates.copy()
    all_ids = out["all_heldout_ids"].astype(str).str.split(";")
    distances = out["heldout_distances_km"].astype(str).str.split(";")
    out["covered_heldout_ids"] = [
        ";".join(
            identifier
            for identifier, distance in zip(ids, values)
            if identifier and float(distance) <= float(radius_km)
        )
        for ids, values in zip(all_ids, distances)
    ]
    return out


def fold_completion(folds: pd.DataFrame, expected_repeats: int) -> dict[str, Any]:
    """Return a failure-inclusive fold completion audit."""
    valid = int(folds.get("status", pd.Series(dtype=str)).eq("ok").sum())
    if valid == int(expected_repeats):
        status = "ok"
    elif valid > 0:
        status = "partial"
    else:
        status = "failed"
    return {
        "status": status,
        "valid_repeats": valid,
        "attempted_repeats": int(len(folds)),
        "failed_repeats": max(0, int(expected_repeats) - valid),
    }
