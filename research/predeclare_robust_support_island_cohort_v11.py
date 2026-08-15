#!/usr/bin/env python3
"""Bind the untouched island cohort sampler to protocol v1.1.

Protocol v1.1 changes only three island sampling cells after the v1 sampling-
frame audit produced zero taxon draws. No occurrence coordinates or outcomes
were inspected before this availability-only amendment.
"""
from __future__ import annotations

import json

import predeclare_robust_support_island_cohort as sampler

EXPECTED = "e62e0e65e490ee6f04ce50dc3009407cb9ed1875fd610f153592104934b77acd"

if __name__ == "__main__":
    sampler.EXPECTED_PROTOCOL = EXPECTED
    args = sampler.parser().parse_args()
    print(json.dumps(sampler.run(args.protocol, args.output), indent=2))
