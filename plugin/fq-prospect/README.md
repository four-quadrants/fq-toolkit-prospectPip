# FQ Prospect

The Claude side of the FQ Toolkit prospect pipeline. The toolkit app (on the
analyst's Mac) reads and builds; these skills do what only Claude can:

- **fq-launchbay-pull**: "pull [client] from LaunchBay" writes the document list
  and checklist the app downloads and audits from. Needs the LaunchBay connector.
- **fq-analysis-review**: the review, one page per prospect: "build / load
  [client]'s assumptions", "refresh [client]'s review with the new answers and
  documents", "pull in and build [client]'s consult deck". Assumptions, what
  the documents show, questions and client email, then the plan,
  recommendations, projections and slides, and the deck built from it.
- **fq-consult-review**: only for older clients that still have a separate
  consult review page.

Needs, in the Claude session: the FQ_Toolkit folder and the Prospects folder on
the Analysis share connected. See the toolkit's `fq_auditor/SETUP.md`.
