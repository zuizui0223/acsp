#!/usr/bin/env Rscript

# Batch the official spsurvey::grts comparator for one frozen candidate frame.
# All draws are generated before any held-out occurrence outcome is attached.

suppressPackageStartupMessages({
  library(sf)
  library(spsurvey)
})

source("benchmark_methods/grts_candidate_frame.R")

EXPECTED_SPSURVEY_VERSION <- "5.6.1"

parse_batch_args <- function(args) {
  out <- list(
    input = NULL,
    output = NULL,
    draws = 50L,
    seed_base = 20260811L,
    pair_id = 1L,
    repeat_id = 1L,
    k = 5L,
    replacements = 3L,
    score_col = "component_local_habitat_score"
  )
  arg_names <- c(
    "--input" = "input",
    "--output" = "output",
    "--draws" = "draws",
    "--seed-base" = "seed_base",
    "--pair-id" = "pair_id",
    "--repeat" = "repeat_id",
    "--k" = "k",
    "--replacements" = "replacements",
    "--score-col" = "score_col"
  )
  i <- 1L
  while (i <= length(args)) {
    key <- args[[i]]
    if (!key %in% names(arg_names)) stop("unknown argument: ", key)
    if (i == length(args)) stop("missing value for ", key)
    value <- args[[i + 1L]]
    name <- unname(arg_names[[key]])
    out[[name]] <- value
    i <- i + 2L
  }
  for (name in c("draws", "seed_base", "pair_id", "repeat_id", "k", "replacements")) {
    out[[name]] <- as.integer(out[[name]])
  }
  out
}

pairwise_min_distance_km <- function(points, ids, id_col) {
  if (length(ids) < 2L) return(NA_real_)
  positions <- match(ids, as.character(points[[id_col]]))
  if (anyNA(positions)) return(NA_real_)
  selected <- points[positions, , drop = FALSE]
  distance <- as.matrix(sf::st_distance(selected))
  values <- distance[upper.tri(distance)]
  if (length(values) == 0L) return(NA_real_)
  min(as.numeric(values), na.rm = TRUE) / 1000
}

