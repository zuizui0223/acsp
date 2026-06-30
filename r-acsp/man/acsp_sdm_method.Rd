\name{acsp_sdm_method}
\alias{acsp_sdm_method}
\title{Build an SDM Method Record}
\usage{acsp_sdm_method(source_records, qc_excluded, presence_used, background,
  partition, variables, algorithms, best_model, best_auc,
  environment_source, prediction_extent, validation_caution = "")}
\arguments{
  \item{source_records, qc_excluded, presence_used, background}{Record counts.}
  \item{partition}{Result from \code{acsp_sdm_partition}.}
  \item{variables, algorithms}{Character vectors.}
  \item{best_model, best_auc}{Best individual model and validation AUC.}
  \item{environment_source, prediction_extent}{Method descriptions.}
  \item{validation_caution}{Optional AUC or partition warning.}
}
\value{A one-row data frame.}
\description{Creates a machine-readable SDM methods summary for reporting and export.}
