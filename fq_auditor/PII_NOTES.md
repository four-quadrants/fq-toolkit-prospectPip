# Residual-PII findings — how to read them

## Your original question: leaked, or just a last-four?

**Leaked.** The report masks values to the last four digits for display, but a
finding can only fire on a dashed SSN, a dashed EIN, a labelled account number of
6–17 digits, or nine consecutive digits. A document showing only `XXXXXXXX6840`
produces no finding. Every finding now states `(9 digits present)`, so it isn't
ambiguous.

## The Oklahoma Form 511 — confirmed

You opened the federal 1040 and it was properly redacted. You were right, and the
finding was also right: **it's page 26 of 29, the Oklahoma Form 511**, not the
federal return. You then confirmed three SSNs on that page. All three are now
detected:

| Field on Form 511 | Detected |
|---|---|
| Your Social Security Number | ✅ |
| Spouse's Social Security Number | ✅ |
| Dependent (Schedule 511-1) | ✅ |

**The redactor handles the federal return but not the Oklahoma state return.**

## Four things your check exposed

Finding one of three isn't a tuning problem, it's four bugs. Each is fixed:

**1. No page numbers.** The report said "there's an SSN in this file" about a
29-page return. That's what sent you to the wrong page. Findings now carry
`page N of M`, backfilled automatically for files cached before this change —
only for files that actually have findings, so nobody waits on a re-read of a
whole folder.

**2. Ruled boxes counted as "table noise".** The old rule treated a couple of `|`
characters as evidence of a numeric table and downgraded anything inside one. Tax
forms are made of ruled boxes, so this suppressed findings on exactly the pages
that matter most. Dot leaders are still treated as noise — that part was right.

**3. The caption window was too narrow.** OCR reads a form's boxes in its own
order, so "Your Social Security Number" landed ~150 characters from the digits it
labels. The window was 45 characters. It's now 300, with a guard so a number
buried in a column of figures near a caption stays medium rather than high.

**4. Deduplication kept the wrong occurrence.** This was the real culprit. The
same SSN appears on many pages, and its confidence depends entirely on which page
you judge it from — captioned on page 26, anonymous on page 24. The scanner kept
only the *first* occurrence, so it judged both parents' SSNs on their least
informative appearance and discarded the page where the caption made them obvious.
Occurrences are now merged across pages, keeping the best-evidenced sighting and
listing every page the value appears on.

That last one matters operationally: on the unredacted 2023 return, one SSN
appears on **pages 11-15, 18-26, 28-30, 33-37, 40-42 of 42**. Re-redacting the
first page you find would leave twenty-four more.

There's also a page-level escalation rule: if one identifier is confirmed on a
page, other nine-digit numbers on that same page are promoted. Confidence
shouldn't depend on whether OCR happened to render a caption legibly — at 200 DPI
"Your Social Security Number" came through as `"Seon ae zis"`, while at 150 DPI it
read correctly.

## Current numbers

- **Redacted batch** (16 files cached): 5 high-confidence findings in 4 files —
  the Form 511 SSNs, plus a nine-digit number by "Code Number" on both practice
  returns. Zero dashed SSNs, zero dashed EINs, zero labelled accounts, so the
  redactor's main paths are working.
- **Originals** (all 95): 81 high-confidence findings in 20 files, 28 OCR
  artifacts suppressed. Expected — these are unredacted.

## Still to check

- The **"Code Number"** finding on `2023 SCorporate Rose Rock ClientCopy` and
  `2024 Rose Rock tax return` — nine digits after the company name. Probably the
  practice EIN. Same kind of check as the Form 511 one: does it survive redaction?
- Only 16 of 93 redacted files have been scanned. The rest need OCR before this
  is a complete picture of what your redactor leaves behind.

## The client email is separate

Two independent mechanisms, deliberately. This section is internal and never
reaches a client. The email is scanned *after* it's generated, and if any PII
pattern or internal filename appears the tool refuses to write the file. That
check caught a real leak during development — an early draft included "account
ending 6840" and cited a source filename.
