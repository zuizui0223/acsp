\name{acsp_zones}
\alias{acsp_zones}
\title{Consolidate candidate points into practical survey zones}
\usage{acsp_zones(candidates, merge_distance_m = 1000,
  area_col = "survey_area_id", score_col = "priority_score",
  id_col = "site_id", latitude_col = "latitude", longitude_col = "longitude")}
\arguments{
\item{candidates}{A data frame with identifiers, scores, latitude, and longitude.}
\item{merge_distance_m}{Maximum complete-link diameter for a zone.}
\item{area_col,score_col,id_col,latitude_col,longitude_col}{Column names.}
}
\value{A zone-level data frame.}
\description{Uses a deterministic complete-link rule so nearby candidate points become one practical visit without single-link chaining.}
