"""Optional provider adapters for experimental :mod:`acsp.discovery`.

Provider modules normalize external public data into frozen local snapshots. They
are deliberately separate from the scientific discovery primitives so a provider
failure can be audited without silently changing the ecological method.
"""

from .coastal_worldcover import CoastalWorldCoverAudit, attach_worldcover_coastal_features
from .gbif import GBIFOccurrenceAudit, fetch_gbif_occurrence_evidence, match_species
from .worldcover import WORLD_COVER_2021_CLASS_NAMES, WorldCoverCropAudit, build_worldcover_2021_map_crop, worldcover_2021_map_url, worldcover_tile_id, worldcover_tile_ids_for_bounds

__all__ = [
    "GBIFOccurrenceAudit", "match_species", "fetch_gbif_occurrence_evidence",
    "WORLD_COVER_2021_CLASS_NAMES", "WorldCoverCropAudit", "worldcover_tile_id", "worldcover_tile_ids_for_bounds", "worldcover_2021_map_url", "build_worldcover_2021_map_crop",
    "CoastalWorldCoverAudit", "attach_worldcover_coastal_features",
]
