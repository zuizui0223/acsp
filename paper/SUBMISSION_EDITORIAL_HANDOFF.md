# ACSP Ecological Informatics editorial handoff — 2026-10-25

**Status: draft submission materials produced; NOT submitted and NOT author-approved.**
The current authoritative scientific manuscript remains
[`MANUSCRIPT_ROBUST_PATCH_DRAFT.md`](MANUSCRIPT_ROBUST_PATCH_DRAFT.md), which
was **not edited** by this editorial package. Earlier Top-5 manuscripts,
frozen validation cohorts, algorithm parameters, transfer STOP results and
the exploratory Cirsium field-design branch are unchanged.

## What can be handed off now

| File | Purpose | Status |
|---|---|---|
| `SUBMISSION_HIGHLIGHTS.md` | Five result-focused candidate Highlights, all ≤85 characters | Draft; convert to an editable source file if the journal requires it |
| `SUBMISSION_ABSTRACT_SHORT.md` | Optional shorter (~200-word) abstract retaining both positive and failed gates | Draft alternative; it does not replace the current manuscript's ~325-word abstract |
| `SUBMISSION_COVER_LETTER_DRAFT.md` | One-page-scale manuscript introduction and relevance to the journal | Draft; internal note/signature require removal/completion |
| `validate_submission_packet.py` | Network-free highlights/abstract/cover claim and length preflight | Development check; no author declarations are fabricated |
| `validate_submission_alignment.py` | Existing frozen manuscript/tables/algorithm contract guard | Must continue to pass independently |

## Source of truth and claim ceiling

- Main manuscript: fixed Japanese 12-region frame, 96 taxon–region pairs,
  480 declared folds, frozen 2.5% float32 leave-one-prototype-out tier,
  1-km same-area complete-link non-ranked candidate patches.
- Primary 10-km regional retrospective endpoint: lift over same-size random
  patch sets **+0.0855870810**, pair-bootstrap 95% CI
  **[+0.0511862963, +0.1216509694]**; sign-flip p **3.33322e-5**.
- Reserved 24-taxon country-framed replication: failed uncertainty gate.
  Fresh 48-taxon confirmation: 34/48 temporally evaluable, failed 0.75 gate.
  Later observability activation: provider stopped before held-out evaluation
  after 29 HTTP 429 errors among 3,161 historical queries.
- The paper does **not** show calibrated occurrence probability, exact-site
  occupancy, survey time savings, universal geographic transfer, or general
  superiority over SDM, GRTS, or biosurvey.
- The separate September standalone global command has a bounded
  adapter confirmation. It must not be silently rewritten into this already
  frozen August manuscript's worldwide superiority or global-product claim.

## Publisher information checked (not a journal-specific guarantee)

- Elsevier's general Highlights guidance, last updated 2026-06-01,
  recommends **3–5**, each **≤85 characters**, generally as a separate
  editable file. Some journals require Highlights, others do not:
  https://www.elsevier.support/publishing/answer/how-do-i-include-highlights-with-my-manuscript
- Elsevier's general Cover Letter guidance, last updated 2026-05-18,
  recommends a focused letter ideally **under one page**, discussing aim,
  findings, novelty and journal fit; funding and author declarations are
  normally separate:
  https://www.elsevier.support/publishing/answer/what-should-be-included-in-a-cover-letter
- The official Elsevier scope describes *Ecological Informatics* as covering
  computational ecology, ecological data science and uncertainty analysis:
  https://shop.elsevier.com/journals/ecological-informatics/1574-9541
- The journal-specific ScienceDirect Guide for Authors could not be read
  programmatically (HTTP 403). Therefore the short abstract's 250-word
  **working editorial target** is **not asserted as a journal limit**.
  Article type, abstract maximum, Highlights requirement, declarations,
  graphical-abstract requirement, anonymization and file types must be
  checked on the live journal submission page before author submission.

## 2026-10-26 GBIF source-record citation audit

The new [original-input provenance note](GBIF_CITATION_AND_INPUT_PROVENANCE.md)
and offline `audit_gbif_citation_provenance.py` establish a more precise
gap than the former generic citation TODO:

- The frozen **96-pair / 480-fold** primary input was obtained through
  **GBIF Occurrence Search API**, which did not assign a download DOI.
- The original converter carried `gbifID` into temporary cleaned rows
  but **did not carry `datasetKey`**.
- GitHub Actions uploaded the fold export status and derived result files,
  **not the underlying original train/held-out occurrence CSV files**.
- The authentic original GBIF record-ID set or a verified matching GBIF
  dataset/download DOI has **not** been recovered from the checked
  public repository. A new download cannot retroactively stand in
  for those historical records.
- The manuscript's Data and code availability paragraph has been
  corrected to reflect this boundary without changing the ecological
  result or any fixed method constants.

```bash
python paper/audit_gbif_citation_provenance.py
python -m unittest discover -s tests -p 'test_gbif_citation_provenance.py' -v
```

These tests can pass while `journal_submission_ready=false`; they
verify truthful reporting, **not the creation of a DOI or exact historical
input archive**. Recover an authenticated original fold archive, if
available, before any GBIF-derived-dataset citation is claimed.

## Editorial blocks that cannot be filled from current records

1. **Authors and signoff:** Full author roster/order, corresponding author's
   institution and email, journal article type, co-author approval, CRediT
   roles and conflict-of-interest declaration are not established by the
   frozen repository. Do not infer these from commits or `CITATION.cff`,
   which lists only the collective `ACSP Developers`.
2. **Immutable software citation:** The queried public GitHub releases
   collection was empty (2026-10-25); there is no verified immutable
   journal-release DOI to insert. Request an owner-approved release and
   archive and verify the actual DOI before replacing the manuscript text.
3. **Occurrence/data citations:** Resolve the exact frozen GBIF downloads
   and dataset DOIs to the source SHA/run/artifact manifests; do not invent
   one aggregated GBIF DOI or claim every snapshot is archived outside GitHub.
4. **Formatting and bibliography:** Check the specific Guide for Authors,
   finalize manuscript type, references/DOIs, file export, citations, section
   order and whether a graph abstract is requested. Current References have
   seven entries and may need fuller scholarly context; this is editorial,
   not permission to change validation claims.
5. **Final author review:** Read the entire manuscript, short abstract,
   Highlights, letter and tables together; remove internal notes; affirm
   originality, overlap/concurrent-submission status and necessary disclosures
   separately before any actual submission.

## Mechanical verification

```bash
python paper/validate_submission_alignment.py
python paper/validate_submission_packet.py
python -m unittest discover -s tests -p 'test_submission_packet.py' -v
```

The editorial validator explicitly reports `author_submission_ready=false`;
passing tests means only that the *draft* is internally consistent with the
frozen scientific table and standard editorial bounds. It does not certify
author declarations, complete journal-specific compliance or publication.
