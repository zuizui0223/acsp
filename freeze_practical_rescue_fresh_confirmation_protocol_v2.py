#!/usr/bin/env python3
"""Freeze the model-bound fresh confirmation protocol against corrected GRTS v2.

The underlying cohort, exclusion, inference, runtime, and leakage contracts are
reused unchanged. Only the already-frozen corrected GRTS development identity
and feasible diagnostic-replacement rule are substituted before any fresh taxon
is sampled or any fresh outcome is inspected.
"""
from __future__ import annotations

import hashlib
import json

import freeze_practical_rescue_fresh_confirmation_protocol as base

GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT = "74fec14b44035e897072b022d82ea30c00b27ce1bb95c16a0e9a5578a3d3da7a"
base.GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT = GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT

parser = base.parser


def run(model, model_manifest, excluded_taxa, exclusion_manifest, output):
    base.run(model, model_manifest, excluded_taxa, exclusion_manifest, output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload.pop("protocol_fingerprint", None)
    payload["protocol_id"] = "acsp-practical-rescue-fresh-confirmation-v2"
    official = payload["official_grts"]
    requested = int(official.pop("replacement_sites"))
    official["replacement_sites_requested"] = requested
    official["replacement_sites_effective_rule"] = (
        "min(replacement_sites_requested, max(candidate_frame_rows - n_base, 0))"
    )
    official["replacement_sites_role"] = (
        "diagnostic oversample only; lack of spare rows cannot invalidate an otherwise valid primary base design"
    )
    payload["inference"]["primary_contrast"] = (
        "practical_rescue_final_72 - corrected_official_grts_proportional_local_mindis10km"
    )
    payload["estimand"]["primary"] = (
        "taxon-region-pair mean over five spatial outer folds of frozen Practical Rescue Top-5 held-out recovery "
        "minus the mean of 50 pre-outcome corrected official GRTS Top-5 draws with feasible diagnostic replacements"
    )
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["protocol_fingerprint"] = fingerprint
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        "status": payload["status"],
        "protocol_fingerprint": fingerprint,
        "final_model_sha256": payload["final_model"]["model_sha256"],
        "excluded_taxa_sha256": payload["exclusion"]["excluded_taxa_sha256"],
        "confirmation_taxa_sampled": False,
        "confirmation_occurrence_outcomes_inspected": False,
        "corrected_grts_v2": True,
    }


if __name__ == "__main__":
    args = parser().parse_args()
    print(json.dumps(run(
        args.model,
        args.model_manifest,
        args.excluded_taxa,
        args.exclusion_manifest,
        args.output,
    ), indent=2, ensure_ascii=False))
