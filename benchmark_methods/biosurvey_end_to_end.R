#!/usr/bin/env Rscript

# End-to-end comparator for the published biosurvey planning workflow.
# This adapter deliberately starts from a geographic region and environmental
# raster stack, which is biosurvey's native problem definition. It does NOT
# force biosurvey to rank the ACSP candidate frame.

suppressPackageStartupMessages({
  library(terra)
  library(biosurvey)
})

BIOSURVEY_COMMIT <- "035fbebf3d47f823fa55b41a56a74b35dc510753"
BIOSURVEY_VERSION <- "0.1.2"

parse_args <- function(args) {
  out <- list(
    region = NULL,
    variables = NULL,
    output_dir = NULL,
    budget = 5L,
    seed = 20260811L,
    replicates = 10L,
    eg_block_grid = 10L
  )
  i <- 1L
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) stop("unexpected argument: ", key)
    if (i == length(args)) stop("missing value for ", key)
    value <- args[[i + 1L]]
    name <- gsub("-", "_", substring(key, 3L), fixed = TRUE)
    if (!name %in% names(out)) stop("unknown argument: ", key)
    out[[name]] <- value
    i <- i + 2L
  }
  out$budget <- as.integer(out$budget)
  out$seed <- as.integer(out$seed)
  out$replicates <- as.integer(out$replicates)
  out$eg_block_grid <- as.integer(out$eg_block_grid)
  out
}

assert_pinned_biosurvey <- function() {
  version <- as.character(packageVersion("biosurvey"))
  if (!identical(version, BIOSURVEY_VERSION)) {
    stop("biosurvey version mismatch: expected ", BIOSURVEY_VERSION, ", found ", version)
  }
  invisible(version)
}

selection_frame <- function(selection, slot_name) {
  sets <- selection[[slot_name]]
  if (is.null(sets) || length(sets) == 0L) {
    return(data.frame())
  }
  frame <- sets[[1]]
  if (!is.data.frame(frame)) frame <- as.data.frame(frame)
  required <- c("Longitude", "Latitude")
  if (!all(required %in% names(frame))) {
    stop(slot_name, " does not contain Longitude/Latitude")
  }
  frame
}

write_method <- function(frame, output_path, method, seed, budget, native_parameter = NA_character_) {
  if (nrow(frame) > budget) {
    stop(method, " exceeded declared budget; native output is not truncated")
  }
  out <- frame
  out$selection_rank <- seq_len(nrow(out))
  out$selection_method <- method
  out$selection_seed <- as.integer(seed)
  out$declared_budget <- as.integer(budget)
  out$native_parameter <- native_parameter
  write.csv(out, output_path, row.names = FALSE, na = "")
  invisible(out)
}

