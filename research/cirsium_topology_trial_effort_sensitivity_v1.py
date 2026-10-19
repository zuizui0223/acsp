#!/usr/bin/env python3
"""Hypothetical Cirsium site-only trial effort sensitivity; NO actual field data.

The original topology-vs-geometry methods, candidate membership, and 90-minute
effort schedule are unchanged. q is UNKNOWN for any future independent cohort.
These are optimistic two-arm normal-approximation scenarios, not a study design
approval, preregistered sample size, actual detection, or measured site effect.
"""
from __future__ import annotations

import json
import math
from statistics import NormalDist
from typing import Any

SCHEMA = "cirsium-topology-site-only-effort-sensitivity-v1"
PLANNED_PERSON_MINUTES_PER_PATCH = 90


def _prob(value: float, label: str, inclusive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    v = float(value)
    if not math.isfinite(v) or (not 0 <= v <= 1 if inclusive else not 0 < v < 1):
        raise ValueError(f"{label} outside allowed range")
    return v


def sample_size_scenario(
    site_discordance_q: float,
    risk_difference_among_distinct_sites: float,
    control_detection_fraction: float = 0.30,
    alpha_two_sided: float = 0.05,
    target_power: float = 0.80,
) -> dict[str, Any]:
    """Estimate balanced arm sizes for a hypothetical patch-level binary endpoint.

    Assumes same-site no effect, q balanced between arms, constant conditional
    risk difference across discordant patches, independent evaluable patches,
    no attrition, no within-taxon/sector clustering, and identical search process.

    Formula: n_arm = ceil((z_alpha*sqrt(2*pbar*(1-pbar)) +
                         z_power*sqrt(p0*(1-p0)+p1*(1-p1)))**2 / delta**2).
    It is a normal approximation, NOT an exact/randomization power calculation.
    """
    q = _prob(site_discordance_q, "q", inclusive=True)
    p0 = _prob(control_detection_fraction, "control_detection_fraction")
    alpha = _prob(alpha_two_sided, "alpha_two_sided")
    power = _prob(target_power, "target_power")
    theta = risk_difference_among_distinct_sites
    if isinstance(theta, bool) or not isinstance(theta, (int, float)):
        raise ValueError("conditional difference must be numeric")
    theta = float(theta)
    if not math.isfinite(theta) or not -1 <= theta <= 1:
        raise ValueError("conditional risk difference must be in [-1, 1]")
    delta = q * theta
    p1 = p0 + delta
    if not 0 <= p1 <= 1:
        raise ValueError("assumed treated response probability falls outside [0,1]")

    common = {
        "schema_version": SCHEMA,
        "status": "HYPOTHETICAL_NORMAL_APPROXIMATION_NOT_FIELD_EVIDENCE",
        "assumed_q_not_measured": q,
        "assumed_conditional_distinct_site_risk_difference": theta,
        "assumed_control_patch_success_fraction": p0,
        "assumed_intention_to_treat_difference": delta,
        "alpha_two_sided": alpha,
        "target_power": power,
        "real_new_cohort_q": None,
        "actual_cohort_field_ready": False,
        "prospective_outcomes_opened": False,
        "historical_cirsium_patch_outcomes_used": False,
        "planned_person_minutes_per_patch": PLANNED_PERSON_MINUTES_PER_PATCH,
    }
    if delta == 0:
        return {**common, "required_per_arm": None, "required_total_patches": None,
                "optimistic_active_person_hours": None,
                "interpretation": "Zero assumed site-choice signal; finite-sample power is undefined for this alternative."}

    pbar = (p0 + p1) / 2
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(power)
    numerator = (
        z_alpha * math.sqrt(2 * pbar * (1 - pbar))
        + z_power * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))
    ) ** 2
    n_arm = math.ceil(numerator / (delta**2))
    return {
        **common,
        "required_per_arm": n_arm,
        "required_total_patches": 2 * n_arm,
        "optimistic_active_person_hours": (2 * n_arm * PLANNED_PERSON_MINUTES_PER_PATCH) / 60,
        "interpretation": "Scenario only; excludes travel, access, phenology, attrition and clustered taxon/sector effects.",
    }


def main() -> None:
    scenarios = [
        sample_size_scenario(0.25, 0.10),
        sample_size_scenario(0.25, 0.20),
        sample_size_scenario(0.50, 0.20),
        sample_size_scenario(1.00, 0.20),
        sample_size_scenario(0.00, 0.20),
    ]
    print(json.dumps({"schema_version": SCHEMA, "actual_q_known": False,
                      "new_independent_field_cohort_ready": False,
                      "scenarios": scenarios}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
