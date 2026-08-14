# Research and validation pipeline

This directory holds the retrospective validation, benchmark, and comparator
machinery. It is **not** part of the survey-planning tool that users install.

The separation is deliberate. The repository root is the tool: the Streamlit
application, the `acsp` package, the R package, and their tests. Everything in
this directory exists to test claims about that tool and to produce
publication artifacts.

## Layout

| Path | Contents |
|---|---|
| `research/*.py` | Benchmark runners, cohort samplers, aggregators, guardrail evaluators |
| `research/test_*.py` | Tests for the above |
| `../validation/` | Frozen protocol JSON, predeclared cohorts, frozen result sets |
| `../benchmark_results/` | Retained confirmation artifacts |
| `../benchmark_methods/` | R comparators (`spsurvey::grts`, `biosurvey`) |
| `../paper/` | Manuscript draft and table builders |
| `../field_validation/` | Prospective field records |
| `../legacy/` | Superseded experiments, excluded from normal test discovery |

Frozen artifacts stay at the repository root because protocol fingerprints and
provenance records were written against those paths. Moving them would break
reproducibility of already-frozen cohorts.

## Running

Scripts resolve data paths relative to the **repository root**, so run them
from there:

```bash
PYTHONPATH="$PWD:$PWD/research" python research/predeclare_practical_core_confirmation_cohort.py --help
```

Tests:

```bash
python -m unittest discover -s research -t research -v
```

CI sets `PYTHONPATH` for every workflow that reaches into this directory.

## Current state

The main line is the **192-pair untouched confirmation** of the Practical Core
against `spsurvey::grts()` and `biosurvey`. The protocol, claim guardrail, and
cohort are frozen; the run has not been executed. See
[`../docs/ACSP_PRACTICAL_CORE.md`](../docs/ACSP_PRACTICAL_CORE.md) for the
decision being tested and its claim boundary.

Do not inspect cohort outcomes and then retune. The guardrail contract sets
`no_retuning_after_outcome: true`, and every inspected cohort permanently
stops being independent confirmation data.

## Reports

- [`HIERARCHICAL_VALIDATION_REPORT.md`](HIERARCHICAL_VALIDATION_REPORT.md) — the supported 10 km regional-zone claim
- [`FINE_SCALE_LIMITS_REPORT.md`](FINE_SCALE_LIMITS_REPORT.md) — why 5 km exact-site claims are not supported
- [`RETROSPECTIVE_VALIDATION_PROTOCOL.md`](RETROSPECTIVE_VALIDATION_PROTOCOL.md) — the retrospective design
- [`METHODS_PAPER_PLAN.md`](METHODS_PAPER_PLAN.md) — manuscript plan
