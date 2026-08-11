#!/usr/bin/env Rscript

# Frozen official GRTS primary comparator for the rescue development gate.
# The input CSV is pre-outcome and contains only candidate IDs, coordinates,
# candidate type, and local evidence. Non-finite local evidence is retained as
# zero evidence, then mapped to the positive 1e-6 auxiliary floor.

suppressPackageStartupMessages({
  library(sf)
  library(spsurvey)
})

source("benchmark_methods/grts_batch_candidate_frame.R")

EXPECTED_SPSURVEY_VERSION <- "5.6.1"
EXPECTED_SPSURVEY_COMMIT <- "0914fcd071713fdab19f43d8d9a66436830bd917"
PRIMARY_VARIANT <- "official_grts_proportional_local_mindis10km"

parse_rescue_args <- function(args) {
  out <- list(
    input = NULL,
    output = NULL,
    draws = 50L,
    seed_base = 20260811L,
    global_pair_id = 1L,
    repeat = 1L,
    k = 5L,
    replacements = 3L,
    score_col = "component_local_habitat_score"
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
  for (name in c("draws", "seed_base", "global_pair_id", "repeat", "k", "replacements")) {
    out[[name]] <- as.integer(out[[name]])
  }
  out
}

prepare_rescue_grts_frame <- function(input, score_col) {
  frame <- read.csv(input, stringsAsFactors = FALSE, check.names = FALSE)
  if (nrow(frame) == 0L) stop("candidate frame is empty")
  id_col <- candidate_id_column(frame)
  if (anyDuplicated(as.character(frame[[id_col]]))) stop("candidate IDs must be unique")
  frame$latitude <- finite_numeric(frame$latitude, "latitude")
  frame$longitude <- finite_numeric(frame$longitude, "longitude")
  if (!score_col %in% names(frame)) stop("candidate frame lacks score column: ", score_col)
  evidence <- suppressWarnings(as.numeric(frame[[score_col]]))
  evidence[!is.finite(evidence)] <- 0
  frame$grts_aux_score <- pmax(evidence, 1e-6)
  points <- sf::st_as_sf(
    frame,
    coords = c("longitude", "latitude"),
    crs = 4326,
    remove = FALSE
  )
  points <- sf::st_transform(points, crs = local_aeqd_crs(frame$latitude, frame$longitude))
  list(frame = frame, points = points, id_col = id_col)
}

run_rescue_primary_batch <- function(
  input,
  output,
  draws = 50L,
  seed_base = 20260811L,
  global_pair_id = 1L,
  repeat = 1L,
  k = 5L,
  replacements = 3L,
  score_col = "component_local_habitat_score"
) {
  actual_version <- as.character(utils::packageVersion("spsurvey"))
  if (!identical(actual_version, EXPECTED_SPSURVEY_VERSION)) {
    stop("spsurvey version mismatch: expected ", EXPECTED_SPSURVEY_VERSION, ", got ", actual_version)
  }
  prepared <- prepare_rescue_grts_frame(input, score_col)
  rows <- vector("list", as.integer(draws))
  for (draw_index in seq_len(as.integer(draws))) {
    seed <- as.integer(seed_base) + as.integer(global_pair_id) * 100000L +
      as.integer(repeat) * 1000L + as.integer(draw_index)
    row <- draw_one(
      prepared,
      PRIMARY_VARIANT,
      seed,
      as.integer(k),
      as.integer(replacements)
    )
    row$draw_index <- as.integer(draw_index)
    row$global_pair_id <- as.integer(global_pair_id)
    row$repeat <- as.integer(repeat)
    row$requested_k <- as.integer(k)
    row$requested_replacements <- as.integer(replacements)
    row$spsurvey_version <- actual_version
    row$spsurvey_tag_commit <- EXPECTED_SPSURVEY_COMMIT
    row$outcomes_available_to_selector <- FALSE
    row$missing_local_evidence_rule <- "nonfinite_to_zero_then_pmax_1e-6"
    rows[[draw_index]] <- row
  }
  result <- do.call(rbind, rows)
  result <- result[, c(
    "global_pair_id", "repeat", "variant", "draw_index", "seed",
    "requested_k", "base_count", "base_ids",
    "requested_replacements", "replacement_count", "replacement_ids",
    "realized_min_distance_km", "warning_message", "error_message",
    "spsurvey_version", "spsurvey_tag_commit",
    "outcomes_available_to_selector", "missing_local_evidence_rule"
  )]
  dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
  write.csv(result, output, row.names = FALSE, na = "")
  invisible(result)
}

if (sys.nframe() == 0L) {
  args <- parse_rescue_args(commandArgs(trailingOnly = TRUE))
  if (is.null(args$input) || is.null(args$output)) stop("--input and --output are required")
  run_rescue_primary_batch(
    input = args$input,
    output = args$output,
    draws = args$draws,
    seed_base = args$seed_base,
    global_pair_id = args$global_pair_id,
    repeat = args$repeat,
    k = args$k,
    replacements = args$replacements,
    score_col = args$score_col
  )
}
