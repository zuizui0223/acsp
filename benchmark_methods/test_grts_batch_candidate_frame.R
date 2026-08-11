#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(spsurvey)
})

source("benchmark_methods/grts_batch_candidate_frame.R")

root <- tempfile("grts-batch-test-")
dir.create(root, recursive = TRUE)
input <- file.path(root, "candidates.csv")
output_a <- file.path(root, "draws-a.csv")
output_b <- file.path(root, "draws-b.csv")

n <- 24L
candidates <- data.frame(
  candidate_id = sprintf("candidate-%03d", seq_len(n)),
  latitude = 34.5 + rep(seq(0, 0.5, length.out = 6), each = 4),
  longitude = 138.9 + rep(seq(0, 0.7, length.out = 4), times = 6),
  component_local_habitat_score = seq(0.20, 0.98, length.out = n),
  candidate_type = rep(c("habitat-match", "survey-gap", "environmental-test"), length.out = n),
  stringsAsFactors = FALSE
)
write.csv(candidates, input, row.names = FALSE)

run_grts_batch(
  input = input,
  output = output_a,
  draws = 4L,
  seed_base = 20260811L,
  pair_id = 7L,
  repeat = 2L,
  k = 5L,
  replacements = 3L
)
run_grts_batch(
  input = input,
  output = output_b,
  draws = 4L,
  seed_base = 20260811L,
  pair_id = 7L,
  repeat = 2L,
  k = 5L,
  replacements = 3L
)

a <- read.csv(output_a, stringsAsFactors = FALSE, check.names = FALSE)
b <- read.csv(output_b, stringsAsFactors = FALSE, check.names = FALSE)

stopifnot(nrow(a) == 12L)
stopifnot(identical(a, b))
stopifnot(setequal(unique(a$variant), c(
  "official_grts_equal",
  "official_grts_proportional_local",
  "official_grts_proportional_local_mindis10km"
)))
stopifnot(all(a$draw_index %in% 1:4))
stopifnot(all(a$spsurvey_version == "5.6.1"))
stopifnot(all(a$outcomes_available_to_selector == FALSE))
stopifnot(all(a$base_count == 5L))
stopifnot(all(a$replacement_count == 3L))
stopifnot(all(vapply(strsplit(a$base_ids, ";", fixed = TRUE), length, integer(1)) == 5L))
stopifnot(all(vapply(strsplit(a$replacement_ids, ";", fixed = TRUE), length, integer(1)) == 3L))
stopifnot(all(a$error_message == "" | is.na(a$error_message)))

mindis <- a[a$variant == "official_grts_proportional_local_mindis10km", ]
stopifnot(all(mindis$realized_min_distance_km >= 9.9))

expected_seed <- 20260811L + 7L * 100000L + 2L * 1000L + 1L
stopifnot(all(a[a$draw_index == 1L, "seed"] == expected_seed))

cat("spsurvey_version=", as.character(packageVersion("spsurvey")), "\n", sep = "")
cat("rows=", nrow(a), "\n", sep = "")
cat("GRTS batch adapter tests passed\n")
