# E8 execution is intentionally blocked

The scientific endpoint and recovery code are frozen before the v3 balance result.

The execution template contains no cohort artifact identity and is **not executable**.

Activation requires a separate immutable receipt created only if:

- v3 cohort status = cohort_frozen_balance_passed;
- exactly 48 unique taxa / 24 matched pairs / 12 regions;
- cohort outcome_opened = false;
- cohort ACSP candidate_generation_run = false.

That later receipt may fill only:

- workflow run ID;
- artifact ID;
- artifact digest;
- cohort file SHA-256;
- exact source commit/ref.

It may not change any scientific parameter or inference threshold.
