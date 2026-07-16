import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from acsp.chelsa_sampling import sample_chelsa_at_coordinates


def test_samples_local_rasters_directly(tmp_path):
    sources = {}
    transform = from_origin(138.0, 36.0, 1.0, 1.0)
    for index, variable in enumerate(("bio1", "bio4", "bio12", "bio15"), start=1):
        path = tmp_path / f"{variable}.tif"
        data = np.array([[index, index + 1], [index + 2, index + 3]], dtype="float32")
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=2,
            width=2,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=-9999.0,
        ) as dataset:
            dataset.write(data, 1)
        sources[variable] = str(path)

    points = pd.DataFrame({"latitude": [35.5, 34.5], "longitude": [138.5, 139.5]})
    result = sample_chelsa_at_coordinates(points, sources=sources)
    assert result.complete_indices.tolist() == [0, 1]
    assert result.frame.loc[0, "bio1"] == 1.0
    assert result.frame.loc[1, "bio15"] == 7.0


def test_outside_raster_becomes_incomplete(tmp_path):
    sources = {}
    for variable in ("bio1", "bio4", "bio12", "bio15"):
        path = tmp_path / f"{variable}.tif"
        with rasterio.open(
            path, "w", driver="GTiff", height=1, width=1, count=1,
            dtype="float32", crs="EPSG:4326", transform=from_origin(0, 1, 1, 1), nodata=-9999.0,
        ) as dataset:
            dataset.write(np.array([[1.0]], dtype="float32"), 1)
        sources[variable] = str(path)
    points = pd.DataFrame({"latitude": [50.0], "longitude": [150.0]})
    result = sample_chelsa_at_coordinates(points, sources=sources)
    assert result.complete_indices.size == 0
