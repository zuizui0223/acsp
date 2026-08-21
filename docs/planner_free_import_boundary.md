# Planner-free validated package import boundary

The validated candidate-patch API is required to remain independent from the historical ranked-planner stack at import time as well as at execution time.

The package root therefore resolves public compatibility exports lazily. Importing `acsp`, `validated_robust_candidate_patches`, or `discover_validated_candidate_patches` must not import `acsp.planning`. Historical planner names such as `integrated_candidate_scores` remain available from the package root and load `acsp.planning` only when explicitly requested.

This is an architectural dependency boundary only. It does not change the frozen 2.5% robust-support rule, 1 km patch aggregation, candidate membership, confirmation statistics, or validated claim.
