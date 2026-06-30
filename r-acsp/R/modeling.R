#' Default ACSP SDM ensemble algorithms
#'
#' @return A character vector of algorithm labels shared with the Python package.
#' @export
acsp_default_algorithms <- function() {
  c("Logistic regression", "Random forest", "ExtraTrees", "Gradient boosting")
}
