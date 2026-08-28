# Build brief — the `fq-launchbay-pull` skill

**Status: not built yet.** This is the spec. Build it, then delete this line.

Written 2026-08-27 at the end of a long session, while the procedure was still
fresh. Everything below was learned by doing it by hand for Dr. Kelly Spaulding;
none of it is guesswork.

---

## Why this needs to exist

The FQ Intake Auditor runs entirely locally and needs two files in a client's
folder before it can do anything:

| File | What it is |
|---|---|
| `launchbay_manifest.json` | every document the client uploaded, with a direct download link |
| `launchbay_tasks.json` | the request checklist, the team's tick-marks, and anything the client typed instead of uploading |

Neither can be produced by the toolkit itself: LaunchBay's list lives behind
their API, and the only access available is the MCP connector inside Claude.
There are no API credentials and none are obtainable.

So a person with Claude produces those two files; the operator — who has neither
Claude nor LaunchBay access — presses buttons in the app. **This skill is that
handoff.** Today it exists only as improvisation in one chat, which means a
fresh session would reinvent it and might not reinvent it identically.

## What it should do

**Trigger on:** "pull <client> from LaunchBay", "refresh <client>'s documents",
"get the LaunchBay list for <client>", or a client name alongside any request to
fetch or refresh their intake.

**Takes:** a client name, and the client folder (ask if not obvious; do not guess
between two similarly named folders).

**Produces:** the two JSON files above, then runs `lb_checklist.py` to turn the
tasks file into `checklist_reviewed.json`, then reports what it found.

## Procedure

### 1. Find the project

Use the LaunchBay connector's `find-project` with `projectName`. It returns the
project id, its stages, and the request tasks with their ids. Kelly Spaulding was
project `165409` with tasks "Initial Document Request" (`2419117`) and "Expanded
Document Request" (`2419118`).

If more than one project matches, stop and ask. Filing one client's documents
into another's folder is the worst thing this can do.

### 2. Get the file list

`get-project-files` with the project id. It returns everything grouped by task,
each with a name, a File ID, a `kind`, a size, and a `cdn.filestackcontent.com`
URL.

**Only `kind: collection` is a client upload.** `signature` and `attachment` are
documents the FIRM sent out — the ACH form, the privacy principles, the blank
request list, an Open Dental sample report. Filing those back as client documents
would be wrong, and `lb_fetch.py` already refuses them, but the manifest should
record the kind honestly rather than filter early.

Write `launchbay_manifest.json` into the **client folder** (the one containing
`Original_sourcedocs`, not `Original_sourcedocs` itself):

```json
{
  "project": "Dr. Kelly Spaulding",
  "project_id": 165409,
  "pulled": "2026-08-27",
  "note": "The urls are unauthenticated and CDN-cached; treat this file as sensitive as the documents themselves.",
  "files": [
    {"id": 1097221, "task": "Expanded Document Request", "kind": "collection",
     "name": "8.14.26 File to Four Quadrants.qbb",
     "url": "https://cdn.filestackcontent.com/Tb5QbuNSTWi9c26Os4SA"}
  ]
}
```

Every field is used. `id` is how `lb_fetch.py` knows what it has already
downloaded, so it must be the LaunchBay File ID and must be stable.

### 3. Get the checklist

For each request task, read its subtasks and its comments. The subtasks ARE the
checklist items and carry the team's `done` flags. The comments are where a
client answers by typing instead of uploading — Kelly typed:

> "Total Dr. Days worked: 2024: 144  2025: 193  Jan 1-June 30 2026: 94"

...and also uploaded three spreadsheets with the same numbers, which is what most
clients do. Both routes must be captured; the auditor prefers the documents and
falls back to the comment.

Write `launchbay_tasks.json` into the client folder:

```json
{"project": "Dr. Kelly Spaulding",
 "tasks": [
   {"stage": "Initial Document Request", "status": "completed",
    "subtasks": [{"text": "2024, 2025, & 2026 YTD Profit & Loss Statement", "done": true}],
    "comments": [{"who": "Kelly Spaulding", "text": "Total Dr. Days worked: ..."}]}]}
```

### 4. Build the checklist

```
python3 lb_checklist.py "<client folder>"
```

Writes `checklist_reviewed.json`. It handles the wording, the fuzzy matching and
the side (Practice vs Personal) itself — do not hand-edit its output.

### 5. Report

State plainly: the project found, how many uploads, how many are new since the
last pull, how many checklist items, and which ones the client answered in the
portal rather than uploading. Then tell them to press **Get documents** in the app.

## Rules

- **Never invent a document.** If LaunchBay lists nothing, say so. A manifest with
  a plausible-looking guess in it would be downloaded, filed, and believed.
- **Never overwrite `Original_sourcedocs`.** This skill writes JSON only.
- **Re-running is normal and safe.** The manifest is a snapshot; `lb_fetch.py`
  skips by File ID and by matching name+size on disk, so nothing downloads twice.
- **Treat the manifest as sensitive.** Those URLs need no login — anyone holding
  one can read the document. That is why it is written inside the client folder
  and never anywhere general.
- **Do not filter the file list to what you think is relevant.** Record
  everything with its kind; the toolkit decides.

## Traps found the hard way

- The `.qbb` QuickBooks backups are ~53 MB each. They download fine but are
  binary — the classifier identifies them by extension, which is the one place a
  filename is allowed to decide anything.
- A manifest written by hand missed four files, and the audit then reported three
  checklist items missing that the client had actually sent. **Always take the
  full list from `get-project-files`; never transcribe it.**
- The audit reads `checklist_reviewed.json` by walking up from the documents
  folder. Put it in the client folder and it will be found.

## Done means

Running `python3 audit.py "<client folder>/Original_sourcedocs" --client "<name>"`
produces a sensible satisfied/missing count instead of falling back to the
built-in Bassett checklist. If you see the `BUILT-IN FALLBACK` banner, the
checklist did not land where the audit looks.
