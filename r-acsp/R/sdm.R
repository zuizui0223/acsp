#' Choose an SDM spatial validation design
#'
#' @param n_occurrences Number of presence records.
#' @param geographic_span_degrees Minimum longitude/latitude extent span.
#' @return A list containing method and reason.
#' @export
acsp_sdm_partition <- function(n_occurrences, geographic_span_degrees = NA_real_) {
  n <- as.integer(n_occurrences)
  span <- as.numeric(geographic_span_degrees)
  if (n < 15L) return(list(method = "jackknife", reason = sprintf("Jackknife was selected because only %d presence records were available.", n)))
  if (n < 30L || (!is.na(span) && span < 2)) return(list(method = "random holdout", reason = sprintf("Random 75/25 holdout was selected for %d records because spatial folds could be empty.", n)))
  if (n < 50L) return(list(method = "random k-fold", reason = sprintf("Random five-fold cross-validation was selected for %d records.", n)))
  list(method = "block", reason = sprintf("Four-quadrant spatial block cross-validation was selected for %d records to test geographic transferability.", n))
}

#' Build a manuscript-ready SDM method record
#'
#' @param source_records,qc_excluded,presence_used,background Integer counts.
#' @param partition A result from acsp_sdm_partition().
#' @param variables,algorithms Character vectors.
#' @param best_model Best individual model name.
#' @param best_auc Best validation AUC.
#' @param environment_source,prediction_extent Descriptions.
#' @return A one-row data.frame.
#' @export
acsp_sdm_method <- function(source_records, qc_excluded, presence_used, background,
                            partition, variables, algorithms, best_model, best_auc,
                            environment_source, prediction_extent,
                            validation_caution = "") {
  data.frame(
    source_occurrence_records = source_records,
    qc_excluded_records = qc_excluded,
    presence_records_used = presence_used,
    background_points = background,
    partition_method = partition$method,
    partition_reason = partition$reason,
    environment_variables = paste(variables, collapse = ", "),
    environment_source = environment_source,
    prediction_extent = prediction_extent,
    ensemble_method = "equal-weight mean predicted probability",
    ensemble_algorithms = paste(algorithms, collapse = ", "),
    best_individual_model = best_model,
    best_individual_auc = best_auc,
    validation_caution = validation_caution,
    stringsAsFactors = FALSE
  )
}
