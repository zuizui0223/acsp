"""Provider-neutral availability states for ACSP Discovery.

This module separates whether a robust prediction can be constructed and later
evaluated from whether the frozen robust ecological signal is useful. It does
not relax the validated robust core or turn sparse evidence into pseudo-exact
anchors.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class AvailabilityState(str, Enum):
    PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
    SENTINEL_OR_ABSTAIN = "SENTINEL_OR_ABSTAIN"
    ROBUST_EMPTY = "ROBUST_EMPTY"
    ROBUST_READY_EVALUABLE = "ROBUST_READY_EVALUABLE"
    ROBUST_READY_NOT_RETROSPECTIVELY_EVALUABLE = "ROBUST_READY_NOT_RETROSPECTIVELY_EVALUABLE"


@dataclass(frozen=True)
class AvailabilityDecision:
    state: AvailabilityState
    robust_prediction_constructible: bool
    retrospective_evaluation_available: bool
    ecological_prediction_failure: bool
    reason: str
    human_access_used: bool = False
    field_outcomes_used_to_choose_state: bool = False
    validated_robust_core_changed: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_availability_state(
    *,
    country_or_outer_frame_available: bool,
    historical_evidence_sufficient: bool,
    robust_candidate_generation_status: str,
    recent_heldout_available: bool,
) -> AvailabilityDecision:
    """Resolve an auditable availability state without retuning the robust core.

    ``robust_candidate_generation_status`` must be one of ``not_attempted``,
    ``generated`` or ``empty``. An empty robust result is not treated as a
    provider/evidence failure: it is a legitimate outcome of the frozen robust
    construction when inputs were adequate.
    """
    status = str(robust_candidate_generation_status).strip().lower()
    if status not in {"not_attempted", "generated", "empty"}:
        raise ValueError("robust_candidate_generation_status must be not_attempted, generated, or empty")

    if not bool(country_or_outer_frame_available):
        if status != "not_attempted":
            raise ValueError("robust generation cannot precede an available outer frame")
        return AvailabilityDecision(
            state=AvailabilityState.PROVIDER_BLOCKED,
            robust_prediction_constructible=False,
            retrospective_evaluation_available=False,
            ecological_prediction_failure=False,
            reason="No declared/constructible outer frame; provider or geographic declaration is blocked.",
        )

    if not bool(historical_evidence_sufficient):
        if status != "not_attempted":
            raise ValueError("robust generation cannot proceed when historical evidence is insufficient")
        return AvailabilityDecision(
            state=AvailabilityState.SENTINEL_OR_ABSTAIN,
            robust_prediction_constructible=False,
            retrospective_evaluation_available=bool(recent_heldout_available),
            ecological_prediction_failure=False,
            reason="Historical evidence is insufficient for the frozen robust construction; route to a separately justified sentinel lane or abstain.",
        )

    if status == "not_attempted":
        raise ValueError("robust generation must be attempted when frame and historical evidence are sufficient")

    if status == "empty":
        return AvailabilityDecision(
            state=AvailabilityState.ROBUST_EMPTY,
            robust_prediction_constructible=True,
            retrospective_evaluation_available=bool(recent_heldout_available),
            ecological_prediction_failure=False,
            reason="The frozen robust core was constructible but returned no candidate patches; retain this as a legitimate empty robust result.",
        )

    if bool(recent_heldout_available):
        return AvailabilityDecision(
            state=AvailabilityState.ROBUST_READY_EVALUABLE,
            robust_prediction_constructible=True,
            retrospective_evaluation_available=True,
            ecological_prediction_failure=False,
            reason="A frozen robust candidate set is constructible and a recent heldout outcome is available for retrospective evaluation.",
        )

    return AvailabilityDecision(
        state=AvailabilityState.ROBUST_READY_NOT_RETROSPECTIVELY_EVALUABLE,
        robust_prediction_constructible=True,
        retrospective_evaluation_available=False,
        ecological_prediction_failure=False,
        reason="A frozen robust candidate set is constructible, but no recent heldout outcome exists; prediction availability and retrospective evaluability are separate.",
    )


__all__ = ["AvailabilityState", "AvailabilityDecision", "resolve_availability_state"]
