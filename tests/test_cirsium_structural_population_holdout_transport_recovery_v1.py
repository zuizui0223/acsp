from __future__ import annotations

import pandas as pd
import pytest
import requests

import recover_cirsium_structural_population_holdout_transport_v1 as recovery


def _amendment():
    return {
        "transport_retry": {
            "retryable_http_statuses": [429, 500, 501, 502, 503, 504, 505, 506, 507, 508, 510, 511],
            "maximum_total_attempts": 5,
            "sleep_before_retry_seconds": [2, 5, 10, 20],
        }
    }


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = int(status)
    return requests.HTTPError(f"HTTP {status}", response=response)


def test_transport_retry_recovers_identical_503_request_without_substitution() -> None:
    calls = []
    sleeps = []

    def fake_fetch(species_name: str, *args, **kwargs):
        calls.append((species_name, args, dict(kwargs)))
        if len(calls) <= 2:
            raise _http_error(503)
        return pd.DataFrame({"x": [1]}), {"eligible_records": 1}

    recovery.ATTEMPT_LOG.clear()
    frame, audit = recovery.fetch_gbif_species_with_transport_retry(
        "Cirsium otayae",
        maximum_records=10000,
        fetcher=fake_fetch,
        sleep_fn=sleeps.append,
        amendment=_amendment(),
    )
    assert len(frame) == 1
    assert len(calls) == 3
    assert calls[0] == calls[1] == calls[2]
    assert sleeps == [2.0, 5.0]
    assert audit["transport_attempts"] == 3
    assert audit["transport_retry_used"] is True
    assert audit["transport_retry_http_statuses"] == [503, 503]
    assert recovery.ATTEMPT_LOG["Cirsium otayae"]["final_status"] == "SUCCESS"


def test_transport_retry_does_not_retry_non429_4xx() -> None:
    calls = []

    def fake_fetch(species_name: str, *args, **kwargs):
        calls.append(species_name)
        raise _http_error(400)

    with pytest.raises(requests.HTTPError):
        recovery.fetch_gbif_species_with_transport_retry(
            "Cirsium pendulum",
            maximum_records=10000,
            fetcher=fake_fetch,
            sleep_fn=lambda _: pytest.fail("400 must not sleep/retry"),
            amendment=_amendment(),
        )
    assert calls == ["Cirsium pendulum"]


def test_transport_retry_stops_at_frozen_attempt_cap() -> None:
    calls = []
    sleeps = []

    def fake_fetch(species_name: str, *args, **kwargs):
        calls.append(species_name)
        raise _http_error(503)

    with pytest.raises(requests.HTTPError):
        recovery.fetch_gbif_species_with_transport_retry(
            "Cirsium pendulum",
            maximum_records=10000,
            fetcher=fake_fetch,
            sleep_fn=sleeps.append,
            amendment=_amendment(),
        )
    assert len(calls) == 5
    assert sleeps == [2.0, 5.0, 10.0, 20.0]
