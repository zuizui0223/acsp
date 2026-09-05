"""Optional provider adapters for experimental :mod:`acsp.discovery`.

Provider modules normalize external public data into frozen local snapshots. They
are deliberately separate from the scientific discovery primitives so a provider
failure can be audited without silently changing the ecological method.
"""

from .worldcover import (
    WORLD_COVER_2021_CLASS_NAMES,
    WorldCoverCropAudit,
    build_worldcover_2021_map_crop,
    worldcover_2021_map_url,
    worldcover_tile_id,
    worldcover_tile_ids_for_bounds,
)

__all__ = [
    "WORLD_COVER_2021_CLASS_NAMES",
    "WorldCoverCropAudit",
    "worldcover_tile_id",
    "worldcover_tile_ids_for_bounds",
    "worldcover_2021_map_url",
    "build_worldcover_2021_map_crop",
]
