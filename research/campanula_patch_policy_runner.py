#!/usr/bin/env python3
"""Run the Campanula patch policy with JSON-safe oracle diagnostics."""
from __future__ import annotations

import campanula_patch_policy as policy


_original_oracle = policy.exact_oracle_set_cover


def json_safe_oracle(*args, **kwargs):
    result = _original_oracle(*args, **kwargs)
    if result is not None and "island_patch_counts" in result:
        result["island_patch_counts"] = {
            str(key): int(value)
            for key, value in result["island_patch_counts"].items()
        }
    return result


if __name__ == "__main__":
    policy.exact_oracle_set_cover = json_safe_oracle
    policy.main()
