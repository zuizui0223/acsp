#!/usr/bin/env python3
from pathlib import Path

MARKER = "## 2026-08-16 - ChatGPT (OpenAI) - Adaptive survey architecture convergence"
ENTRY = """## 2026-08-16 - ChatGPT (OpenAI) - Adaptive survey architecture convergence

Changed files:
- Campanula microenvironment development scripts/workflows and development freezes
- validation/izu_island_microenvironment_random_taxa_20260816/*
- validation/izu_microenvironment_generalization_development/*
- research/acsp_algorithm_component_ledger.json
- research/ACSP_ADAPTIVE_SURVEY_ARCHITECTURE.md
- research/acsp_training_domain_gate.py and tests
- research/develop_izu_nested_training_policy_selection_v2.py and tests
- CHANGELOG_AI.md

Summary:
- Treated Campanula microdonta as a development instrument rather than independent validation and removed the old candidate-universe ceiling by full-island search.
- Preserved negative ablations: static WorldCover composition, the current NDVI transition/gradient representation, mandatory persistent-patch filtering, fixed Campanula microclimate correction, occurrence-count island allocation, and independent environmental Top-cell ranking did not generalize sufficiently.
- The frozen Campanula-derived 0.90 NDVI + 0.10 microclimate ranking failed a predeclared unseen 16-taxon Izu plant transfer (0.7192 recall versus 0.8608 same-allocation random); those 16 taxa are permanently development-only.
- Diagnosed survey-budget saturation: 793 points with a 1 km recovery buffer covered most of the island grid and drove same-allocation random recall to about 0.86, so point count alone is not treated as field budget.
- Reframed the main algorithm as occurrence-conditioned ecological support followed by set-level maximum geographic coverage under an external survey budget.
- Under a strong geometry-only comparator, only q=0.10 / K=5 / 1 km retained a provisional within-island NDVI-support signal (+0.030 recall; bootstrap lower bound >0; sign-flip p<0.05). NDVI between-island allocation and training-occurrence-count allocation were rejected.
- Tested and rejected prototype-LOO environmental reconstruction as an adaptive support-width selector; it reverted to q=1 in 60/80 folds and lost the K=5 q10 advantage. Internal objectives must match downstream survey-set recovery.
- Added fully nested training-only support-policy selection, then tightened it before inspecting v1 output so every q/K comparison uses identical complete inner spatial folds; outer-held-out coordinates remain invisible during q selection.
- Added a component evidence ledger and architecture document. Future experiments must target one unresolved layer and may not silently reintroduce rejected complexity.
- Added a training-only domain gate because the historical kingdom-first surface inference can misclassify aquatic plants as terrestrial. Training land support can override coarse taxonomy in the research method.
- Audited the previously predeclared outside-Izu 24-pair cohort. Its occurrence outcomes remain untouched, but its taxon identities exposed aquatic taxa and motivated the domain gate, so it is no longer eligible as independent confirmation of that gate.

Features preserved:
- Production ACSP behavior, optional SDM/SSDM, maps, exports, and the frozen Practical Core are unchanged by this development line.
- The frozen 192-pair Practical Core confirmation cohort remains untouched and unconsumed.
- Campanula field coordinates do not enter inference-time candidate generation or cross-taxon support-policy selection.

Validation / current gates:
- Campanula development can recover all 19/19 field clusters at 1 km, but Campanula is development evidence only.
- The 16-taxon transfer failure and all subsequent negative development results remain in repository artifacts.
- Training-stability adaptive-support run 31944106155 completed green and was scientifically rejected as the support-width selector.
- Strict fully nested paired support-policy selection is the active scientific experiment; no new external confirmation cohort is consumed before method freeze.

Known risks / TODO:
- Support-policy selection remains unresolved until strict nested development finishes.
- If nested q selection fails, the next allowed change is ecological-support representation (multi-modal or scale-adaptive support), not K/r/q retuning on outer outcomes.
- The domain gate still requires prospective integration into a newly frozen external protocol.
- Route/equal-area field-budget output follows only after ecological support and set selection stabilize.
- Final cross-taxon/cross-island confirmation requires a new post-freeze cohort; inspected cohorts cannot be recycled as confirmation.

"""


def main() -> None:
    path = Path("CHANGELOG_AI.md")
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return
    prefix = "# AI Change Log\n\n"
    updated = prefix + ENTRY + text[len(prefix):] if text.startswith(prefix) else ENTRY + text
    path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
