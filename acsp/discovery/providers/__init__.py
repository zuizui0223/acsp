"""Optional provider adapters for experimental :mod:`acsp.discovery`.

Provider modules normalize external public data into frozen local snapshots. They
are deliberately separate from the scientific discovery primitives so a provider
failure can be audited without silently changing the ecological method.
"""


from importlib import import_module

# Preserve the public interface without loading unrelated experimental modules.
_EXPORT_MODULES = {
    "coastal_worldcover": "CoastalWorldCoverAudit WorldCoverComponentAudit attach_worldcover_coastal_features attach_worldcover_component_ids".split(),
    "gbif": "GBIFOccurrenceAudit fetch_gbif_occurrence_evidence match_species".split(),
    "worldcover": "WORLD_COVER_2021_CLASS_NAMES WorldCoverCropAudit build_worldcover_2021_map_crop worldcover_2021_map_url worldcover_tile_id worldcover_tile_ids_for_bounds".split(),
    "worldcover_points": "WorldCoverPointSampleAudit retain_worldcover_land_points".split(),
}
_LAZY_EXPORTS = {name: module for module, names in _EXPORT_MODULES.items() for name in names}


def __getattr__(name):
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "GBIFOccurrenceAudit",
    "match_species",
    "fetch_gbif_occurrence_evidence",
    "WORLD_COVER_2021_CLASS_NAMES",
    "WorldCoverCropAudit",
    "worldcover_tile_id",
    "worldcover_tile_ids_for_bounds",
    "worldcover_2021_map_url",
    "build_worldcover_2021_map_crop",
    "WorldCoverPointSampleAudit",
    "retain_worldcover_land_points",
    "WorldCoverComponentAudit",
    "attach_worldcover_component_ids",
    "CoastalWorldCoverAudit",
    "attach_worldcover_coastal_features",
]