prepare_frame <- function(input, score_col) {
  frame <- read.csv(input, stringsAsFactors = FALSE, check.names = FALSE)
  if (nrow(frame) == 0L) stop("candidate frame is empty")
  id_col <- candidate_id_column(frame)
  if (anyDuplicated(as.character(frame[[id_col]]))) stop("candidate IDs must be unique")
  frame$latitude <- finite_numeric(frame$latitude, "latitude")
  frame$longitude <- finite_numeric(frame$longitude, "longitude")
  if (!score_col %in% names(frame)) stop("candidate frame lacks score column: ", score_col)
  evidence <- suppressWarnings(as.numeric(frame[[score_col]]))
  if (any(!is.finite(evidence))) stop("local evidence must be finite for all GRTS candidates")
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

draw_one <- function(prepared, variant, seed, k, replacements) {
  frame <- prepared$frame
  points <- prepared$points
  id_col <- prepared$id_col
  mindis_km <- if (variant == "official_grts_proportional_local_mindis10km") 10 else 0
  maxtry <- if (mindis_km > 0) 20L else 10L
  mode <- if (variant == "official_grts_equal") "equal" else "proportional"
  warnings <- character()
  error_message <- ""
  design <- tryCatch(
    withCallingHandlers({
      set.seed(as.integer(seed))
      common <- list(
        sframe = points,
        n_base = min(as.integer(k), nrow(frame)),
        n_over = max(0L, as.integer(replacements)),
        mindis = if (mindis_km > 0) mindis_km * 1000 else NULL,
        maxtry = maxtry,
        projcrs_check = TRUE
      )
      if (mode == "equal") {
        do.call(spsurvey::grts, c(common, list(seltype = "equal")))
      } else {
        do.call(spsurvey::grts, c(common, list(
          seltype = "proportional",
          aux_var = "grts_aux_score"
        )))
      }
    }, warning = function(w) {
      warnings <<- c(warnings, conditionMessage(w))
      invokeRestart("muffleWarning")
    }),
    error = function(e) {
      error_message <<- paste0(class(e)[1], ": ", conditionMessage(e))
      NULL
    }
  )

  if (is.null(design)) {
    return(data.frame(
      variant = variant,
      seed = as.integer(seed),
      base_count = 0L,
      base_ids = "",
      replacement_count = 0L,
      replacement_ids = "",
      realized_min_distance_km = NA_real_,
      warning_message = paste(unique(warnings), collapse = " | "),
      error_message = error_message,
      stringsAsFactors = FALSE
    ))
  }

  base_ids <- extract_original_id(design$sites_base, id_col)
  replacement_ids <- extract_original_id(design$sites_over, id_col)
  data.frame(
    variant = variant,
    seed = as.integer(seed),
    base_count = length(base_ids),
    base_ids = paste(base_ids, collapse = ";"),
    replacement_count = length(replacement_ids),
    replacement_ids = paste(replacement_ids, collapse = ";"),
    realized_min_distance_km = pairwise_min_distance_km(points, base_ids, id_col),
    warning_message = paste(unique(warnings), collapse = " | "),
    error_message = error_message,
    stringsAsFactors = FALSE
  )
}

run_grts_batch <- function(
  input,
  output,
  draws = 50L,
  seed_base = 20260811L,
  pair_id = 1L,
  repeat_id = 1L,
  k = 5L,
  replacements = 3L,
  score_col = "component_local_habitat_score"
) {
  actual_version <- as.character(utils::packageVersion("spsurvey"))
  if (!identical(actual_version, EXPECTED_SPSURVEY_VERSION)) {
    stop("spsurvey version mismatch: expected ", EXPECTED_SPSURVEY_VERSION, ", got ", actual_version)
  }
  prepared <- prepare_frame(input, score_col)
  variants <- c(
    "official_grts_equal",
    "official_grts_proportional_local",
    "official_grts_proportional_local_mindis10km"
  )
  rows <- list()
  index <- 1L
  for (variant in variants) {
    for (draw_index in seq_len(as.integer(draws))) {
      seed <- as.integer(seed_base) + as.integer(pair_id) * 100000L +
        as.integer(repeat_id) * 1000L + as.integer(draw_index)
      row <- draw_one(prepared, variant, seed, k, replacements)
      row$draw_index <- as.integer(draw_index)
      row$pair_id <- as.integer(pair_id)
      row[["repeat"]] <- as.integer(repeat_id)
      row$requested_k <- as.integer(k)
      row$requested_replacements <- as.integer(replacements)
      row$spsurvey_version <- actual_version
      row$outcomes_available_to_selector <- FALSE
      rows[[index]] <- row
      index <- index + 1L
    }
  }
  result <- do.call(rbind, rows)
  result <- result[, c(
    "pair_id", "repeat", "variant", "draw_index", "seed",
    "requested_k", "base_count", "base_ids",
    "requested_replacements", "replacement_count", "replacement_ids",
    "realized_min_distance_km", "warning_message", "error_message",
    "spsurvey_version", "outcomes_available_to_selector"
  )]
  dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
  write.csv(result, output, row.names = FALSE, na = "")
  invisible(result)
}

if (sys.nframe() == 0L) {
  args <- parse_batch_args(commandArgs(trailingOnly = TRUE))
  if (is.null(args$input) || is.null(args$output)) stop("--input and --output are required")
  run_grts_batch(
    input = args$input,
    output = args$output,
    draws = args$draws,
    seed_base = args$seed_base,
    pair_id = args$pair_id,
    repeat_id = args$repeat_id,
    k = args$k,
    replacements = args$replacements,
    score_col = args$score_col
  )
}
