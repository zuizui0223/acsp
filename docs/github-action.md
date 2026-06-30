# Run ACSP as a GitHub Action

ACSP can run without the Streamlit interface when you already have a candidate CSV. The Action ranks candidates by `priority_score`, applies an equal quota across multiple `survey_area_id` values, and writes a selected-candidate CSV plus a JSON summary.

## Required CSV columns

- `site_id`: stable candidate identifier used to break equal-score ties
- `priority_score`: numeric priority score, larger values selected first

`survey_area_id` is optional. When more than one non-empty area is present, the Action selects the top `per-area` rows within every area. Otherwise it selects the top `default-total` rows overall.

## Use in another repository

```yaml
- name: Run ACSP
  id: acsp
  uses: zuizui0223/acsp@main
  with:
    candidates-csv: data/candidates.csv
    output-csv: outputs/acsp-recommended.csv
    summary-json: outputs/acsp-summary.json
    per-area: "3"
    default-total: "8"
```

The Action exposes these outputs:

- `recommended-csv`: selected-candidate CSV path
- `summary-json`: run-summary JSON path
- `selected-count`: number of selected candidates

Use `examples/github-action-workflow.yml` as a complete workflow template. In this repository, open the **Actions** tab and run **Run ACSP recommendation** to execute `.github/workflows/run-acsp.yml`; it uses `examples/acsp-candidates.csv` unless another repository-relative CSV path is supplied.

## Column-name overrides

Pass `area-column`, `score-column`, or `site-column` when your candidate table uses different names.
