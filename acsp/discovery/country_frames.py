"""Provider-neutral country-frame planning for experimental global discovery.

The core lesson from opened global development is that an automatic global search
must not confuse an arbitrary historical country with the best-supported place to
instantiate the frozen robust machinery. Conversely, when a user explicitly asks
about one country, ACSP must not silently substitute an easier country.

This module uses historical evidence and provider coverage only. It never reads
heldout occurrences, candidate-patch recovery, field outcomes, or access data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
from typing import Iterable, Mapping


class CountryFrameState(str, Enum):
    READY = "READY"
    INSUFFICIENT_HISTORICAL_EVIDENCE = "INSUFFICIENT_HISTORICAL_EVIDENCE"
    PROVIDER_UNSUPPORTED = "PROVIDER_UNSUPPORTED"
    NO_HISTORICAL_COUNTRY = "NO_HISTORICAL_COUNTRY"


@dataclass(frozen=True)
class CountryFrameCandidate:
    country_code: str
    historical_record_count: int
    provider_supported: bool
    state: CountryFrameState
    evidence_rank: int | None
    stable_tie_break: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CountryFramePlan:
    mode: str
    selected_country_code: str | None
    state: CountryFrameState
    candidates: tuple[CountryFrameCandidate, ...]
    historical_min_count: int
    heldout_used: bool = False
    field_outcomes_used: bool = False
    country_substitution_after_target_declaration: bool = False

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["state"] = self.state.value
        value["candidates"] = [
            {**candidate.as_dict(), "state": candidate.state.value}
            for candidate in self.candidates
        ]
        return value


def _stable_tie_break(country_code: str, seed: int) -> str:
    return hashlib.sha256(f"{int(seed)}|{str(country_code).upper()}".encode("utf-8")).hexdigest()


def rank_historical_country_frames(
    country_counts: Mapping[str, int],
    *,
    provider_supported_country_codes: Iterable[str],
    historical_min_count: int = 5,
    tie_break_seed: int = 0,
) -> tuple[CountryFrameCandidate, ...]:
    """Rank all historical country frames by evidence without heldout outcomes.

    Eligible provider-supported countries are ordered by descending historical
    record count. Stable hash order breaks equal-count ties. Ineligible countries
    remain in the returned audit after all ready countries.
    """
    minimum = int(historical_min_count)
    if minimum < 1:
        raise ValueError("historical_min_count must be positive")
    supported = {str(code).strip().upper() for code in provider_supported_country_codes if str(code).strip()}
    normalized: list[tuple[str, int, bool, CountryFrameState, str]] = []
    for raw_code, raw_count in dict(country_counts).items():
        code = str(raw_code).strip().upper()
        if not code:
            continue
        count = int(raw_count)
        if count < 0:
            raise ValueError("historical country counts cannot be negative")
        is_supported = code in supported
        if not is_supported:
            state = CountryFrameState.PROVIDER_UNSUPPORTED
        elif count < minimum:
            state = CountryFrameState.INSUFFICIENT_HISTORICAL_EVIDENCE
        else:
            state = CountryFrameState.READY
        normalized.append((code, count, is_supported, state, _stable_tie_break(code, tie_break_seed)))

    state_order = {
        CountryFrameState.READY: 0,
        CountryFrameState.INSUFFICIENT_HISTORICAL_EVIDENCE: 1,
        CountryFrameState.PROVIDER_UNSUPPORTED: 2,
    }
    normalized.sort(key=lambda row: (state_order[row[3]], -row[1], row[4], row[0]))
    output: list[CountryFrameCandidate] = []
    ready_rank = 0
    for code, count, is_supported, state, tie in normalized:
        rank = None
        if state == CountryFrameState.READY:
            ready_rank += 1
            rank = ready_rank
        output.append(
            CountryFrameCandidate(
                country_code=code,
                historical_record_count=count,
                provider_supported=is_supported,
                state=state,
                evidence_rank=rank,
                stable_tie_break=tie,
            )
        )
    return tuple(output)


def plan_automatic_global_country(
    country_counts: Mapping[str, int],
    *,
    provider_supported_country_codes: Iterable[str],
    historical_min_count: int = 5,
    tie_break_seed: int = 0,
) -> CountryFramePlan:
    """Choose the best-supported provider-ready historical country for auto mode.

    No heldout or outcome information is used. The complete ranked country audit
    remains attached so future multi-country portfolios can consume it without
    changing the selection semantics.
    """
    candidates = rank_historical_country_frames(
        country_counts,
        provider_supported_country_codes=provider_supported_country_codes,
        historical_min_count=historical_min_count,
        tie_break_seed=tie_break_seed,
    )
    ready = [candidate for candidate in candidates if candidate.state == CountryFrameState.READY]
    if ready:
        return CountryFramePlan(
            mode="automatic_global",
            selected_country_code=ready[0].country_code,
            state=CountryFrameState.READY,
            candidates=candidates,
            historical_min_count=int(historical_min_count),
        )
    if not candidates:
        state = CountryFrameState.NO_HISTORICAL_COUNTRY
    elif any(candidate.provider_supported for candidate in candidates):
        state = CountryFrameState.INSUFFICIENT_HISTORICAL_EVIDENCE
    else:
        state = CountryFrameState.PROVIDER_UNSUPPORTED
    return CountryFramePlan(
        mode="automatic_global",
        selected_country_code=None,
        state=state,
        candidates=candidates,
        historical_min_count=int(historical_min_count),
    )


def plan_explicit_target_country(
    target_country_code: str,
    country_counts: Mapping[str, int],
    *,
    provider_supported_country_codes: Iterable[str],
    historical_min_count: int = 5,
    tie_break_seed: int = 0,
) -> CountryFramePlan:
    """Assess one user-declared country without substituting a different frame."""
    target = str(target_country_code).strip().upper()
    if not target:
        raise ValueError("target_country_code is required")
    candidates = rank_historical_country_frames(
        country_counts,
        provider_supported_country_codes=provider_supported_country_codes,
        historical_min_count=historical_min_count,
        tie_break_seed=tie_break_seed,
    )
    lookup = {candidate.country_code: candidate for candidate in candidates}
    candidate = lookup.get(target)
    supported = {str(code).strip().upper() for code in provider_supported_country_codes if str(code).strip()}
    if candidate is None:
        state = CountryFrameState.INSUFFICIENT_HISTORICAL_EVIDENCE if target in supported else CountryFrameState.PROVIDER_UNSUPPORTED
    else:
        state = candidate.state
    return CountryFramePlan(
        mode="explicit_target",
        selected_country_code=target if state == CountryFrameState.READY else None,
        state=state,
        candidates=candidates,
        historical_min_count=int(historical_min_count),
        country_substitution_after_target_declaration=False,
    )


__all__ = [
    "CountryFrameState",
    "CountryFrameCandidate",
    "CountryFramePlan",
    "rank_historical_country_frames",
    "plan_automatic_global_country",
    "plan_explicit_target_country",
]
