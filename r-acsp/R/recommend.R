#' Recommend top survey candidates with equal area quotas
#'
#' @param candidates A data.frame containing site identifiers and priority scores.
#' @param per_area Number of sites retained per survey area.
#' @param default_total Number retained when only one area is present.
#' @param area_col,score_col,id_col Column names.
#' @param extent Optional numeric vector ordered west, south, east, north.
#' @param latitude_col,longitude_col Coordinate column names used with extent.
#' @return A ranked data.frame.
#' @export
acsp_recommend <- function(candidates, per_area = 3L, default_total = 8L,
                           area_col = "survey_area_id",
                           score_col = "priority_score", id_col = "site_id",
                           extent = NULL, latitude_col = "latitude", longitude_col = "longitude") {
  stopifnot(is.data.frame(candidates), score_col %in% names(candidates), id_col %in% names(candidates))
  if (!is.null(extent)) {
    if (length(extent) != 4L || any(!is.finite(extent)) || extent[[1L]] >= extent[[3L]] || extent[[2L]] >= extent[[4L]]) {
      stop("extent must be finite west, south, east, north values with west < east and south < north")
    }
    stopifnot(latitude_col %in% names(candidates), longitude_col %in% names(candidates))
    inside <- candidates[[longitude_col]] >= extent[[1L]] & candidates[[longitude_col]] <= extent[[3L]] &
      candidates[[latitude_col]] >= extent[[2L]] & candidates[[latitude_col]] <= extent[[4L]]
    candidates <- candidates[!is.na(inside) & inside, , drop = FALSE]
  }
  candidates <- candidates[order(-candidates[[score_col]], candidates[[id_col]]), , drop = FALSE]
  if (area_col %in% names(candidates) && length(unique(candidates[[area_col]])) > 1L) {
    selected <- do.call(rbind, lapply(split(candidates, candidates[[area_col]]), utils::head, n = per_area))
    selected <- selected[order(selected[[area_col]], -selected[[score_col]]), , drop = FALSE]
  } else {
    selected <- utils::head(candidates, default_total)
  }
  rownames(selected) <- NULL
  selected$recommendation_rank <- seq_len(nrow(selected))
  selected
}

#' Consolidate candidate points into practical survey zones
#'
#' @param candidates A data.frame with identifiers, scores, latitude, and longitude.
#' @param merge_distance_m Maximum complete-link diameter for a zone.
#' @param area_col,score_col,id_col,latitude_col,longitude_col Column names.
#' @return A zone-level data.frame.
#' @export
acsp_zones <- function(candidates, merge_distance_m = 1000,
                       area_col = "survey_area_id", score_col = "priority_score",
                       id_col = "site_id", latitude_col = "latitude", longitude_col = "longitude") {
  needed <- c(score_col, id_col, latitude_col, longitude_col)
  if (!is.data.frame(candidates) || !all(needed %in% names(candidates))) stop("candidate zone columns are missing")
  if (!area_col %in% names(candidates)) candidates[[area_col]] <- 1L
  distance_m <- function(lat, lon, rows) {
    p1 <- lat * pi / 180; p2 <- rows[[latitude_col]] * pi / 180
    dp <- (rows[[latitude_col]] - lat) * pi / 180
    dl <- (rows[[longitude_col]] - lon) * pi / 180
    a <- sin(dp / 2)^2 + cos(p1) * cos(p2) * sin(dl / 2)^2
    2 * 6371008.8 * asin(sqrt(pmin(1, pmax(0, a))))
  }
  output <- list(); out_index <- 0L
  for (area in sort(unique(candidates[[area_col]]))) {
    group <- candidates[candidates[[area_col]] == area, , drop = FALSE]
    group <- group[order(as.character(group[[id_col]]), group[[latitude_col]], group[[longitude_col]]), , drop = FALSE]
    zones <- list()
    for (i in seq_len(nrow(group))) {
      compatible <- which(vapply(zones, function(indices) {
        max(distance_m(group[[latitude_col]][i], group[[longitude_col]][i], group[indices, , drop = FALSE])) <= merge_distance_m
      }, logical(1)))
      if (length(compatible)) zones[[compatible[[1L]]]] <- c(zones[[compatible[[1L]]]], i) else zones[[length(zones) + 1L]] <- i
    }
    for (z in seq_along(zones)) {
      members <- group[zones[[z]], , drop = FALSE]
      representative <- members[order(-members[[score_col]], as.character(members[[id_col]])), , drop = FALSE][1L, , drop = FALSE]
      radius <- max(distance_m(representative[[latitude_col]], representative[[longitude_col]], members))
      out_index <- out_index + 1L
      zone_row <- data.frame(
        zone_id = sprintf("%s-Z%03d", area, z),
        zone_score = max(members[[score_col]], na.rm = TRUE), zone_member_count = nrow(members),
        zone_radius_m = radius, representative_site_id = representative[[id_col]],
        latitude = representative[[latitude_col]], longitude = representative[[longitude_col]],
        zone_member_site_ids = paste(members[[id_col]], collapse = ";"), stringsAsFactors = FALSE
      )
      zone_row[[area_col]] <- area
      output[[out_index]] <- zone_row
    }
  }
  result <- do.call(rbind, output)
  result <- result[order(-result$zone_score, result$zone_id), , drop = FALSE]
  rownames(result) <- NULL; result$zone_rank <- seq_len(nrow(result)); result
}
