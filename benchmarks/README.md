# ACSP benchmark catalogue

ACSP benchmarks evaluate survey prioritization, candidate-zone construction, spatial validation, and field-recovery performance. Environmental Occupancy Geometry has moved to the standalone `zuizui0223/eog` repository and is no longer maintained or benchmarked here.

Supported ACSP benchmark entry points remain at the repository root or under `field_validation/`. Superseded experiments remain under `legacy/` for reproducibility and are excluded from normal test discovery.

## Interpretation rules

- Compare ACSP recommendations with same-pool random and simpler candidate-ranking baselines.
- Rebuild candidates from training data only during retrospective validation.
- Keep failed taxa and technical exclusions in audit outputs.
- Do not infer accessibility or detectability weights from retrospective occurrence recovery alone.
- Treat exact-site claims separately from validated regional-zone performance.
