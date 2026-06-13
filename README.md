# ACSP — Adaptive Complementarity-based Survey Prioritization

Interactive Streamlit app for building field survey planning maps from GBIF occurrence data, with ACSP (Adaptive Complementarity-based Survey Prioritization) candidate-set selection.

## Features

- Upload a GBIF occurrence CSV, or search GBIF by scientific name.
- Auto-detect coordinate columns such as `decimalLatitude` and `decimalLongitude`.
- Detect optional `eventDate`, `year`, and `species` / `scientificName` columns.
- Display occurrences on a Folium map.
- Draw occurrence buffers.
- Cluster occurrences with DBSCAN using meter-based distance thresholds.
- Generate one candidate survey site per cluster.
- Draw candidate routes and straight-line distance labels.
- Export a standalone HTML map.
- Export candidate survey sites as CSV.
- Generate Google Maps links for candidate sites and route handoff.

## Local install

```bash
python -m pip install -r requirements.txt
```

## Run locally

```bash
python -m streamlit run gbif_fieldmap_builder_app.py
```

## Deploy on Streamlit Community Cloud

Use:

- Repository: `zuizui0223/gbif-fieldmap-builder`
- Branch: `main`
- Main file path: `gbif_fieldmap_builder_app.py`

## Notes

Distances shown on the map are straight-line distances. Google Maps links are provided for real-world route planning.
