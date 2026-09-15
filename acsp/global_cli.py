"""Species-name command for global historical-country candidate patches."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .global_patches import discover_global_candidate_patches


def build_parser():
    parser = argparse.ArgumentParser(prog="acsp-global-patches", description="Generate non-ranked patches from a species name using historical-only country planning and the fixed global adapter. Large countries can take substantial time; no tiles are dropped to speed up a run.")
    parser.add_argument("--taxon", required=True, help="Scientific species name.")
    parser.add_argument("--country", default="", help="Optional fixed ISO alpha-2 target, never substituted; explicit-country searches are not independently confirmed.")
    parser.add_argument("--out-dir", required=True, help="New output directory. Existing directories are never overwritten.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    latest = {"requested_name": args.taxon, "requested_country": args.country or None}

    def write_json(name, payload):
        (out / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def progress(phase, details):
        latest.update(details)
        latest["phase"] = phase
        write_json("progress.json", latest)
        if "country_plan" in details:
            write_json("country_plan.json", details["country_plan"])
        print(phase, file=sys.stderr, flush=True)

    try:
        patches, audit = discover_global_candidate_patches(args.taxon, country=args.country, progress=progress)
        path = out / "candidate_patches.csv"
        patches.to_csv(path, index=False)
        audit["candidate_patches_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        write_json("summary.json", audit)
    except Exception as exc:
        write_json("summary.json", {**latest, "status": "TECHNICAL_FAILURE", "error_type": type(exc).__name__, "error_message": str(exc), "new_scientific_confirmation": False})
        print(f"TECHNICAL_FAILURE: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": audit["status"], "candidate_patch_count": len(patches), "out_dir": str(out)}, ensure_ascii=False))
    return 0 if audit["status"] in {"ROBUST_READY", "ROBUST_EMPTY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
