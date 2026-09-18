"""Canonical public paths for the fresh-SENTINEL prospective freeze protocol.

These paths are part of the preregistration identity. First-add immutability is
path-specific, so allowing alternate receipt filenames would permit a second
post-hoc pin. Every public provenance verifier therefore binds to these exact
repository-relative paths.
"""
from __future__ import annotations

from pathlib import Path

CANONICAL_CANDIDATE_RECEIPT_REPO_PATH = "validation/cirsium_fresh_sentinel_public_freeze_receipt_v1.json"
CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH = "validation/cirsium_fresh_sentinel_public_field_schedule_receipt_v1.json"
CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH = "validation/coverage_then_fine_structure_fresh_sentinel_field_evaluation_contract_v1.json"
CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH = "validation/cirsium_aza3_acsp_field_log_template_v1.csv"


def require_canonical_repo_path(
    path: Path,
    *,
    repo_root: Path,
    expected_repo_path: str,
    label: str,
) -> Path:
    repo = Path(repo_root).resolve()
    value = Path(path)
    value = (repo / value).resolve() if not value.is_absolute() else value.resolve()
    try:
        relative = value.relative_to(repo).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} must be inside the repository") from exc
    if relative != expected_repo_path:
        raise ValueError(f"{label} must use canonical repo path {expected_repo_path}")
    return value
