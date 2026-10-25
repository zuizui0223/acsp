#!/usr/bin/env python3
"""Network-free audit of provisional ACSP journal-submission editorial materials.

This audit cannot certify author declarations, a publisher's journal-specific
requirements, DOI availability, biological field results, or actual submission.
The authoritative frozen paper validator remains validate_submission_alignment.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
HIGHLIGHTS = PAPER / "SUBMISSION_HIGHLIGHTS.md"
ABSTRACT = PAPER / "SUBMISSION_ABSTRACT_SHORT.md"
COVER = PAPER / "SUBMISSION_COVER_LETTER_DRAFT.md"
MANUSCRIPT = PAPER / "MANUSCRIPT_ROBUST_PATCH_DRAFT.md"
PRIMARY_TABLE = PAPER / "generated" / "table_1_robust_patch_confirmation.csv"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _paragraph_under_heading(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    blocks = text.split("\n\n", 1)
    _require(len(blocks) == 2 and blocks[0].startswith("# "), f"Missing draft title: {path.name}")
    return blocks[1].strip()


def validate(
    *,
    highlights_path: Path = HIGHLIGHTS,
    abstract_path: Path = ABSTRACT,
    cover_path: Path = COVER,
    manuscript_path: Path = MANUSCRIPT,
    primary_table_path: Path = PRIMARY_TABLE,
) -> dict[str, object]:
    """Verify a *draft* against the immutable main manuscript and primary CSV."""
    manuscript = manuscript_path.read_text(encoding="utf-8")
    _require(manuscript.startswith("# "), "No authoritative main manuscript title")
    title = manuscript.splitlines()[0][2:].strip()
    _require("## Abstract\n" in manuscript, "Main manuscript missing original abstract")
    _require("To be completed using the target journal's CRediT taxonomy" in manuscript,
             "Authors' unconfirmed CRediT gate appears silently resolved")

    with primary_table_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    _require(len(rows) == 1, "Primary confirmation must be exactly one row")
    primary = rows[0]
    _require(primary["analysis_scope"] == "validated_japan_12_region_frame", "Wrong scientific frame")
    _require(primary["product"] == "non-ranked robust candidate patches", "Wrong product")
    _require(primary["confirmation_status"] == "untouched_confirmation_passed", "Frozen trial altered")
    _require(primary["comparator"] == "same-size random candidate-patch sets", "Comparator changed")

    h_body = _paragraph_under_heading(highlights_path)
    lines = [line.strip() for line in h_body.splitlines() if line.strip()]
    _require(all(line.startswith("- ") for line in lines), "Highlights require bullets only")
    highlights = [line[2:] for line in lines]
    _require(3 <= len(highlights) <= 5, "Provide 3-5 provisional Highlights")
    _require(all(0 < len(line) <= 85 for line in highlights),
             "Every Highlight must be 1-85 characters")
    _require(len(set(highlights)) == len(highlights), "Duplicate highlight")
    _require(any("non-ranked" in s for s in highlights), "Candidate-patch object missing")
    _require(any("+0.0856" in s for s in highlights), "Positive effect missing")
    _require(any("did not pass" in s for s in highlights), "Failed transfer gate missing")
    _require(any("abstention" in s for s in highlights), "Provider-STOP boundary missing")

    abstract = _paragraph_under_heading(abstract_path)
    _require(not any(line.startswith("#") for line in abstract.splitlines()),
             "Short alternative must be a single abstract paragraph")
    word_count = len(abstract.split())
    _require(120 <= word_count <= 250, "Alternative abstract outside 120-250 working words")
    _require("\n" not in abstract, "Alternative abstract must be one paragraph")
    required_tokens = [
        "2.5%", "1-km", "10-km", "12", "24-taxon", "48-taxon",
        "34/48", "29 HTTP 429", "3,161",
        str(int(primary["declared_taxon_region_pairs"])),
        str(int(primary["declared_folds"])),
        f'{float(primary["mean_lift_over_comparator"]):.5f}',
        f'{float(primary["bootstrap_ci95_lower"]):.5f}',
        f'{float(primary["bootstrap_ci95_upper"]):.5f}',
        f'{float(primary["plant_mean_lift"]):.5f}',
        f'{float(primary["animal_mean_lift"]):.5f}',
    ]
    for value in required_tokens:
        _require(value in abstract, f"Missing frozen abstract evidence: {value}")
    _require("same-size random patch sets" in abstract, "Comparator omitted")
    _require("did not meet all preregistered gates" in abstract, "Global failure gate omitted")
    _require("stopped before held-out evaluation" in abstract, "Provider STOP omitted")
    _require("but not calibrated occupancy" in abstract, "Claim ceiling omitted")
    _require("explicit abstention" in abstract, "Abstention omitted")

    cover = _paragraph_under_heading(cover_path)
    _require(cover.startswith("Dear Editor,"), "Cover letter must address editor")
    _require(f"“{title}”" in cover, "Cover letter must use exact manuscript title")
    _require("*Ecological Informatics*" in cover, "Journal fit missing")
    _require("96 taxon" in cover and "480 spatial folds" in cover,
             "Frozen sample size missing")
    _require(f'{float(primary["mean_lift_over_comparator"]):.5f}' in cover,
             "Cover letter effect differs from primary table")
    _require("preregistered failures" in cover and "stopped before held-out evaluation" in cover,
             "Failed transfer/abstention not communicated")
    _require("occupancy probability" in cover, "Claim ceiling missing")
    _require("[Corresponding author" in cover and "Internal note" in cover,
             "Unconfirmed author metadata must remain explicit")
    _require(len(cover.split()) <= 400, "Provisional cover letter exceeds working one-page length")

    joined = "\n".join(highlights) + abstract + cover
    disallowed = [
        "globally validated", "global superiority established",
        "significantly better than SDM", "confirmed field efficiency",
        "occupancy probabilities estimated",
    ]
    for phrase in disallowed:
        _require(phrase not in joined.lower(), f"Unsupported affirmative claim: {phrase}")

    return {
        "status": "editorial_draft_consistency_passed",
        "author_submission_ready": False,
        "journal_specific_requirements_verified": False,
        "frozen_manuscript_edited_by_packet": False,
        "primary_confirmatory_pairs": int(primary["declared_taxon_region_pairs"]),
        "primary_confirmatory_folds": int(primary["declared_folds"]),
        "highlight_count": len(highlights),
        "highlight_character_counts": [len(s) for s in highlights],
        "short_abstract_words": word_count,
        "cover_draft_words": len(cover.split()),
        "release_doi_verified": False,
        "author_contributions_and_conflicts_confirmed": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
