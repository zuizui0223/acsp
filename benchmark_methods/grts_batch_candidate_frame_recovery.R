#!/usr/bin/env Rscript

# QA-only batch adapter for frozen Practical Core GRTS recovery.
# This preserves the predeclared official spsurvey::grts contract while avoiding
# the R reserved-word parser bug in the original batch adapter.

suppressPackageStartupMessages({
  library(sf)
  library(spsurvey)
})

source("benchmark_methods/grts_candidate_frame.R")

EXPECTED_SPSURVEY_VERSION <- "5.6.1"

prepare_recovery_frame <- function(input, score_col) {
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
  points <- sf::st_as_sf(frame, coords = c("longitude", "latitude"), crs = 4326, remove = FALSE)
  points <- sf::st_transform(points, crs = local_aeqd_crs(frame$latitude, frame$longitude))
  list(frame = frame, points = points, id_col = id_col)
}

min_distance_km_recovery <- function(points, ids, id_col) {
  if (length(ids) < 2L) return(NA_real_)
  positions <- match(ids, as.character(points[[id_col]]))
  if (anyNA(positions)) return(NA_real_)
  distance <- as.matrix(sf::st_distance(points[positions, , drop = FALSE]))
  values <- distance[upper.tri(distance)]
  if (length(values) == 0L) return(NA_real_)
  min(as.numeric(values), na.rm = TRUE) / 1000
}

draw_one_recovery <- function(prepared, variant, seed, k, replacements) {
  frame <- prepared$frame
  points <- prepared$points
  id_col <- prepared$id_col
  mindis_km <- if (variant == "official_grts_proportional_local_mindis10km") 10 else 0
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
        maxtry = if (mindis_km > 0) 20L else 10L,
        projcrs_check = TRUE
      )
      if (mode == "equal") {
        do.call(spsurvey::grts, c(common, list(seltype = "equal")))
      } else {
        do.call(spsurvey::grts, c(common, list(seltype = "proportional", aux_var = "grts_aux_score")))
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
      variant = variant, seed = as.integer(seed), base_count = 0L, base_ids = "",
      replacement_count = 0L, replacement_ids = "", realized_min_distance_km = NA_real_,
      warning_message = paste(unique(warnings), collapse = " | "), error_message = error_message,
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
    realized_min_distance_km = min_distance_km_recovery(points, base_ids, id_col),
    warning_message = paste(unique(warnings), collapse = " | "),
    error_message = error_message,
    stringsAsFactors = FALSE
  )
}

run_grts_batch_recovery <- function(input, output, draws = 50L, seed_base = 20260811L,
                                    pair_id = 1L, repeat_id = 1L, k = 5L,
                                    replacements = 3L,
                                    score_col = "component_local_habitat_score") {
  actual_version <- as.character(utils::packageVersion("spsurvey"))
  if (!identical(actual_version, EXPECTED_SPSURVEY_VERSION)) {
    stop("spsurvey version mismatch: expected ", EXPECTED_SPSURVEY_VERSION, ", got ", actual_version)
  }
  prepared <- prepare_recovery_frame(input, score_col)
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
      row <- draw_one_recovery(prepared, variant, seed, k, replacements)
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
    "pair_id", "repeat", "variant", "draw_index", "seed", "requested_k", "base_count",
    "base_ids", "requested_replacements", "replacement_count", "replacement_ids",
    "realized_min_distance_km", "warning_message", "error_message", "spsurvey_version",
    "outcomes_available_to_selector"
  )]
  dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
  write.csv(result, output, row.names = FALSE, na = "")
  invisible(result)
}
