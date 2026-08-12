#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(spsurvey)
})

source("benchmark_methods/grts_rescue_primary_batch_v2.R")

make_frame <- function(n) {
  data.frame(
    candidate_id = sprintf("candidate-%02d", seq_len(n)),
    candidate_type = rep("Habitat-match", n),
    latitude = 34.0 + seq_len(n) * 0.20,
    longitude = 137.0 + seq_len(n) * 0.20,
    component_local_habitat_score = seq(1.0, 0.2, length.out = n),
    stringsAsFactors = FALSE
  )
}

check_sparse_frame <- function(n, expected_base, expected_over) {
  input <- tempfile(fileext = ".csv")
  output <- tempfile(fileext = ".csv")
  write.csv(make_frame(n), input, row.names = FALSE)
  run_rescue_primary_batch_v2(
    input = input,
    output = output,
    draws = 2L,
    seed_base = 20260811L,
    global_pair_id = 999L,
    repeat_id = n,
    k = 5L,
    replacements = 3L,
    score_col = "component_local_habitat_score"
  )
  result <- read.csv(output, stringsAsFactors = FALSE, check.names = FALSE)
  stopifnot(nrow(result) == 2L)
  stopifnot(all(result$candidate_frame_rows == n))
  stopifnot(all(result$requested_replacements == 3L))
  stopifnot(all(result$effective_replacements == expected_over))
  stopifnot(all(result$base_count == expected_base))
  stopifnot(all(result$error_message == "" | is.na(result$error_message)))
  stopifnot(all(result$outcomes_available_to_selector %in% c(FALSE, "FALSE")))
  invisible(result)
}

check_sparse_frame(4L, 4L, 0L)
check_sparse_frame(5L, 5L, 0L)
check_sparse_frame(7L, 5L, 2L)
check_sparse_frame(8L, 5L, 3L)

cat("Corrected GRTS sparse-frame replacement tests passed\n")
