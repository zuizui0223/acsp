#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from verify_ru_robust_timeout_activation import (
    EXPECTED_JOB_NAMES,
    EXPECTED_STEP_NAME,
    SOURCE_RUN_ID,
    verify_jobs_payload,
)


def _payload(minutes: int = 180, *, conclusion: str = "cancelled") -> dict:
    start = datetime(2026, 8, 25, 1, 3, 30, tzinfo=timezone.utc)
    jobs = []
    for i, name in enumerate(sorted(EXPECTED_JOB_NAMES), start=1):
        end = start + timedelta(minutes=minutes)
        jobs.append(
            {
                "id": 1000 + i,
                "name": name,
                "status": "completed",
                "conclusion": conclusion,
                "started_at": start.isoformat().replace("+00:00", "Z"),
                "completed_at": end.isoformat().replace("+00:00", "Z"),
                "steps": [
                    {
                        "name": EXPECTED_STEP_NAME,
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                ],
            }
        )
    return {"total_count": len(jobs), "jobs": jobs}


def test_exact_timeout_is_accepted() -> None:
    result = verify_jobs_payload(_payload())
    assert result["source_run_id"] == SOURCE_RUN_ID
    assert result["technical_limit_confirmed"] is True
    assert result["scientific_method_changed"] is False
    assert result["outcome_driven_tuning"] is False
    assert len(result["jobs"]) == 4


def test_early_manual_cancel_is_rejected() -> None:
    try:
        verify_jobs_payload(_payload(120))
    except ValueError as exc:
        assert "too early" in str(exc)
    else:
        raise AssertionError("early cancellation must not activate fallback")


def test_successful_source_run_is_rejected() -> None:
    try:
        verify_jobs_payload(_payload(180, conclusion="success"))
    except ValueError as exc:
        assert "not timeout-compatible" in str(exc)
    else:
        raise AssertionError("successful source run must not activate fallback")


def test_missing_frozen_pair_is_rejected() -> None:
    payload = deepcopy(_payload())
    payload["jobs"] = payload["jobs"][:-1]
    try:
        verify_jobs_payload(payload)
    except ValueError as exc:
        assert "expected frozen RU jobs" in str(exc)
    else:
        raise AssertionError("all four frozen RU jobs are required")


if __name__ == "__main__":
    test_exact_timeout_is_accepted()
    test_early_manual_cancel_is_rejected()
    test_successful_source_run_is_rejected()
    test_missing_frozen_pair_is_rejected()
    print("RU timeout activation verifier tests passed")
