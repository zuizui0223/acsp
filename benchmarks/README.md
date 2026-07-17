# Benchmark catalogue

The benchmark entry points remain at the repository root for backward compatibility with existing workflows. This catalogue distinguishes supported analyses from exploratory or legacy scripts without moving files and breaking reproducibility.

## Environmental occupancy geometry

| Script | Purpose | Status |
|---|---|---|
| `benchmark_occupancy_topology_discrimination.py` | Controlled synthetic tests of fragmentation and path tortuosity | manuscript core |
| `benchmark_random_taxa_occupancy_geometry_v2.py` | Frozen random taxon-region thinning benchmark | supported |
| `finalize_occupancy_geometry_confirmation.py` | Applies predeclared confirmation gates | supported |
| `benchmark_random_taxa_occupancy_geometry_direct.py` | Direct CHELSA coordinate confirmation | manuscript core |
| `benchmark_occupancy_geometry_comparators.py` | Descriptive comparison with PCA, covariance volume, K-means, centroid, and nearest occurrence | manuscript core |
| `benchmark_occupancy_geometry_incremental_information.py` | Exploratory incremental-information analysis | exploratory; small cohort |
| `benchmark_random_taxa_occupancy_geometry.py` | Shared lower-level benchmark utilities | internal support |
| `run_random_taxa_occupancy_geometry.py` | Convenience runner | internal support |

## Interpretation rules

- Synthetic discrimination and direct CHELSA confirmation are the strongest current evidence.
- Comparator results are descriptive and must not be presented as a universal ranking of methods.
- Incremental-information results are exploratory because the evaluable cohort is small.
- Campanula is excluded from the general-method validation and should be introduced only as a later independent case study.
- Workflow artifacts, frozen pair declarations, failure records, and seeds must be retained for manuscript analyses.

## Planned structural cleanup

After the manuscript analysis interface is frozen, benchmark scripts may be moved into a Python package or `benchmarks/eog/` directory in a dedicated compatibility PR. They are intentionally not moved in this documentation-only cleanup because current GitHub Actions and external command references use the root paths.
