\name{acsp_sdm_partition}
\alias{acsp_sdm_partition}
\title{Choose an SDM Validation Design}
\usage{acsp_sdm_partition(n_occurrences, geographic_span_degrees = NA_real_)}
\arguments{
  \item{n_occurrences}{Number of presence records.}
  \item{geographic_span_degrees}{Minimum longitude/latitude extent span.}
}
\value{A list containing \code{method} and \code{reason}.}
\description{Chooses jackknife, random holdout, random k-fold, or spatial block validation from sample size and spread.}
