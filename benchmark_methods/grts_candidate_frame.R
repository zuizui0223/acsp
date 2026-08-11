#!/usr/bin/env Rscript

# Adapter for the official spsurvey::grts implementation on an ACSP finite
# candidate frame. This is a comparator, not an ACSP reimplementation of GRTS.
# Candidate IDs are preserved so selections can be evaluated against the exact
# same held-out recovery table as other decision policies.

suppressPackageStartupMessages({
  library(sf)
  library(spsurvey)
})

parse_args <- function(args) {
  out <- list(
    input = NULL,
    output = NULL,
    replacements_output = NULL,
    k = 5L,
    replacements = 0L,
    seed = 1L,
    mode = "equal",
    score_col = "component_local_habitat_score",
    mindis_km = 0,
    maxtry = 10L
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
  out$k <- as.integer(out$k)
  out$replacements <- as.integer(out$replacements)
  out$seed <- as.integer(out$seed)
  out$mindis_km <- as.numeric(out$mindis_km)
  out$maxtry <- as.integer(out$maxtry)
  out
}

candidate_id_column <- function(frame) {
  if ("candidate_id" %in% names(frame)) return("candidate_id")
  if ("site_id" %in% names(frame)) return("site_id")
  stop("candidate frame requires candidate_id or site_id")
}

finite_numeric <- function(x, name) {
  values <- suppressWarnings(as.numeric(x))
  if (any(!is.finite(values))) stop(name, " must be finite for all candidate rows")
  values
}

local_aeqd_crs <- function(latitude, longitude) {
  lat0 <- mean(latitude)
  lon0 <- mean(longitude)
  sprintf(
    "+proj=aeqd +lat_0=%.10f +lon_0=%.10f +datum=WGS84 +units=m +no_defs",
    lat0,
    lon0
  )
}

extract_original_id <- function(sites, id_col) {
  if (is.null(sites) || nrow(sites) == 0L) return(character())
  if (id_col %in% names(sites)) return(as.character(sites[[id_col]]))
  prefixed <- paste0("sframe_", id_col)
  if (prefixed %in% names(sites)) return(as.character(sites[[prefixed]]))
  stop("GRTS output did not preserve candidate identifier column ", id_col)
}

write_selection <- function(sites, frame, id_col, path, selection_type) {
  ids <- extract_original_id(sites, id_col)
  if (length(ids) == 0L) {
    empty <- frame[FALSE, , drop = FALSE]
    empty$selection_rank <- integer()
    empty$selection_type <- character()
    write.csv(empty, path, row.names = FALSE, na = "")
    return(invisible(empty))
  }
  lookup <- match(ids, as.character(frame[[id_col]]))
  if (anyNA(lookup)) stop("selected candidate IDs not found in original frame")
  selected <- frame[lookup, , drop = FALSE]
  selected$selection_rank <- seq_len(nrow(selected))
  selected$selection_type <- selection_type
  if (!is.null(sites) && "siteID" %in% names(sites)) {
    selected$grts_site_id <- as.character(sites$siteID)
  }
  if (!is.null(sites) && "replsite" %in% names(sites)) {
    selected$grts_replacement_order <- as.character(sites$replsite)
  }
  if (!is.null(sites) && "ip" %in% names(sites)) {
    selected$grts_inclusion_probability <- suppressWarnings(as.numeric(sites$ip))
  }
  write.csv(selected, path, row.names = FALSE, na = "")
  invisible(selected)
}

run_grts_candidate_frame <- function(
  input,
  output,
  replacements_output = NULL,
  k = 5L,
  replacements = 0L,
  seed = 1L,
  mode = "equal",
  score_col = "component_local_habitat_score",
  mindis_km = 0,
  maxtry = 10L
) {
  frame <- read.csv(input, stringsAsFactors = FALSE, check.names = FALSE)
  if (nrow(frame) == 0L) stop("candidate frame is empty")
  id_col <- candidate_id_column(frame)
  if (anyDuplicated(as.character(frame[[id_col]]))) stop("candidate IDs must be unique")
  frame$latitude <- finite_numeric(frame$latitude, "latitude")
  frame$longitude <- finite_numeric(frame$longitude, "longitude")
  limit <- min(as.integer(k), nrow(frame))
  if (limit < 1L) stop("k must be positive")
  replacements <- max(0L, as.integer(replacements))
  mindis_km <- max(0, as.numeric(mindis_km))
  maxtry <- max(1L, as.integer(maxtry))
  mode <- tolower(trimws(mode))
  if (!mode %in% c("equal", "proportional")) {
    stop("mode must be equal or proportional")
  }

  if (mode == "proportional") {
    if (!score_col %in% names(frame)) stop("proportional GRTS requires score column: ", score_col)
    evidence <- suppressWarnings(as.numeric(frame[[score_col]]))
    if (any(!is.finite(evidence))) stop("proportional GRTS score must be finite")
    # spsurvey requires a positive auxiliary variable. Preserve evidence order
    # while keeping zero-score candidates in the finite frame.
    frame$grts_aux_score <- pmax(evidence, 1e-6)
  }

  points <- st_as_sf(
    frame,
    coords = c("longitude", "latitude"),
    crs = 4326,
    remove = FALSE
  )
  points <- st_transform(points, crs = local_aeqd_crs(frame$latitude, frame$longitude))
  mindis_m <- if (mindis_km > 0) mindis_km * 1000 else NULL

  set.seed(as.integer(seed))
  common <- list(
    sframe = points,
    n_base = limit,
    n_over = replacements,
    mindis = mindis_m,
    maxtry = maxtry,
    projcrs_check = TRUE
  )
  if (mode == "equal") {
    design <- do.call(grts, c(common, list(seltype = "equal")))
  } else {
    design <- do.call(grts, c(common, list(
      seltype = "proportional",
      aux_var = "grts_aux_score"
    )))
  }

  selection_label <- paste0(
    "grts_", mode,
    if (mindis_km > 0) paste0("_mindis", format(mindis_km, trim = TRUE), "km") else ""
  )
  dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
  base <- write_selection(
    design$sites_base,
    frame,
    id_col,
    output,
    selection_label
  )
  if (nrow(base) != limit) {
    stop("GRTS returned ", nrow(base), " base sites; expected ", limit)
  }
  if (anyDuplicated(as.character(base[[id_col]]))) stop("GRTS base selection contains duplicate IDs")

  if (!is.null(replacements_output)) {
    dir.create(dirname(replacements_output), recursive = TRUE, showWarnings = FALSE)
    write_selection(
      design$sites_over,
      frame,
      id_col,
      replacements_output,
      paste0(selection_label, "_replacement")
    )
  }

  invisible(list(
    base = base,
    design = design,
    mode = mode,
    mindis_km = mindis_km,
    seed = as.integer(seed)
  ))
}

if (sys.nframe() == 0L) {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  if (is.null(args$input) || is.null(args$output)) {
    stop("--input and --output are required")
  }
  run_grts_candidate_frame(
    input = args$input,
    output = args$output,
    replacements_output = args$replacements_output,
    k = args$k,
    replacements = args$replacements,
    seed = args$seed,
    mode = args$mode,
    score_col = args$score_col,
    mindis_km = args$mindis_km,
    maxtry = args$maxtry
  )
}
