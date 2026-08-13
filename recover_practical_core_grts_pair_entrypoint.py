#!/usr/bin/env python3
"""Compatibility entry point for the frozen-artifact GRTS recovery runner.

The recovery implementation originally called its private ``_run_grts`` helper
with the keyword ``draw_path`` while the helper's parameter is named
``output_path``.  This shim fixes only that implementation mismatch at runtime;
it does not alter the frozen cohort, candidate pools, selections, seeds, GRTS
settings, held-out outcomes, or scientific protocols.
"""
from __future__ import annotations

import json

import recover_practical_core_grts_pair as recovery

_ORIGINAL_RUN_GRTS = recovery._run_grts


def _run_grts_compat(*args, draw_path=None, output_path=None, **kwargs):
    if output_path is not None and draw_path is not None:
        raise TypeError("specify only one of output_path or draw_path")
    resolved_output = output_path if output_path is not None else draw_path
    if resolved_output is None:
        raise TypeError("missing output_path/draw_path")
    return _ORIGINAL_RUN_GRTS(*args, output_path=resolved_output, **kwargs)


def main() -> None:
    recovery._run_grts = _run_grts_compat
    args = recovery.parser().parse_args()
    print(json.dumps(recovery.run(args), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
