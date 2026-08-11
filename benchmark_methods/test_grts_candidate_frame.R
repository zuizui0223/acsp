#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(spsurvey)
})

source("benchmark_methods/grts_candidate_frame.R")

root <- tempfile("grts-candidate-test-")
dir.create(root, recursive = TRUE)
input <- file.path(root, "candidates.csv")

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

run_one <- function(mode, seed, prefix, mindis_km = 0) {
  base <- file.path(root, paste0(prefix, "-base.csv"))
  over <- file.path(root, paste0(prefix, "-over.csv"))
  run_grts_candidate_frame(
    input = input,
    output = base,
    replacements_output = over,
    k = 5L,
    replacements = 3L,
    seed = seed,
    mode = mode,
    score_col = "component_local_habitat_score",
    mindis_km = mindis_km,
    maxtry = 20L
  )
  list(
    base = read.csv(base, stringsAsFactors = FALSE),
    over = read.csv(over, stringsAsFactors = FALSE)
  )
}

check_selection <- function(result, expected_type) {
  stopifnot(nrow(result$base) == 5L)
  stopifnot(length(unique(result$base$candidate_id)) == 5L)
  stopifnot(all(result$base$candidate_id %in% candidates$candidate_id))
  stopifnot(identical(result$base$selection_rank, 1:5))
  stopifnot(all(result$base$selection_type == expected_type))

  stopifnot(nrow(result$over) == 3L)
  stopifnot(length(unique(result$over$candidate_id)) == 3L)
  stopifnot(all(result$over$candidate_id %in% candidates$candidate_id))
  stopifnot(length(intersect(result$base$candidate_id, result$over$candidate_id)) == 0L)
}

minimum_pair_distance_km <- function(frame) {
  xy <- st_as_sf(frame, coords = c("longitude", "latitude"), crs = 4326, remove = FALSE)
  xy <- st_transform(xy, crs = local_aeqd_crs(frame$latitude, frame$longitude))
  distances <- units::drop_units(st_distance(xy)) / 1000
  diag(distances) <- Inf
  min(distances)
}

equal_a <- run_one("equal", 20260811L, "equal-a")
equal_b <- run_one("equal", 20260811L, "equal-b")
proportional_a <- run_one("proportional", 20260811L, "proportional-a")
proportional_b <- run_one("proportional", 20260811L, "proportional-b")
proportional_10_a <- run_one("proportional", 20260811L, "proportional-10-a", mindis_km = 10)
proportional_10_b <- run_one("proportional", 20260811L, "proportional-10-b", mindis_km = 10)

check_selection(equal_a, "grts_equal")
check_selection(proportional_a, "grts_proportional")
check_selection(proportional_10_a, "grts_proportional_mindis10km")

# Same frame + same R seed must reproduce base and replacement choices.
stopifnot(identical(equal_a$base$candidate_id, equal_b$base$candidate_id))
stopifnot(identical(equal_a$over$candidate_id, equal_b$over$candidate_id))
stopifnot(identical(proportional_a$base$candidate_id, proportional_b$base$candidate_id))
stopifnot(identical(proportional_a$over$candidate_id, proportional_b$over$candidate_id))
stopifnot(identical(proportional_10_a$base$candidate_id, proportional_10_b$base$candidate_id))
stopifnot(identical(proportional_10_a$over$candidate_id, proportional_10_b$over$candidate_id))

# The synthetic frame can satisfy the 10-km base-site requirement. This checks
# that we are actually exercising the official minimum-distance path.
stopifnot(minimum_pair_distance_km(proportional_10_a$base) >= 9.999)

# Proportional GRTS keeps local evidence as a probabilistic inclusion driver,
# rather than converting it into deterministic top-score ranking.
stopifnot("component_local_habitat_score" %in% names(proportional_a$base))
stopifnot("component_local_habitat_score" %in% names(proportional_10_a$base))

cat("spsurvey_version=", as.character(packageVersion("spsurvey")), "\n", sep = "")
cat("sf_version=", as.character(packageVersion("sf")), "\n", sep = "")
cat("equal_ids=", paste(equal_a$base$candidate_id, collapse = ";"), "\n", sep = "")
cat("proportional_ids=", paste(proportional_a$base$candidate_id, collapse = ";"), "\n", sep = "")
cat("proportional_mindis10_ids=", paste(proportional_10_a$base$candidate_id, collapse = ";"), "\n", sep = "")
cat("GRTS adapter tests passed\n")
