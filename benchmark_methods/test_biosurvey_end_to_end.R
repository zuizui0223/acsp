#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(terra)
  library(biosurvey)
})

source("benchmark_methods/biosurvey_end_to_end.R")

stopifnot(as.character(packageVersion("biosurvey")) == "0.1.2")

root <- tempfile("biosurvey-end-to-end-")
dir.create(root, recursive = TRUE)
region_path <- file.path(root, "region.gpkg")
variables_path <- file.path(root, "environment.tif")
output_dir <- file.path(root, "output")

region <- terra::vect(
  matrix(c(
    138.8, 34.4,
    139.8, 34.4,
    139.8, 35.4,
    138.8, 35.4,
    138.8, 34.4
  ), ncol = 2, byrow = TRUE),
  type = "polygons",
  crs = "EPSG:4326"
)
terra::writeVector(region, region_path, overwrite = TRUE)

base <- terra::rast(
  xmin = 138.8, xmax = 139.8,
  ymin = 34.4, ymax = 35.4,
  resolution = 0.025,
  crs = "EPSG:4326"
)
xy <- terra::xyFromCell(base, seq_len(terra::ncell(base)))
variables <- c(base, base, base, base, base)
values(variables[[1]]) <- xy[, 2]
values(variables[[2]]) <- xy[, 1]
values(variables[[3]]) <- sin(xy[, 1] * 8) + cos(xy[, 2] * 5)
values(variables[[4]]) <- (xy[, 1] - 139.3)^2 + (xy[, 2] - 34.9)^2
values(variables[[5]]) <- xy[, 1] * xy[, 2]
names(variables) <- c("bio1", "bio5", "bio6", "bio12", "bio15")
terra::writeRaster(variables, variables_path, overwrite = TRUE)

manifest <- run_biosurvey_end_to_end(
  region_path = region_path,
  variables_path = variables_path,
  output_dir = output_dir,
  budget = 5L,
  seed = 20260811L,
  replicates = 3L,
  eg_block_grid = 6L
)

stopifnot(manifest$status == "complete")
stopifnot(manifest$biosurvey_version == "0.1.2")
stopifnot(manifest$biosurvey_commit == "035fbebf3d47f823fa55b41a56a74b35dc510753")
stopifnot(manifest$declared_budget == 5L)
stopifnot(manifest$uniformG_sites == 5L)
stopifnot(manifest$uniformE_sites == 5L)
stopifnot(manifest$uniformE_native_function_called == TRUE)
stopifnot(grepl("data.frame-to-SpatVector-PC1-PC2", manifest$uniformE_compatibility_shim, fixed = TRUE))
stopifnot(manifest$EG_sites >= 1L)
stopifnot(manifest$EG_sites <= 5L)
stopifnot(manifest$acsp_candidate_frame_used == FALSE)
stopifnot(manifest$heldout_outcomes_used == FALSE)

for (file in c("biosurvey_uniformG.csv", "biosurvey_uniformE.csv", "biosurvey_EG.csv")) {
  selected <- read.csv(file.path(output_dir, file), stringsAsFactors = FALSE)
  stopifnot(nrow(selected) >= 1L)
  stopifnot(nrow(selected) <= 5L)
  stopifnot(all(is.finite(selected$Longitude)))
  stopifnot(all(is.finite(selected$Latitude)))
  stopifnot(identical(selected$selection_rank, seq_len(nrow(selected))))
}

audit <- read.csv(file.path(output_dir, "biosurvey_EG_budget_audit.csv"), stringsAsFactors = FALSE)
stopifnot(nrow(audit) == 5L)
stopifnot(any(audit$status == "ok"))

cat("biosurvey_version=", as.character(packageVersion("biosurvey")), "\n", sep = "")
cat("biosurvey_commit=035fbebf3d47f823fa55b41a56a74b35dc510753\n")
cat("uniformE_compatibility_shim=", manifest$uniformE_compatibility_shim, "\n", sep = "")
cat("uniformG_sites=", manifest$uniformG_sites, "\n", sep = "")
cat("uniformE_sites=", manifest$uniformE_sites, "\n", sep = "")
cat("EG_sites=", manifest$EG_sites, "\n", sep = "")
cat("biosurvey end-to-end adapter tests passed\n")
