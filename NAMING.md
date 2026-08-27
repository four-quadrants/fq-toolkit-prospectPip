# Filing names — the standing convention

*The test is: you should know what a file is without opening it. Everything below
is derived from the document's CONTENTS, never its filename.*

---

## 1. The patterns

### Financial accounts — statements

```
[Person] <Kind> (<Institution>) x<last4> <YYYY-MM>.pdf
```

| example | |
|---|---|
| `Nadia Chk (BancFirst) x4108 2026-01.pdf` | checking, one month |
| `MM (Arvest) x3357 2026-02.pdf` | money market, holder not established |
| `Elise Roth (Vanguard) x6621 2026.pdf` | Roth, annual statement |
| `CC (Citibank) x8890 2026-03.pdf` | credit card |
| `Bank stmt (BancFirst) x2274 2025-12.pdf` | product could not be read |

**Kind** is read from a narrow window beside the account number: `Chk`, `Sav`,
`MM`, `HYSA`, `CD`, `CC`, `Brok`, `IRA`, `Roth`, `401k`, `403b`, `457`, `529`,
`HSA`. Falls back to `Bank stmt` / `CC` / `Brok`.

The window is narrow on purpose. Scanning the whole statement header made *every*
Arvest account a money market — the rate-disclosure table lists every product the
bank sells — and every Vanguard account a 529, from a footer mention.

### Wage and tax

```
[Person] <Type> <YYYY>.pdf
```

`Grant W-2 2024.pdf` · `Nadia Paystub 2026-04.pdf` · `Personal tax return 2024.pdf`
· `Business tax return 2023.pdf`

### Practice periodic

```
<Type> <YYYY-MM>.pdf
```

`Payroll summary 2026-02.pdf` · `Day sheet 2026-01.pdf` ·
`Provider productivity 2026-03.pdf` · `P&L 2024.pdf` · `Balance sheet 2025.pdf`

No person: these belong to the practice.

### One-offs

```
[Person] <Type> [YYYY].pdf
```

`Fee schedule 2026.pdf` · `Staff roster.pdf` · `Lease.pdf` ·
`Nadia Life insurance 2026.pdf` · `Bonus structure.pdf`

---

## 2. When a period is required

**Required** for anything that arrives as a run of months or years — statements,
payroll, day sheets, provider productivity, P&L, balance sheets, W-2s, paystubs,
tax returns. Two reasons: the name collides with its own siblings without it
(`Grant W-2.pdf` three years running), and the checklist asks for these *by*
period, so a name without one cannot be checked off.

**Not required** for one-offs — a lease, a staff roster, a fee schedule, an
insurance policy. The year is included when it is known and the name reads fine
without it.

If a period is required and cannot be read, the file **is still renamed** — to say
what it is — with `(year TBD)` in place of the date:

```
Grant Term Life Policy Summary.pdf  ->  Grant W-2 (year TBD).pdf
```

A file called "Term Life Policy Summary" whose contents are a W-2 is actively
misleading; `Grant W-2 (year TBD)` is merely incomplete. The marker goes in the
name, not only in the report, for two reasons: three undated W-2s would otherwise
all become `Grant W-2.pdf`, and the folder itself should show what still needs a
human.

The date is never invented. These appear in the clarification writeup under
**RENAMED BUT NEEDS CONFIRMING**, and the auditor counts them separately.

---

## 3. When a person is included

Only on documents that genuinely belong to one person: W-2, paystub, brokerage /
retirement statements, personal insurance, credit report.

Never on a joint return (two people), an S-corp return (none), or anything
belonging to the practice. Attaching whoever happened to be mentioned produced
`Nadia Business tax return 2023.pdf` — Nadia is named in the S-corp return, but it
is not her document.

The person is read from the document's own text, matched against household names
harvested from the personal tax return.

---

## 4. What gets renamed

Three cases only:

1. **The name contradicts the contents.** Non-negotiable — filing an insurance
   statement into Pay Info under an insurance name is worse than not filing it.
2. **The name says nothing.** `74074.pdf`, `Erin Roth.pdf`, `College.docx`,
   anything ending `(1)`.
3. Never otherwise. A name the client chose that already describes the contents is
   left alone. Churn makes a tree harder to recognise, not easier.

Measured on the 95-document Hollingsworth corpus: **14 renamed, 81 left alone.**

---

## 5. Three guardrails, each of which caught a real mistake

**The old name sometimes knows more than the classifier.**
`Cap 1 HYSA March.pdf` was going to become `Grant Chk (Capital One) x7719
2026-03.pdf` — throwing away "HYSA" and replacing it with a wrong guess. If the
existing name contains a product word the proposed name lacks, the old name wins.
This protected 15 files.

**Collisions must be detected, not discovered.**
`2024 individual Hollingsworth main.pdf` and `Cash_App_January_2026_Account_Statement.pdf`
both proposed `Personal tax return 2024.pdf` — the second is a mislabeled copy of
the same return. Renaming both would have destroyed one. Collisions are numbered
**and** flagged, because a collision usually means two documents that need
comparing.

**A required period that cannot be read is marked, not invented.**
`Grant Term Life Policy Summary.pdf` is a W-2, but the year is absent from the
OCR of that scan — the only four-digit numbers on the page are a suite number and
a ZIP. It becomes `Grant W-2 (year TBD).pdf`: correct about the type, honest
about the gap, and impossible to confuse with a dated sibling.

---

## 6. The rename log

`<Client> - Rename Log.csv`, in the client folder:

```
old_name, new_name, sha256, reason, destination
```

Keyed by content hash, so a file can be found by the name the client sent it
under, however many times it is later renamed or moved.

---

## 7. Still open

- **W-2 year on rotated or poor scans.** The year is printed large on the form but
  can be missing from the OCR entirely. A targeted region OCR would need to handle
  pages whose content is sideways — tesseract auto-orients a full page but not a
  crop, which is why cropping that document returned garbage.
- **`Acct` fallback frequency.** `BancFirst` statements never yield a product word,
  so they land on `Bank stmt`. Worth checking whether the product is legible on the
  document at all.
- **SoonerSave 457** reads as `Brok` rather than `457` — the account has no tail,
  so the narrow window falls back to the header, which does not name the plan type.
