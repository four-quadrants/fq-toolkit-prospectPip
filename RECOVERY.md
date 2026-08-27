# RECOVERY — where everything lives

---

## PICK UP HERE (2026-08-19)

Shell is back, which made it possible to test the detectors against the real
cached OCR text in bulk instead of one page at a time in a browser console.

**Auditor: verified end-to-end.** Fresh sandbox, four installs
(`pip install pymupdf pytesseract pillow python-docx --break-system-packages`),
full run over all 95 originals off `.cache_originals` — reproduces the scorecard
exactly: 8 satisfied · 3 mismatched · 5 missing · 68 unexpected · 8 series gaps ·
59 files with PII.

**Two redactor bugs found and fixed today** (details in section 2c/2d):

1. **Over-redaction: 104 false credit-card hits, corpus-wide.** Luhn checksum
   alone, no issuer prefix. Every one was a bank-statement trace number. Fixed —
   now 0.
2. **Under-redaction: the W-2 SSN miss is an OCR settings problem, not a
   detector problem.** Fixed with a conditional second pass.

**Three more bugs found from the "partial box on Copy 2" report** (section 2e):

3. **My own 300-char window was a regression.** It accepted any nine digits near
   an SSN caption — on a W-2 that means the ZIP+4 and the wage figures. That was
   the partial box: it was landing on the wrong number. Replaced with a
   shape-checked `labeledSsn()`.
4. **The EIN vanished on re-detect.** `reprocessAll()` never called
   `addIdRunBoxes`, so every bare 9-digit ID disappeared the moment any toggle
   fired. First pass found them; the re-detect path silently dropped them.
5. **ZIP+4 was being flagged as a 9-digit ID** on every document with an address.

**Browser-verified 2026-08-19.** Tested in-app across payroll summary, two W-2s,
a bank statement, a brokerage statement and a tax return. SSN and EIN detected;
the wages over-redaction gone. Reported as solid.

Remaining browser checks if you want belt-and-braces:

- Open `Cena_5.html#selftest` — should be **26/26**.
- Load `Daniel W2 2025.pdf`, OCR it. **Box (a) SSN and box (b) EIN should both now
  box** via caption-anchored region OCR (section 2f). Watch the status line for
  "Re-reading form layout…" then "Reading form fields…" — the second and third
  stages firing.
- Confirm a bank statement no longer shows ~20 spurious card-number boxes, and
  that ZIP codes are no longer boxed as IDs.

---

## PICK UP HERE (2026-08-18, end of session)

**Done today:** found Cena_5 (it was in `~/Downloads` among 20 superseded
copies), moved it here, fixed the Form 511 dependent-SSN leak, added a
self-test (13/13) and a console diagnostic. Page 26 of the 2023 individual
return now catches all three SSNs — confirmed by eye.

**Open, in order:**

1. **A W-2 SSN is still missed — OCR garble.** Diagnostic is built and waiting.
   Open `Cena_5.html`, load the W-2, OCR the page, then run `cenaDiag()` in the
   browser console (Cmd+Option+J). It prints ID-shaped runs containing letters,
   with every digit masked as `#`, and a `caught` column. Rows marked **NO** are
   what's slipping through; the letters in those shapes are the substitutions
   `ocrNorm` needs to fold.

   *Prime suspect, found while building the diagnostic:* `ocrNorm`'s own comment
   (line ~718) documents the fold set as "O/0, I/l/1, S/5, B/8, G/6, **Z/2**",
   but the code maps `Z` to **1**, lumped in with `I` and `l`:
   `.replace(/[IlZz]/g,'1')`. `Z` resembles `2`, not `1`. Comment and code
   disagree, so one is wrong. Not changed yet — a fold mapping touches every
   detector, so confirm with `cenaDiag()` output first.

   Other confusions absent from the fold set entirely: `A`/4, `T`/7, `D`/0,
   `E`/3, `q`/9, `|`/1, `/`/1.

2. **Regression check** — run a P&L and a paystub, confirm the widened separator
   didn't introduce false positives. (Note: paystubs legitimately carry an SSN,
   so a hit there is probably correct.)
3. **Package both tools as standalone** — see section 7.
4. Then the "Code Number" EIN question, and the remaining 77 un-OCR'd files.

