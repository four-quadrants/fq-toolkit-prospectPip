# FQ Prospect

The Claude side of the FQ Toolkit prospect pipeline. The toolkit app (on the
analyst's Mac) reads and builds; these skills do what only Claude can:

- **fq-launchbay-pull**: "pull [client] from LaunchBay" writes the document list
  and checklist the app downloads and audits from. Needs the LaunchBay connector.
- **fq-analysis-review**: "load / pull in [client]'s analysis review". The lead
  advisor's first page: what the documents show, and the follow-up questions,
  with the client email written on the page.
- **fq-consult-review**: "load / refresh / pull in [client]'s consult review".
  The second page: the plan, recommendations, projections and slides. Pulling
  it in is what the deck is built from.

Needs, in the Claude session: the FQ_Toolkit folder and the Prospects folder on
the Analysis share connected. See the toolkit's `fq_auditor/SETUP.md`.
