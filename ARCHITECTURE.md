# FQ Intake Tools — architecture

*Written 2026-08-19. Captures decisions made and options still open, so the design
does not live in a chat log.*

---

## 0. Correction (2026-08-21) — the lanes are not what section 1 says

Section 1 below describes the auditor working on originals and filing *those*.
That is wrong. The actual intent:

```
client documents
   └─> Original_sourcedocs/     flat, untouched, never sorted — record only
   └─> redact ─> redacted set   THE WORKING SET
                    ├─> filed into Personal/ and Business/
                    └─> fed to every analysis program built next
                        (statement analysis, credit reports, financial deep dive)
```

**The redactor is not a last step before sending something out. It is the front
door.** Everything downstream consumes redacted files, which changes what
redaction is for: it must remove *identity* while preserving *financial
substance*.

| must be removed | must survive |
|---|---|
| SSN, EIN, full account numbers | account **last four** |
| card numbers, routing numbers | balances, transaction amounts |
| addresses | dates, payees, institution names, account type |

Two consequences measured on this corpus, both now fixed:

**Redaction destroys the text layer.** Originals need OCR on 198 of 773 pages
(25%); the redacted set needs it on **781 of 781 (100%)**, because every page is
rebuilt as a flat image. So the export resolution sets a ceiling on the accuracy
of every later program. It was the review canvas at `SCALE = 2` (~144 dpi);
`EXPORT_SCALE` is now 3 (~216 dpi), re-rendered from the source file rather than
copied off the review canvas.

**The account number was being lost entirely.** On a Fidelity 529 the original
reads `Primary Account 4417208899 3021/S`. Cena matched the whole thing as one
token, so the keep-the-last-four rule preserved `7555` — the last four of the
*adjacent* fragment — and blacked out `4417208899` including the `0605` that
filing and analysis need. Whitespace-separated groups are now only treated as one
number when they read as grouped formatting (`1234 5678 9012 3456`); a group of
six or more digits is an account number in its own right.

**Decided 2026-08-25 — filing MOVES the redacted copies** out of the staging batch
into `Personal/` and `Business/`. Safe because `Original_sourcedocs/` is never
touched, so the archive is always intact. The rename log records every destination
keyed by content hash, so a misfiled document can be found without hunting for it.

**Still open:** whether the auditor should classify from the originals even though
it files the redacted copies. Classification agrees 16/16 on the redacted files
tested, but the redacted set costs 4x the OCR, loses 25–30% of the text on tax
returns, and can lose the account tail. Reading originals for metadata and filing
redacted copies would avoid all three. Not decided.

---

## 1. The two lanes

The clarifying decision: **the redactor is not a filing step. It is the airlock on
the way out.**

### Lane A — local, full PII

```
client documents  →  audit  →  file into Personal/ and Business/
```

Originals, complete, never leaves the machine. The auditor may read full PII
because it runs as local Python on your Mac: no network calls, no cloud service,
no upload. The residual risk is a compromised workstation, which is the same risk
the documents already carry sitting in a folder.

**This is the working client file.** Analysts need whole documents — full account
numbers to match statements to accounts, complete tax returns to trace figures.

### Lane B — export, de-identified

```
originals  →  Cena redacts  →  residual-PII check  →  safe to leave the machine
```

This is what exists so data can be analysed elsewhere — Claude, or any cloud
tool, or anything you don't fully control. Redaction is the price of admission
for leaving the machine.

Worth noting: cloud is not the only option for the analysis Lane B enables. Local
models and local scripts can do a lot of it without anything leaving at all. Lane
B is about *permitting* outside processing, not requiring it.

### What this changes

The auditor's residual-PII scan is not a quality report. **It is the gate on Lane
B.** Nothing should leave on Lane B that the scan has flagged. That deserves to be
enforced in code, not remembered by a human — Cena already does this for the
client email, refusing to write the file if a PII pattern appears in it, and the
same pattern applies to a batch export.

---

## 2. Two PII detectors, and why that is correct

There are two independent implementations:

| | Cena (`Cena_5.html`) | Auditor (`detectors.py`) |
|---|---|---|
| Language | JavaScript | Python, 267 lines |
| Card numbers | Luhn **plus issuer BIN** | none at all |
| ZIP+4 | explicitly excluded | not handled |
| Label proximity | shape-checked, 300-char window | `_keyword_near`, width 300 |
| Table noise | dot-leader heuristic | `_looks_like_table_noise` |
| Page escalation | none | promotes IDs on a page with a confirmed hit |
| Cross-page dedupe | none | merges, keeps best-evidenced sighting |

None of the fixes made on 2026-08-19 exist in the Python.

**Do not unify them.** The instinct is to share one rule set, but if both tools
apply identical rules the auditor can never catch a redactor blind spot — they
would share the blind spot and the audit becomes tautological. Two independent
implementations genuinely cross-check each other. That is not a theory: it is how
the Form 511 dependent SSNs and the "Code Number" EIN were found at all. The
Python auditor caught what the JavaScript redactor missed.