---

*Written 2026-08-18, after a Cowork session loss. This file exists so that no part
of this project depends on a conversation surviving. If you are picking this up
cold, read this first, then `fq_auditor/RESUME_HERE.md`.*

---

## The two apps

This project is **two separate tools** that are easy to confuse:

| | **Cena** (formerly Redactor) | **FQ Intake Auditor** |
|---|---|---|
| What | Removes PII from client documents | Checks a client folder against a checklist |
| Form | Single-file HTML, runs in browser | Python package, runs on your Mac |
| Where | `Cena_5.html` (see below) | `fq_auditor/` |
| Relationship | Produces the redacted batch | Audits the redacted batch, incl. residual PII |

The auditor is **downstream** of the redactor. It is how you found the Form 511 leak.

---

## 1. Cena — Local PII Scrubber

**Latest version: `Cena_5.html`, 2,404 lines.**

Originally named "Redactor," renamed to "Cena" partway through. There are 21
iterations in `~/Downloads`: `Redactor.html` through `Redactor_14.html`, then
`Cena.html` through `Cena_5.html`. **Cena_5 is the newest** — verified by
monotonic line-count growth across the whole chain and by function-set
containment (every function in Redactor_14 exists in Cena_5, plus five more).

Ignore the other 20. They are superseded.

### What it does

Single-file, fully offline PII scrubber. Hard `Content-Security-Policy` with
`connect-src 'none'` — the page physically cannot make a network call. Every
library is inlined as a `<script>` block, zero external `src=` references:
pdf.js (worker inlined via blob URL), pdf-lib, JSZip, SheetJS, Tesseract
(incl. `tess-core` and `tess-worker`). The CSP carries `'unsafe-eval'`, which
the Tesseract WASM core requires.

- **Input** — drag-and-drop or folder-drop, multi-file batch, recursive.
  PDF, images (png/jpg/webp/gif/bmp), CSV, DOCX, XLSX/XLSM/XLS.
- **Detectors** (`DETECTOR_META`, 9 toggles) — SSN (validated area/group/serial),
  full account numbers, physical addresses, card numbers (Luhn), bank routing
  numbers (ABA checksum + prefix), EIN, dates of birth (label-anchored), phone,
  email. First six default on; DOB/phone/email default off. Plus custom keywords
  and custom regex. Every match carries high/medium confidence and a masked preview.
- **Account nuance** — `classifyAccountToken` sorts findings into `full` /
  `last4` / `masked`; only `full` gets redacted, so last-four references survive.
  `ACCOUNT_TYPES` infers HSA / 401(k) / IRA / MM / CD / checking / savings /
  brokerage / credit card from surrounding text.
- **OCR** — pages with no text layer are detected (`pageNeedsOcr`) and run through
  bundled Tesseract. Detection is OCR-tolerant: `ocrNorm` folds O/0, I/l/1, S/5,
  B/8, G/6, Z/2.
- **Review** — matches map to pixel boxes over a rendered canvas
  (`boxesForMatch`). Every box is reviewable in a sidebar; uncheck any, draw
  manual boxes, draw **keep regions** that protect content (`applyKeeps`,
  `isKeep`), rotate pages, or flag a whole document "no redaction / safe file"
  to pass it through byte-identical.
- **Output** — black rectangles painted onto canvas, canvas re-embedded as JPEG
  into a **new** PDF (`buildRedactedBytes`). The original text layer is
  destroyed, not covered — this is true redaction. CSV → redacted CSV.
  XLSX → redacted workbook (cells `[redacted]`, headers preserved, column-level).
  Plus a per-document plain-text log and a batch ZIP with a combined log.

### What Cena added over Redactor_14

