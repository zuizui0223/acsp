# Untouched SDM Top-k comparator cohort

This directory freezes the taxon-region cohort sampled on 2026-08-08 for the direct fitted-SDM Top-5 versus ACSP benchmark.

The cohort was selected only after the complete comparison protocol had been frozen in `validation/sdm_topk_protocol.json`. The sampling workflow did not fetch focal occurrence rows for model fitting, build ACSP candidates, fit an SDM, or calculate held-out recovery.

Audit summary:

- 24 declared taxon-region pairs;
- 12 plant and 12 animal pairs;
- six pairs in each broad geographic stratum;
- 131 unique previously used taxa excluded from six development, confirmation, Izu, and earlier SDM benchmark sample files;
- zero overlap with excluded taxa;
- zero duplicate selected taxa;
- protocol fingerprint `cea7ba04d53d6af7be5d642746539e46ff924435fd683aa43479ea5a38022652`;
- workflow run `31235966440`;
- downloaded artifact SHA-256 `90ef782c436d1891edc58d05d1a4e34fbee1fe03ba4c0fdbcae25f978db43b34`.

The selected scientific names and their regions must not be replaced after later model failures or unfavorable results. The benchmark-level failure rules in the frozen protocol determine how such failures contribute to inference.