**What is actually wrong today** is that they diverge *by accident* and nothing
tracks how. The fix is a shared **test corpus and expectations file**, not shared
code: a list of documents and what each tool should find in them, so a divergence
shows up as a diff instead of a surprise. When they disagree, that disagreement is
the signal — one of them is wrong, and finding out which is the work.

---

## 3. Auditor front end — options

The auditor currently runs as `Run Intake Auditor.command`: double-click, drag a
folder in, get a Word report. The question is what it should become.

### Constraint that shapes everything

**A browser page cannot reorganise files on disk.** Cena works in a browser
because it only needs to *read* files you drop in and *download* results. Filing
needs to create folders and place files in specific locations.

The File System Access API (`showDirectoryPicker`) can grant a page write access
to a chosen directory — but I could not verify whether it is available from a
`file://` page in your Chrome, because the extension I have cannot see `file://`
tabs. **Treat this as unverified.** It is worth a two-minute check before betting
on any browser-based filing design: open `Cena_5.html`, and in the console run
`typeof window.showDirectoryPicker`. If that prints `"undefined"`, browser-based
filing is off the table.

### Option 1 — single-file HTML, like Cena

*Same pattern that already works.*

- **For:** one file, no install, fully offline, same review UX as the redactor, and
  the CSP guarantee is legible to anyone who opens it.
- **Against:** OCR in the browser is materially worse than native tesseract — we
  spent a session proving that. Filing depends on the unverified API above. No
  Word output without a library. A 137-page credit report in a browser tab is slow.
- **Fits:** review and triage. Not filing, not heavy OCR.

### Option 2 — keep the `.command` launcher

*Already built, already working, already scored.*

- **For:** native tesseract (the good OCR), real file operations, Word output,
  parallel per-page processing, no browser limits. Reproduces the scorecard today.
- **Against:** no interface. Output is a document you read after the fact — you
  cannot see *why* something was classified, or correct it in place. Every
  correction is a re-run.
- **Fits:** the engine. Poor as the only surface.

### Option 3 — Python engine, HTML report *(recommended)*

*Python does the work; the browser shows the result.*

The `.command` runs the audit and writes a self-contained HTML report you open in
a browser. File operations, OCR and classification stay in Python. Review,
filtering, sorting and drill-down happen in a real interface.

- **For:** each half does what it is good at. Native OCR quality. Real file moves.
  A reviewable interface without depending on an unverified browser API. The HTML
  is a single file, so it travels and archives like any other deliverable — and
  you already have `Checklist_Parse_Review_1.html`, so this pattern is proven here.
- **Against:** two artefacts instead of one. The report is a snapshot, so acting on
  a correction means a re-run — unless the report writes a small decisions file
  that the next run reads, which is the natural next step.
- **Fits:** everything the auditor actually does.

### Option 4 — local web app

*Python serves a real UI on localhost.*

- **For:** genuinely interactive. Approve a filing plan and watch it execute. No
  re-runs.
- **Against:** a server to start and stop, a port, a process that can be left
  running. `localhost` is a network surface, however local — which cuts against
  the offline guarantee that makes Lane A defensible. Much more to build and
  maintain.
- **Fits:** later, if reviewing turns out to be the bottleneck. Not first.

### Recommendation

**Option 3.** It preserves the OCR quality you need, keeps file operations in the
only place that can perform them, and gives you a review surface — without betting
on a browser API I could not verify. Option 4 remains available if the
snapshot-and-re-run cycle becomes the constraint.

---

## 4. Filing — open questions

Decided: the tree holds **originals** (Lane A). Auto-create account subfolders
from detected accounts. Anything questionable goes to its own review folder rather
than being guessed at.

Still to settle:

- **Copy or move?** Copying cannot lose a document to a classification bug, at the
  cost of two sets on disk and ambiguity about which is authoritative. Moving is
  cleaner but a misfile means hunting. A dry-run plan you approve, then execute,
  gets most of both.
- **Naming.** Does filing rename documents to a convention, or preserve incoming
  names? The corpus already shows why this matters: four files whose contents
  contradict their filenames.
- **The review folder's name**, and whether it is one folder or mirrors the tree.
- **Idempotency.** Running the auditor twice must not duplicate or re-file. Content
  hashing already exists in `extract.py` and can serve here.
- **Output location.** The auditor currently writes its report *into the folder it
  audited*, which pollutes the input and would be re-audited next run. Make the
  output path an argument.

---

## 5. Principles worth keeping

- **Written to disk beats held in a session.** This project survived a Cowork
  crash because the work was in files. Keep it that way.
- **Independent checks beat shared code.** Section 2.
- **A silent miss is worse than a noisy one.** Cena now warns when a page is
  captioned for an identifier it could not read, rather than passing it as clean.
- **Instrument before theorising.** Three attempts at the W-2 bug failed while
  reasoning from a sandbox. Adding `cenaTrace()` found it immediately — twice the
  real cause was environmental (CSP blocking the OCR engine, wrong DPI estimate),
  which no amount of reading the detector code would have revealed.
- **Measure over-redaction, not just under-redaction.** The card-number bug put
  104 boxes over client transaction data and no one had noticed.
