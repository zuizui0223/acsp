#' Recommend top survey candidates with equal area quotas
#'
#' @param candidates A data.frame containing site identifiers and priority scores.
#' @param per_area Number of sites retained per survey area.
#' @param default_total Number retained when only one area is present.
#' @param area_col,score_col,id_col Column names.
#' @return A ranked data.frame.
#' @export
acsp_recommend <- function(candidates, per_area = 3L, default_total = 8L,
                           area_col = "survey_area_id",
                           score_col = "priority_score", id_col = "site_id") {
  stopifnot(is.data.frame(candidates), score_col %in% names(candidates), id_col %in% names(candidates))
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