run_biosurvey_end_to_end <- function(
  region_path,
  variables_path,
  output_dir,
  budget = 5L,
  seed = 20260811L,
  replicates = 10L,
  eg_block_grid = 10L
) {
  assert_pinned_biosurvey()
  budget <- as.integer(budget)
  seed <- as.integer(seed)
  replicates <- as.integer(replicates)
  eg_block_grid <- as.integer(eg_block_grid)
  if (budget < 1L) stop("budget must be positive")
  if (replicates < 1L) stop("replicates must be positive")
  if (eg_block_grid < 2L) stop("eg_block_grid must be at least 2")

  region <- terra::vect(region_path)
  variables <- terra::rast(variables_path)
  if (terra::nlyr(variables) < 2L) stop("biosurvey environmental comparison requires at least two raster layers")
  if (terra::crs(region, proj = TRUE) == "") stop("region CRS is missing")
  if (terra::crs(variables, proj = TRUE) == "") stop("environment raster CRS is missing")

  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

  # PCA is frozen for the end-to-end comparison so uniformE and EG can operate
  # on the same two-dimensional representation even when ACSP uses >2 layers.
  master <- biosurvey::prepare_master_matrix(
    region = region,
    variables = variables,
    do_pca = TRUE,
    center = TRUE,
    scale = TRUE,
    verbose = FALSE
  )
  if (!all(c("PC1", "PC2") %in% names(master$data_matrix))) {
    stop("biosurvey PCA did not produce PC1/PC2")
  }

  geographic <- biosurvey::uniformG_selection(
    master,
    expected_points = budget,
    max_n_samplings = 1,
    replicates = replicates,
    use_preselected_sites = FALSE,
    set_seed = seed,
    verbose = FALSE
  )
  geographic_frame <- selection_frame(geographic, "selected_sites_G")
  if (nrow(geographic_frame) != budget) {
    stop("uniformG did not return exactly the declared budget")
  }

  environmental <- biosurvey::uniformE_selection(
    master,
    variable_1 = "PC1",
    variable_2 = "PC2",
    selection_from = "all_points",
    expected_points = budget,
    max_n_samplings = 1,
    replicates = replicates,
    use_preselected_sites = FALSE,
    set_seed = seed,
    verbose = FALSE
  )
  environmental_frame <- selection_frame(environmental, "selected_sites_E")
  if (nrow(environmental_frame) != budget) {
    stop("uniformE did not return exactly the declared budget")
  }

  blocks <- biosurvey::make_blocks(
    master,
    variable_1 = "PC1",
    variable_2 = "PC2",
    n_cols = eg_block_grid,
    n_rows = eg_block_grid,
    block_type = "equal_area"
  )

  # EG may place two sites in an environmental block when geographically
  # disjoint clusters are detected. Preserve this native behavior. We search
  # n_blocks only using the number of selected sites, never ecological outcomes,
  # and retain the design with the greatest site count not exceeding the budget.
  eg_candidates <- list()
  eg_audit <- data.frame(
    n_blocks = integer(),
    selected_sites = integer(),
    status = character(),
    message = character(),
    stringsAsFactors = FALSE
  )
  for (n_blocks in seq_len(budget)) {
    attempt <- tryCatch(
      biosurvey::EG_selection(
        blocks,
        n_blocks = n_blocks,
        max_n_samplings = 1,
        replicates = replicates,
        use_preselected_sites = FALSE,
        select_point = "E_centroid",
        cluster_method = "hierarchical",
        sample_for_distance = min(250L, nrow(blocks$data_matrix)),
        set_seed = seed,
        verbose = FALSE
      ),
      error = function(error) error
    )
    if (inherits(attempt, "error")) {
      eg_audit <- rbind(eg_audit, data.frame(
        n_blocks = n_blocks,
        selected_sites = NA_integer_,
        status = "error",
        message = conditionMessage(attempt),
        stringsAsFactors = FALSE
      ))
      next
    }
    frame <- selection_frame(attempt, "selected_sites_EG")
    eg_audit <- rbind(eg_audit, data.frame(
      n_blocks = n_blocks,
      selected_sites = nrow(frame),
      status = "ok",
      message = "",
      stringsAsFactors = FALSE
    ))
    if (nrow(frame) <= budget && nrow(frame) > 0L) {
      eg_candidates[[as.character(n_blocks)]] <- frame
    }
  }
  if (length(eg_candidates) == 0L) {
    stop("no native EG selection fit within the declared budget")
  }
  counts <- vapply(eg_candidates, nrow, integer(1))
  eligible_names <- names(counts)[counts == max(counts)]
  chosen_n_blocks <- max(as.integer(eligible_names))
  eg_frame <- eg_candidates[[as.character(chosen_n_blocks)]]

  g_out <- write_method(
    geographic_frame,
    file.path(output_dir, "biosurvey_uniformG.csv"),
    "biosurvey_uniformG",
    seed,
    budget
  )
  e_out <- write_method(
    environmental_frame,
    file.path(output_dir, "biosurvey_uniformE.csv"),
    "biosurvey_uniformE",
    seed,
    budget
  )
  eg_out <- write_method(
    eg_frame,
    file.path(output_dir, "biosurvey_EG.csv"),
    "biosurvey_EG",
    seed,
    budget,
    native_parameter = paste0("n_blocks=", chosen_n_blocks)
  )
  write.csv(eg_audit, file.path(output_dir, "biosurvey_EG_budget_audit.csv"), row.names = FALSE, na = "")

  manifest <- list(
    status = "complete",
    implementation = "claununez/biosurvey",
    biosurvey_version = BIOSURVEY_VERSION,
    biosurvey_commit = BIOSURVEY_COMMIT,
    declared_budget = budget,
    seed = seed,
    thinning_replicates = replicates,
    pca = list(do_pca = TRUE, center = TRUE, scale = TRUE, variables = c("PC1", "PC2")),
    uniformG_sites = nrow(g_out),
    uniformE_sites = nrow(e_out),
    EG_sites = nrow(eg_out),
    EG_chosen_n_blocks = chosen_n_blocks,
    EG_budget_rule = "largest native selected-site count <= declared budget; tie chooses larger n_blocks; never truncate native EG output",
    acsp_candidate_frame_used = FALSE,
    heldout_outcomes_used = FALSE
  )
  writeLines(jsonlite::toJSON(manifest, pretty = TRUE, auto_unbox = TRUE), file.path(output_dir, "biosurvey_manifest.json"))
  invisible(manifest)
}

if (sys.nframe() == 0L) {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  if (is.null(args$region) || is.null(args$variables) || is.null(args$output_dir)) {
    stop("--region, --variables, and --output-dir are required")
  }
  run_biosurvey_end_to_end(
    region_path = args$region,
    variables_path = args$variables,
    output_dir = args$output_dir,
    budget = args$budget,
    seed = args$seed,
    replicates = args$replicates,
    eg_block_grid = args$eg_block_grid
  )
}
