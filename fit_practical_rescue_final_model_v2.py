#!/usr/bin/env python3
"""Refit the unchanged final rescue model after the corrected official GRTS v2 gate.

This is deliberately a thin binding wrapper. Training features, targets,
estimator construction, hyperparameters, runtime guards, and all 72 development
fold loaders remain in fit_practical_rescue_final_model.py unchanged.
"""
from __future__ import annotations

import json

import fit_practical_rescue_final_model as base

EXPECTED_GRTS_DEVELOPMENT_PROTOCOL = "74fec14b44035e897072b022d82ea30c00b27ce1bb95c16a0e9a5578a3d3da7a"

parser = base.parser


def run(standard_roots, sdm_root, rescue_protocol_path, grts_gate_manifest_path, output):
    # Keep the corrected-v2 gate identity local to this call so importing the
    # wrapper cannot alter the retained v1 refit implementation or its tests.
    original = base.EXPECTED_GRTS_DEVELOPMENT_PROTOCOL
    try:
        base.EXPECTED_GRTS_DEVELOPMENT_PROTOCOL = EXPECTED_GRTS_DEVELOPMENT_PROTOCOL
        return base.run(
            standard_roots,
            sdm_root,
            rescue_protocol_path,
            grts_gate_manifest_path,
            output,
        )
    finally:
        base.EXPECTED_GRTS_DEVELOPMENT_PROTOCOL = original


if __name__ == "__main__":
    args = parser().parse_args()
    print(json.dumps(run(
        args.standard_root,
        args.sdm_root,
        args.rescue_protocol,
        args.grts_gate_manifest,
        args.output,
    ), indent=2, ensure_ascii=False))
