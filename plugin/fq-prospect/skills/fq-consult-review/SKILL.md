---
name: fq-consult-review
description: "Older Four Quadrants prospects that still have a separate CONSULT REVIEW page. Use only when someone names a consult review page that already exists for a client. For everything else (loading, refreshing, pulling in a review, building the consult deck) use fq-analysis-review, which now covers the whole review on one page."
---

# Consult review (older pages)

The analysis and consult reviews are now one page per prospect, covered by
the fq-analysis-review skill. Follow that skill for loading, refreshing with
answers, pulling in and building the deck.

A client made before the change may have a separate consult review page
(`"consult"` in `_Audit/review_pages.json`). Keep working that page: seed it
with `--mode consult`; on it the analysis review's notes and questions sit on
their section of the Assumptions tab (carried over with the client's answer,
Claude's verdict and his marks). Everything else, including judging answers
and building the deck, is as in fq-analysis-review.