1. `ssnLikeRuns` — dedicated SSN-shaped-run scanner with a ZIP+4 false-positive
   guard (skips `##-####` tails preceded by a digit, so `12345-6789` isn't an SSN)
2. `addIdRunBoxes` — folds nine-digit-run, SSN-run, and labeled-account
   heuristics into page box generation, with de-duplication
3. `pagesNeedingOcr` / `ocrAllPages` — batch "OCR every scanned page" button
   (Redactor_14 was page-by-page only)
4. `clusterRecs` (Cena_4+) — union-find spatial clustering, groups nearby boxes
   in the review sidebar so related fields read as one item
5. `.grid > * { min-width: 0 }` (Cena_5 only) — layout overflow fix

---

## 2. Oklahoma Form 511 dependent SSNs — FIXED 2026-08-18

**Status: fixed in `Cena_5.html` (in this folder). Needs confirmation against the
real Form 511 page before you trust it on client files.**

### The actual root cause — narrower than first thought

The primary SSN detector was:

```js
var re=/\b(\d{3})[-.\s](\d{2})[-.\s](\d{4})\b/g
```

`[-.\s]` matches **exactly one** separator character. Spaces were already allowed;
what was not allowed was a *run* of them. Boxed form fields render as
`412   55   8830`, so the detector fell through. A one-character-class bug, not a
missing feature.

### What changed

1. **Separator widened** to `([-.]|[ \t]{1,6})`. Horizontal whitespace only — a
   newline join would let the last figure on one line marry the first on the next,
   which is precisely the wage-column mistake `nineDigitRuns` exists to avoid.
2. **Space-separated matches are gated** on `bearsSsnContext()` (page shows a
   dashed SSN, SSN wording, or tax-form markers: Form 511/1040/1099/W-2,
   Schedule 511, dependents, filing status, exemptions) and rejected by
   `looksLikeFigures()` when adjacent to currency or decimals. They score
   `medium`; dashed matches keep `high`.

   **Note the near-miss here.** The first version of `looksLikeFigures` tested
   the preceding characters against `/[$,.]\s?$/`. A sentence ending in `". "`
   matches that, so any SSN following the end of a sentence was thrown away as
   "figures" — including the `…Dependents. 412 55 8830` layout this whole fix
   targets. The self-test caught it; a casual eyeball on the app would not have.
   The guard now requires a **digit** before the separator (`1,234`, `12.34`) or
   a literal `$`, so currency columns are still blocked but sentence punctuation
   is not mistaken for arithmetic.
3. **`ssnBoxedRuns()`** added and wired into `addIdRunBoxes`, so scanned/OCR pages
   generate boxes for the same 3-2-4 boxed shape.
4. **`SSN_LABEL` widened** to cover `Your…`, `Spouse's…`, `Dependent's…`, and
   `Social Security Number of Dependent` — the Form 511 / Schedule 511-1 wording.
5. **`labeledDigits` takes an optional window** (default 45, SSN now passes 300)
   and widens the tolerated inter-group gap from 3 to 8 in wide mode, because on
   a boxed grid OCR puts the caption far from its value.

**`nineDigitRuns` was deliberately left alone.** Its refusal to join
space-separated groups protects wage columns across every P&L and paystub. The
fix is targeted at the exact 3-2-4 shape instead of relaxing the general rule.

### Verifying

Open `Cena_5.html#selftest` in a browser — 13 assertions run against the real
detector functions (not copies) and print a pass/fail table as a full-screen
overlay. Six are guards that must *not* fire: wage columns, currency columns,
newline joins, invalid area/group numbers, ZIP+4.

**Currently 13/13.** Results also go to the browser console. If the overlay
doesn't appear, open the console and call `cenaSelfTest()` directly — it's global.

The self-test is inert without the `#selftest` hash. It runs on `window.load`
with a short delay, because the app's own init repaints the body and would
otherwise cover the results.

**Still to do:** run the real Form 511 page through the app and confirm all three
SSNs (taxpayer, spouse, dependent) are now boxed, then re-run a P&L and a paystub
to confirm no new false positives.

---

## 2c. Over-redaction — 104 false card numbers (FIXED 2026-08-19)

**This is the "don't redact account values and transactions" failure.**

The card detector accepted any 13–19 digit run that passed a Luhn checksum. Luhn
passes roughly **one in ten** random digit strings, and a practice bank statement
is full of long numeric trace and reference strings.

Measured across all 95 documents:

| | |
|---|---|
| Luhn-valid "card numbers" found | **104** |
| ...with a valid issuer BIN + length | **0** |
| ...with card wording within 70 chars | **0** |

Every single one was a false positive — 61 of them 15-digit numbers beginning
`58`, a systematic reference format on the practice statements; 18 were 19-digit
beginning `10`; 14 were 14-digit beginning `20`.

**Fix:** added `cardBrand()` — issuer BIN paired with the lengths each issuer
actually uses (Visa, Mastercard, Amex, Discover, Diners, JCB). A Luhn pass now
only says "this could be a checksum"; the prefix says "this is a card". Matches
with no valid prefix are kept **only** if card wording sits nearby, which covers
a real card whose leading digits OCR mangled — that fallback fires zero times on
this corpus, so it costs nothing.

Corpus-wide card findings after the fix: **0**. No real cards were lost, because
there were none.

---

## 2d. Under-redaction on W-2s — an OCR problem, not a detector problem (FIXED 2026-08-19)

The missed W-2 SSN was not a fold-set gap. **OCR never read the digits at all.**

Cached extraction of `Daniel W2 2025.pdf` shows box (a) coming through as
`sii ila` and `[Ss` — no `###-##-####` anywhere in the page text. No text-based
detector can find a number that was never transcribed. `Sara W2 2024.pdf` is the
same (401 characters of text for an entire W-2).

Re-OCR-ing the page directly settles it:

| render | page-seg mode | SSN-shaped matches |
|---|---|---|
| 150 dpi | PSM 6 | 1 |
| 300 dpi | PSM 6 | 3 |
| any | PSM 3 (the default) | 0 |

Cena renders at `SCALE = 2` (~144 dpi) and never sets a page-segmentation mode,
so tesseract.js uses **PSM 3 (auto)** — exactly the mode that fails on a boxed
form.

**Fix — a conditional second pass, not a global default change.** Switching
everything to PSM 6 would risk multi-column bank statements, so instead:

1. Pass 1 runs as before (PSM 3).
2. If the page text contains an identifier caption (SSN / EIN / account number)
   but no identifier was detected, re-run that page at PSM 6 and keep the second
   result **only if it actually finds one**.
3. If both passes fail, set `pg.idWarning` — logged to the console and written
   into the redaction log under **"NEEDS A HUMAN LOOK"**, listing the pages where
   a caption was seen but no number could be read.

Step 3 is the important one. It converts a silent miss into a visible one.

---

## 2e. The "partial box on Copy 2" report — three more bugs (FIXED 2026-08-19)

Reproduced by re-OCR-ing `Daniel W2 2025.pdf` locally, rebuilding Cena's token
stream exactly as the app does, and running the real detector module over it.
What the detector was actually matching on that page:

```
ssn "#####-####"     <- a ZIP+4
ssn "#####.## ##"    <- a dollar amount
```

**1. The 300-character window was mine, and it was wrong.** `labeledDigits` with a
wide window counts *nine digits* near a caption. Within 300 characters of an SSN
caption on a W-2 sit a ZIP+4 and several wage figures, all nine digits, none of
them SSNs. That is the partial box — it was covering the first token of the wrong
number.

Replaced with `labeledSsn()`, which insists on SSN **shape** (3-2-4), rejects the
5-4 ZIP+4 split, refuses dot separators so currency can't match, and skips the
caption "Social security **wages / tips / tax**" — a money caption that was
walking the matcher straight into the wage boxes.

**2. `reprocessAll()` never called `addIdRunBoxes`.** The first OCR pass added
boxes for bare 9-digit IDs; the re-detect path did not. So the EIN — and every
FEIN on a state form — disappeared the instant anything triggered a re-detect: a
detector toggle, a keyword edit. Added to both the OCR'd-page and docx branches.

**3. ZIP+4 was being read as a 9-digit ID.** `nineDigitRuns` joins digit groups on
dash or dot, so `74074-1234` totalled nine and was flagged on essentially every
document carrying an address. Two of the three "identifiers" on that W-2 page were
ZIP codes. Now rejected by shape.

That third one had a second effect worth noting: the spurious ZIP hits made pages
*look* like they contained identifiers, which suppressed the very warning that was
supposed to catch a missed SSN.

**Measured effect across all 95 documents:** SSN findings 120 → 108 (the twelve
removed were ZIP+4 and currency); 9-digit-ID runs no longer fire on addresses.

**Warnings are now per category.** `identifierGaps()` reports which kind of
identifier went unanswered, so a W-2 whose state ID was read but whose SSN was not
is still flagged. An aggregate check called that page satisfied.

**Known limitation:** a bare 9-digit run satisfies the EIN check, because that is
genuinely how EINs print on forms. So a page where the state ID is read but the
federal EIN is not will not warn. Tightening that would make every form warn.

---

## 2f. W-2 box (a) SSN and box (b) EIN — caption-anchored region OCR (FIXED 2026-08-19)

Neither the PSM-6 full-page second pass nor any DPI increase reads these. The
digits are perfectly legible; **whole-page segmentation drops values that sit
inside ruled form boxes.** Narrow the crop to the caption's own band and both read
first time.

Measured on `Daniel W2 2025.pdf` at 216 dpi:

| crop | psm 6 result |
|---|---|
| whole page | nothing |
| band around box (a) caption | `###-##-####` |
| band around box (b) caption | `#########` |

**Band geometry matters, and not symmetrically.** The value in box (a) sits at the
*left* edge of the ruled box — left of where the caption words begin. A band that
only reached 2 caption-heights left found nothing; 8 caption-heights left found
it. Final band, in multiples of caption height `h`:

```
x: caption.x0 - 8h  →  caption.x0 + 34h
y: caption.y0 - 1h  →  caption.y1 +  4h
```

**How it works.** `runOcrCore` now has three escalating stages, each only running
if the previous left a gap:

1. Full page, PSM 3 (library default).
2. Full page, PSM 6 — kept only if it closes a gap.
3. **Per-caption field bands, PSM 6.** For each unanswered caption category,
   `findCaptionBox` locates the caption in token space, `captionFieldRect` builds
   the band, `ocrRegion` draws that crop to a scratch canvas and OCRs it, then
   shifts the tokens back into page coordinates.

The crop is drawn to our own scratch canvas deliberately, so the coordinate maths
is ours and does not depend on how the OCR library reports coordinates for a
sub-rectangle.

**End-to-end verification** — real crops, real OCR, the real detector module:

```
region ssn  rect 373,615,2814,402   -> MATCH ssn "###-##-####"  box @ page px x=373 y=874
region ein  rect 0,1012,3991,648    -> MATCH ein "#########"    box @ page px x=409 y=1356
```

**Region boxes are tagged `region:true` and preserved across re-detects**, like
manual boxes. Their text is not part of `pg.pageText`, so regenerating from the
page alone would silently discard them — the same failure mode as the missing
`addIdRunBoxes` call in section 2e.

---

## 2g. What actually fixed the W-2 (2026-08-19, from browser traces)

Three sessions of reasoning from the sandbox got this wrong twice. Instrumenting
the pipeline and reading real browser traces got it right. **Add tracing before
theorising** — `cenaTrace()` in the console, digits masked, safe to paste.

### The two real root causes

**1. CSP was strangling the OCR engine.** The console showed:

```
Fetch API cannot load data:application/octet-stream;base64,AGFzbQ...
violates the following Content Security Policy directive: "connect-src 'none'"
```

The inlined Tesseract WASM core is handed to the worker as a `data:` URL, and
`connect-src 'none'` refused it. tesseract.js then fell back silently to a
degraded path, which is why the identical file read cleanly under native
tesseract and badly in the browser. Changed to `connect-src data: blob:` —
both are local schemes that cannot reach the network, so nothing can leave the
machine. http(s), ws(s), remote hosts, scripts, frames, images and fonts are all
still refused.

**2. Tesseract was guessing the wrong resolution.** `Estimating resolution as 720`
for a canvas rendered at `72 * SCALE` = 144 dpi. That mismatch produced
`Image too small to scale!!` and `Line cannot be recognized!!` on small glyphs.
Now set explicitly via `user_defined_dpi`.

**Effect of those two together:** stage-1 word count went 180 → 274, both
captions matched, and box (a) SSN plus box (b) EIN were detected in the *first*
pass — stages 2, 3 and 4 were not needed at all.

### The over-redaction that came with it

With the SSN finally being read, a redaction box appeared over the client's
**wages** figure. Cause found by reconstructing the traced page text and running
the real detector over it: `ssnLikeRuns` returned `###-##-#### #` — the SSN plus
the first digit of wages.

```js
/\d{3}-\d{2}-\d{2,4}(?:[\s.\-]\d)?|\d{2}-\d{4}/g
```

The optional tail exists for OCR-sheared fragments like `412-55-88 3`. On a
*complete* SSN it greedily ate the space and the next digit — and on a W-2 the
next number along is Wages, sitting right beside box (a). Split into two
alternatives with the complete form first, so a complete SSN consumes no tail:

```js
/\d{3}-\d{2}-\d{4}|\d{3}-\d{2}-\d{2,3}(?:[\s.\-]\d)?|\d{2}-\d{4}/g
```

Two assertions added (26/26): a complete SSN must span exactly 11 characters
beside a wages figure, and a sheared SSN must still get its tail.

### Stages that remain, and why

The escalation still earns its place even though stage 1 now succeeds on this
file — it is the safety net for worse scans:

1. Full page, PSM 3, correct DPI.
2. Full page, PSM 6 — kept only if it closes a gap. On the traced run it made
   things *worse* (`unanswered 1 -> 2`) and was correctly discarded.
3. Per-caption field bands (section 2f). Worked for the EIN when stage 1 failed.
4. **W-2 box (a) probe.** When box (a)'s caption is unreadable — it came through
   as `(eb ees! dictates` — anchor off the EIN caption, since box (a) always sits
   directly above box (b). Measured at the browser's own 3356x4566 canvas: EIN
   caption at y=747 h=72; 4 heights above found nothing, 6 found the SSN, so the
   probe uses 7.

**"Answered" is decided geometrically**, not by type: is there an identifier box
inside *this caption's* band? The old aggregate check let one 9-digit state ID
satisfy both the SSN and EIN captions, so the pipeline declared success and never
looked at either box.

---

## 2b. Still open — the "Code Number" finding

- A nine-digit number labeled **"Code Number"** survives redaction on both S-Corp
  returns (`2023 SCorporate Rose Rock ClientCopy`, `2024 Rose Rock tax return`) —
  nine digits immediately after the company name. Probably the practice EIN.
  Needs the same manual check the Form 511 finding got: open the redacted file,
  confirm the digits are really visible, and decide whether an EIN on a business
  return is something you want redacted at all.
- Only **16 of 93** redacted files have been OCR-scanned. The residual-PII picture
  is incomplete until the rest are done — see section 5, step 3.

---

## 3. FQ Intake Auditor

`fq_auditor/` — working end-to-end and scored. **`RESUME_HERE.md` is the current
handoff and supersedes `HANDOFF.md`.** `extract_cache.py` is the dead
proof-stage extractor, replaced by `extract.py`.

- `audit.py` — entry point, plain-text renderers
- `extract.py` — per-page-parallel OCR/text extractor, content-hash cache
- `classify.py` — content-based (not filename-based) classifier
- `detectors.py` — residual-PII scanner, confidence levels
- `reconcile.py` — satisfied / missing / mismatched / unexpected
- `series.py` — statement-series gap and duplicate detection
- `checklist_parse.py` — parses the checklist PDF via layout geometry → 16 items
- `checklist_bassett.py` — hardcoded fallback checklist
- `render_docx.py` — Word report renderer
- `Run Intake Auditor.command` — double-click launcher, drag a folder in
- `SETUP.md` — fresh-Mac setup, no dev account needed

**Scored** (`SCORECARD.md`): 4/4 mislabeled files, 7/8 missing months, 2/2
duplicates, both disguised-file traps, both control series correctly left alone.

Runs on your Mac via the `.command` launcher — it does **not** depend on
Claude's sandbox.

---

## 4. Test corpus

- `RedactorTest/` — 94 unredacted source documents, flat, plus
  `_GROUND_TRUTH_manifest.csv` (row-by-row key with MD5s, `curveball` and
  `content_intact` columns)
- `RedactorTest_ANSWER_KEY.md` — 4 deliberately mislabeled files, 8 omitted
  months, 2 duplicates, 2 control series
- `redacted-batch-2026-08-14 (1)/` — 94 redacted PDFs + 1 xlsx, the redactor's
  output, plus `batch redaction log.txt` (95 documents, generated 8/14/2026)
- `Client_File Checklist.pdf` — what the auditor parses

---

## 5. Next actions, in priority order

1. **Confirm the Form 511 fix on the real file.** The code change is done
   (section 2) and the self-test passes, but synthetic assertions are not the
   same as the actual page. Open `Cena_5.html`, run the 2023 individual return,
   check page 26 for all three SSNs — then re-run a P&L and a paystub and
   confirm nothing new fires.
2. **Verify the "Code Number" finding** on both S-Corp returns.
3. **Finish OCR on the redacted batch** — 77 of 93 files remain:
   ```
   cd fq_auditor
   python3 extract.py "../redacted-batch-2026-08-14 (1)" .cache
   python3 audit.py "../redacted-batch-2026-08-14 (1)" \
     --checklist "../Client_File Checklist.pdf" \
     --client "Bassett" --greeting "Dr. and Mrs. Bassett" --cache .cache
   ```
   Resumable — every finished file is cached permanently.
4. **Eyeball Cap 1 HYSA January** — statements named "Nov-Dec" and "Jan-Feb", so
   this may be cycle-labelling rather than a real gap.
5. **Decide on the 68 "unexpected" items** — group by type, or leave flat?
6. Then: trailing-gap detection (needs an as-of date), the filing tree
   (`owner_side` already emitted), timing a real run on your Mac, and a second
   client's checklist to test the geometry parser.

---

## 7. Packaging — making this independent of Claude

**Start from an accurate baseline: neither tool depends on Claude at runtime.**

- **Cena** is one self-contained HTML file. Every library is inlined, the CSP
  sets `connect-src 'none'`, and it runs from `file://` in any browser with no
  install, no server, no network. It is already standalone.
- **The auditor** is Python that runs on your Mac via `Run Intake Auditor.command`.
  It needs python3 + tesseract, per `SETUP.md`. Also already standalone — that is
  why a dead Claude sandbox blocked nothing today.

What is missing is not independence, it is **packaging discipline**. The failure
mode you actually hit was 21 near-identical filenames in `~/Downloads` with no
marker for which one mattered.

Suggested shape:

```
FQ Intake Tools/
  README.md                  ← what each tool is, how to run it, in plain English
  VERSION.md                 ← dated changelog; what changed and why
  Cena/
    Cena.html                ← THE current build, no version suffix
    archive/                 ← every prior build, dated
  Auditor/
    (contents of fq_auditor/)
    Run Intake Auditor.command
  TestCorpus/
    RedactorTest/
    RedactorTest_ANSWER_KEY.md
    _GROUND_TRUTH_manifest.csv
```

Rules worth adopting:

- **One current file per tool, no version number in the name.** Version lives in
  `VERSION.md` and in a comment at the top of the file. Old builds go to
  `archive/` with a date. This alone prevents what happened.
- **Nothing lives in `~/Downloads`.** Downloads is a staging area the OS is free
  to clean out.
- **The self-test ships with the tool.** `Cena.html#selftest` is the thing that
  tells a future you whether the build is sound, without needing to remember
  what the fixes were.
- **Keep the test corpus with the tools**, not in a client folder. It is how you
  verify a change; it is not client work product.
- If you want it genuinely portable, zip `FQ Intake Tools/` — Cena survives that
  intact because it has no external dependencies. The auditor needs its two
  installs, which `SETUP.md` already covers.

Worth deciding when you pick this up: whether the test corpus contains real
client data. If it does, it should not travel with a package you might share.

---

## 6. Lessons from the crash

- The work survived because it was **written to disk**. The conversation did not.
  Keep writing state to files.
- `~/Downloads` is not storage. Cena_5 sat there among 20 superseded copies and
  a folder cleanup would have taken all of it.
- Claude's Linux sandbox failed to boot for this entire session. File tools kept
  working. Anything that must run — the auditor, the extractor — should be
  runnable **on your Mac**, which is why `Run Intake Auditor.command` exists.
- Cowork artifacts do not survive an app reinstall. Neither does session history.
