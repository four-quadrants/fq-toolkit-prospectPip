# Running a client through intake

What to do, in order, from "a client sent documents" to "we know what is still
missing". `SETUP.md` covers installing the toolkit; this covers using it.

**One step needs Claude. Everything else is buttons in the app.** That split is
the thing to understand before anything else here makes sense.

| Step | Who | Where |
|---|---|---|
| 1. Pull the list from LaunchBay | Austin | Claude |
| 2. Download the documents | anyone | app, Download tab |
| 3. Run the audit | anyone | app, Audit tab |
| 4. Review and decide | analyst | app, Review tab |
| 5. File | analyst | app, Build File Tree |
| 6. Chase the client | analyst | email / portal |

---

## 1. Pull the list from LaunchBay — Austin only

Ask Claude: **"pull [client] from LaunchBay"**.

This writes three files into the client's folder:

- `launchbay_manifest.json` — every document on the project, with a download link
- `launchbay_tasks.json` — the request checklist, the team's tick-marks, and
  anything the client typed in the portal instead of uploading
- `checklist_reviewed.json` — built from the tasks file; this is what the audit
  scores against

Nobody else can do this step. The toolkit has no LaunchBay credentials and none
are obtainable; the MCP connector inside Claude is the only access. That is why
the step exists as a handoff rather than a button.

**The manifest goes stale.** It is a photograph, not a window. If the client
uploads something an hour later, nothing on this machine knows. The app reports
the manifest's age and warns past three days — believe that warning. A stale
list and a client who has sent nothing look identical from here.

> Prather's list was four days old. The app said "nothing new". She had uploaded
> seven files and deleted nine.

---

## 2. Download the documents

App → **Download from LaunchBay**.

Despite the name it does not talk to LaunchBay. It reads the manifest and pulls
each document straight from the CDN. Re-running costs nothing: already-fetched
files are skipped by id, and by name and size if the id log was lost.

The **Audit** button turns green when every document on the list is on disk AND
the list is fresh. Grey means one of those is untrue — check which before
concluding the client has sent nothing.

---

## 3. Run the audit

App → **Run the audit**.

The first run on a client takes a few minutes: every page of every document is
read, and scanned documents are OCR'd. After that it is quick, because the text
is cached against each file's contents — renaming or moving a document does not
cause a re-read.

Two things make a run slow again, both expected:

- a new client, or newly arrived documents
- an OCR version bump in the code, which deliberately invalidates every cache
  entry so a fix actually reaches documents already read

---

## 4. Review and decide

This is the only step that needs judgement. The page groups the checklist three
ways, because they are three different jobs:

**Your call** — the auditor read the documents and could not settle it. Start
here. These are the only items that need you.

**Waiting on the client** — nothing arrived. Not your problem to solve, but you
can say something about it.

**Answered** — settled. Open it to spot-check; click any document name to view it.

### Verdicts change things. Notes do not.

A **verdict** moves the item: it changes the status, the chase list, and the
draft client email. A **note** is a record — it shows on the item and in the
writeup, and it never reaches the client, so it is a safe place for "asked on
the call, they don't have one" or "Casey chasing".

Writing a note and leaving the dropdown alone leaves the item open. That is
deliberate: typing a sentence should not quietly close a checklist item.

### Nothing on screen updates until the audit runs again

Save decisions writes them to disk. The counts, the groups and the writeup are a
snapshot of the last run. Press **Run the audit** again, or **Build File Tree**,
which re-runs it for you.

---

## 5. File

App → **Build File Tree**. Copies every document into `Documents/Personal` and
`Documents/Business`. **Originals are never moved** — if something is filed
wrongly the original is still in `Original_sourcedocs` where the client put it.

---

## 6. Chase the client

`_Audit/<client> - Client Email.txt` is a draft asking for what is outstanding.
Read it before sending; it is generated, not written.

`_Audit/<client> - Needs Clarification` is the internal writeup — what needs a
human, what is missing, what could not be placed. **Never send this to a
client**: it lists residual account and ID numbers found in the documents.

The client email is checked automatically and will refuse to generate rather
than leak an account number. The internal report has no such protection because
it is not supposed to leave the building.

---

## Things that have actually gone wrong

**A document the client withdrew.** Clients delete uploads — usually replacing a
bad export, sometimes by accident. The fetcher only ever adds, so a withdrawn
document stays on disk and keeps answering its checklist item. Move those into
`Original_sourcedocs/_Withdrawn/`; they are still read and still count, but the
report says the client has taken them down.

**A promise read as an answer.** "Will include P&L and balance sheets for these"
is not a P&L. The auditor rejects futures, but read portal comments yourself
before trusting an item that was satisfied by one.

**A password-protected document.** Passwords the client sent live in
`Original_sourcedocs/_PASSWORDS.txt`, copied word for word. That file is as
sensitive as the documents themselves.

**An entity-specific ask.** "Returns for the wellness clinic" cannot be answered
by the main practice's return. Where a checklist names two different entities
for the same kind of document, the auditor refuses to guess and asks you.

**A document that classified as `unknown`.** Usually a scan too faint to read, or
a type the classifier has not been taught. It appears under "provided but not on
the checklist" rather than being silently dropped. Send it to Austin.

---

## When something looks wrong

Run **Check This Mac.command** first — it rules out the boring causes in two
seconds.

If a number on the page disagrees with a number in the report, the report is
from the last run and the page may be showing saved decisions on top of it.
Re-run before investigating anything else.

If the audit prints a `BUILT-IN FALLBACK` banner, `checklist_reviewed.json` is
not where the audit looks. It belongs in the client folder, one level above
`Original_sourcedocs`.
