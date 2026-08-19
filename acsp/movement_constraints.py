"""Physical movement constraints for ACSP operational routing.

The user declares which movement modes are actually available. ACSP does not
invent missing links and does not replace them with straight-line travel. This
module is intentionally operational: movement modes never alter ecological
support or site ranking.
"""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def normalize_mode(value: object) -> str:
    """Normalize one routing-mode label for deterministic matching."""
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        raise ValueError("movement mode must be non-empty")
    return text


def apply_movement_constraints(
    travel_matrix: pd.DataFrame,
    *,
    allowed_modes: Iterable[str],
) -> pd.DataFrame:
    """Keep only explicitly allowed movement edges.

    ``allowed_modes`` is an allow-list, not a preference ranking. Edges whose
    mode is absent from the allow-list are removed and therefore become
    unreachable downstream. This is the mechanism that prevents impossible
    straight-line, flight, or other undeclared movement from entering the
    automatic effort calculation.
    """
    if travel_matrix is None:
        raise ValueError("travel_matrix is required")
    if "mode" not in travel_matrix.columns:
        raise ValueError(
            "travel_matrix must contain an explicit mode column when movement constraints are used"
        )
    allowed = {normalize_mode(mode) for mode in allowed_modes}
    if not allowed:
        raise ValueError("allowed_modes must contain at least one movement mode")

    work = travel_matrix.copy()
    work["mode"] = work["mode"].map(normalize_mode)
    constrained = work[work["mode"].isin(allowed)].copy().reset_index(drop=True)
    constrained.attrs.update(getattr(travel_matrix, "attrs", {}))
    constrained.attrs["allowed_modes"] = sorted(allowed)
    constrained.attrs["movement_constraints_applied"] = True
    constrained.attrs["removed_edge_count"] = int(len(work) - len(constrained))
    return constrained
