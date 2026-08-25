#!/usr/bin/env python3
"""Verify that the frozen RU pair stage actually hit its technical timeout.

This is an execution-safety helper for the exact robust-world fallback.  It does
not inspect any biological outcome.  Activation is valid only when all four
already-frozen RU pair jobs from run 32795662847 were cancelled after running
for essentially the full 180-minute job limit.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

SOURCE_RUN_ID = 32795662847
EXPECTED_JOB_NAMES = {
    "evaluate-ru-pair (2)",
    "evaluate-ru-pair (7)",
    "evaluate-ru-pair (9)",
    "evaluate-ru-pair (16)",
}
EXPECTED_STEP_NAME = "Evaluate one frozen RU declaration with unchanged v2 method"
MIN_TIMEOUT_SECONDS = 179 * 60
MAX_TIMEOUT_SECONDS = 185 * 60


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def verify_jobs_payload(payload: dict[str, Any]) -> dict[str, Any]:
    jobs = {
        str(job.get("name")): job
        for job in payload.get("jobs", [])
        if str(job.get("name")) in EXPECTED_JOB_NAMES
    }
    if set(jobs) != EXPECTED_JOB_NAMES:
        raise ValueError(f"expected frozen RU jobs {sorted(EXPECTED_JOB_NAMES)}, got {sorted(jobs)}")

    audit: list[dict[str, Any]] = []
    for name in sorted(EXPECTED_JOB_NAMES):
        job = jobs[name]
        if job.get("status") != "completed":
            raise ValueError(f"{name} has not completed; fallback activation is premature")
        if job.get("conclusion") != "cancelled":
            raise ValueError(f"{name} conclusion is {job.get('conclusion')!r}, not timeout-compatible cancelled")
        if not job.get("started_at") or not job.get("completed_at"):
            raise ValueError(f"{name} lacks timing metadata")

        elapsed = (_parse_time(job["completed_at"]) - _parse_time(job["started_at"])).total_seconds()
        if elapsed < MIN_TIMEOUT_SECONDS:
            raise ValueError(f"{name} was cancelled too early ({elapsed:.1f}s); do not activate fallback")
        if elapsed > MAX_TIMEOUT_SECONDS:
            raise ValueError(f"{name} duration is inconsistent with the 180-minute technical limit ({elapsed:.1f}s)")

        target_steps = [step for step in job.get("steps", []) if step.get("name") == EXPECTED_STEP_NAME]
        if len(target_steps) != 1:
            raise ValueError(f"{name} does not contain exactly one frozen evaluation step")
        step = target_steps[0]
        if step.get("conclusion") != "cancelled":
            raise ValueError(f"{name} frozen evaluation step was not cancelled at the technical limit")

        audit.append(
            {
                "name": name,
                "job_id": int(job["id"]),
                "started_at": job["started_at"],
                "completed_at": job["completed_at"],
                "elapsed_seconds": elapsed,
                "status": job["status"],
                "conclusion": job["conclusion"],
                "evaluation_step_conclusion": step["conclusion"],
            }
        )

    return {
        "source_run_id": SOURCE_RUN_ID,
        "technical_limit_confirmed": True,
        "expected_timeout_minutes": 180,
        "jobs": audit,
        "scientific_method_changed": False,
        "outcome_driven_tuning": False,
    }


def fetch_jobs_payload(repository: str, token: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repository}/actions/runs/{SOURCE_RUN_ID}/jobs?per_page=100"
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "acsp-ru-timeout-verifier",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs-json", type=Path)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "zuizui0223/acsp"))
    parser.add_argument("--token", default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.jobs_json is not None:
        payload = json.loads(args.jobs_json.read_text(encoding="utf-8"))
    else:
        if not args.token:
            raise SystemExit("GH_TOKEN or GITHUB_TOKEN is required when --jobs-json is not supplied")
        payload = fetch_jobs_payload(args.repository, args.token)

    result = verify_jobs_payload(payload)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
