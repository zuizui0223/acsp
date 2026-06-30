# acsp for R

Minimal reusable methods corresponding to the ACSP Streamlit workflow.

```r
devtools::install("r-acsp")
library(acsp)

recommended <- acsp_recommend(candidates, per_area = 3)
partition <- acsp_sdm_partition(n_occurrences = 86, geographic_span_degrees = 1.8)
algorithms <- acsp_default_algorithms()
```
