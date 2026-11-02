---
name: "fq-launchbay-pull"
description: "Pull a client's document list and request checklist out of LaunchBay and write the two JSON files the FQ Intake Auditor needs (launchbay_manifest.json and launchbay_tasks.json), then build checklist_reviewed.json. Use whenever someone says \"pull [client] from LaunchBay\", \"refresh [client]'s documents\", \"get the LaunchBay list for [client]\", \"re-pull [client]\", or names a Four Quadrants prospect alongside any request to fetch, refresh, or update their intake documents or checklist. Also use when the FQ Toolkit app reports \"No document list for this client yet\" or an audit falls back to the built-in Bassett checklist. This is the only way those files can be produced — the toolkit has no LaunchBay credentials."
---

# fq-launchbay-pull

Pull a Four Quadrants prospect's uploads and request checklist out of LaunchBay
and write them into the client's intake folder as two JSON files, so the FQ
Intake Auditor — which has no LaunchBay access of its own — can do the rest.

## Why this exists

The FQ Intake Auditor runs entirely on a local machine and needs two files in a
client's folder before it can do anything:

| File | What it is |
|---|---|
| `launchbay_manifest.json` | every document on the project, with a direct download link |
| `launchbay_tasks.json` | the request checklist, the team's tick-marks, and anything the client typed instead of uploading |

Neither can be produced by the toolkit. LaunchBay's list lives behind their API,
and the only access available is the MCP connector inside Claude. There are no
API credentials and none are obtainable.

So a person with Claude produces those two files; the operator — who has neither
Claude nor LaunchBay access — presses buttons in the app. **This skill is that
handoff.** Everything downstream (fetching documents, classifying, filing,
auditing) reads from these two files, so a mistake here becomes a mistake in the
client's audit that nobody upstream can see.

## What you need before starting

- **The client name.** Enough to find the project.
- **The client folder** — the one that *contains* `Original_sourcedocs`, not
  `Original_sourcedocs` itself. If it isn't obvious, or two folders have similar
  names, ask. Do not guess.

Typical layout:

```
<client folder>/                    <- both JSON files go HERE
├── Original_sourcedocs/            <- documents land here (not your concern)
├── launchbay_manifest.json
├── launchbay_tasks.json
└── checklist_reviewed.json         <- lb_checklist.py writes this
```

## Procedure

### 1. Find the project

Call the LaunchBay connector's `find-project` with `projectName`. It returns the
project id, its stages, and every task with its id and status.

**If more than one project matches, stop and ask which one.** Filing one client's
documents into another client's folder is the worst thing this pipeline can do,
and it would look entirely plausible on the way through.

Note the ids of the tasks that carry the document checklist. These are the ones
named like "Initial Document Request" and "Expanded Document Request". Signature
tasks (ACH Form, Privacy Principles) and call tasks (Initial Call, Debrief Call)
are not document requests — they have no checklist and belong nowhere in
`launchbay_tasks.json`.

### 2. Get the file list

Call `get-project-files` with the project id. It returns every file grouped by
the task it is attached to, each with a name, a File ID, a `kind`, a size in KB,
and a `cdn.filestackcontent.com` URL.

**Take the full list from the tool output. Never transcribe, summarise, or
abridge it.** A hand-written manifest on the first client missed four files, and
the audit then reported three checklist items missing that the client had
actually sent. The tool output is the source of truth; your job is to reshape it,
not to curate it.

Write `launchbay_manifest.json` into the **client folder**:

```json
{
  "project": "Dr. Jane Example",
  "project_id": 100001,
  "pulled": "2026-08-27",
  "note": "Written from the LaunchBay connector. The urls are unauthenticated and CDN-cached; treat this file as sensitive as the documents themselves.",
  "files": [
    {"id": 200001, "task": "Expanded Document Request", "kind": "collection",
     "name": "Practice backup to Four Quadrants.qbb",
     "bytes": 2048000,
     "url": "https://cdn.filestackcontent.com/EXAMPLEHANDLE"}
  ]
}
```

Every field earns its place:

- **`id`** is the LaunchBay File ID. `lb_fetch.py` records it in `.lb_fetched.json`
  and skips ids it has already seen, so this is what makes re-running free. It
  must be the real File ID and it must be stable.
- **`kind`** decides what gets downloaded. See below.
- **`bytes`** is a second safety net — with it, `lb_fetch.py` recognises a file
  already on disk by name and size even if its id log was lost. The connector
  reports size in **KB, 1024-based**, so `bytes = kb * 1024`. That was measured
  against real downloads, not assumed: the drift is under 500 bytes on files up
  to 54 MB, comfortably inside the 2048-byte tolerance `lb_fetch.py` allows.
  Without `bytes`, that fallback degrades to matching on filename alone.
- **`task`** is the task the file was attached to. For files the tool lists as
  project-level, use `"(project-level)"`.

#### Only `kind: collection` is a client upload

`signature` and `attachment` are documents the *firm* sent out — the ACH form,
the privacy principles, the blank request list, an Open Dental sample report.
Filing those back as client documents would be wrong.

`lb_fetch.py` already refuses anything that isn't `collection`, so **record every
file with its true kind rather than filtering early**. The manifest is a faithful
snapshot of the project; the toolkit decides what to act on. Filtering here would
hide from the operator that the firm's own attachments exist.

#### Copy names exactly as LaunchBay has them

Resist tidying. Real names in one project included `Operating Account X0000 -
2026-07-31 (1).pdf`, `May HSA statement .pdf` (trailing space), `March HSA
Investment Statemetn.pdf` (client's typo), and ten files with **no extension at
all**. All of that is correct input — the toolkit renames files after it
classifies them, and the rename log is what the reviewer reads to understand what
happened. If you "fix" a name here, the manifest stops matching what is on disk
and the fix becomes invisible.

### 3. Get the checklist

For each document-request task, call `find-task` with its task id. Read two
things from the result:

**The subtasks** are the checklist items, and they carry the team's `[done]`
flags. Copy each subtask's text **verbatim and in full** — do not paraphrase or
truncate. `lb_checklist.py` derives what would satisfy an item from its wording,
so a shortened item is a different item. "If the practice has a line of credit
(LOC), please provide the following: ..." is recognised as a conditional that
needs a yes/no rather than a document, purely because it starts with "If the
practice has". Trim that opening and it becomes a chase for a document that may
not exist.

**The comments** are where a client answers by typing instead of uploading. This
is not a rare edge case — it is how most clients handle birthdates, patient
counts, doctor days, and "we don't have one of those". One client wrote:

> "Birthdates: (both spouses' dates typed out) No current financial plan No line of credit for the practice"

Downstream, `reconcile.py` turns a *missing* item into a *satisfied* one when a
comment answers it. So **include every comment on the task, from everyone, in
full** — client and team alike. Dropping the comments does not produce a slightly
incomplete report; it produces a report that chases the client for information
they already gave you.

Write `launchbay_tasks.json` into the client folder:

```json
{
  "project": "Dr. Jane Example",
  "project_id": 100001,
  "written": "2026-08-27",
  "tasks": [
    {
      "stage": "Initial Document Request",
      "task_id": 2419117,
      "status": "completed",
      "subtasks": [
        {"text": "2024, 2025, & 2026 YTD Profit & Loss Statement", "done": true}
      ],
      "comments": [
        {"who": "Jane Example", "text": "Total Dr. Days worked: 2024: 150 2025: 180 Jan 1-June 30 2026: 90"}
      ]
    }
  ]
}
```

`status` is the task's own status from LaunchBay (`completed`, `in_review`,
`active`), copied as-is. `done` is the subtask's tick-mark, as-is — do not infer
it from whether you think a document arrived.

### 4. Build the checklist

```
python3 <toolkit>/fq_auditor/lb_checklist.py "<client folder>"
```

Writes `checklist_reviewed.json` beside the tasks file. It handles the wording,
the fuzzy matching, the Practice/Personal split and the comment matching itself —
**do not hand-edit its output.** Editing it is how a checklist ends up describing
what someone hoped was there.

The audit finds this file by walking up from the documents folder, so putting it
in the client folder is what makes it work.

### 5. Verify before reporting

Two cheap checks that catch the failure modes that actually happen:

```bash
python3 - "<client folder>" <<'PY'
import json, sys, collections
folder = sys.argv[1]
m = json.load(open(f"{folder}/launchbay_manifest.json"))
t = json.load(open(f"{folder}/launchbay_tasks.json"))
files = m["files"]
ids = [f["id"] for f in files]
dupes = [k for k, v in collections.Counter(ids).items() if v > 1]
missing = [f["name"] for f in files
           if not all(f.get(k) for k in ("id", "task", "kind", "name", "url"))]
print("manifest files :", len(files), " (compare to the count in get-project-files)")
print("client uploads :", sum(1 for f in files if f["kind"] == "collection"))
print("duplicate ids  :", dupes or "none")
print("incomplete rows:", missing or "none")
for task in t["tasks"]:
    print(f"{task['stage']}: {len(task['subtasks'])} subtask(s), "
          f"{len(task['comments'])} comment(s)")
PY
```

The manifest count must equal the total `get-project-files` reported. The comment
counts must equal what `find-task` showed — a zero there almost always means the
comments were skipped rather than that the task had none.

### 6. Report

State plainly:

- which project was found, and its id
- how many files, how many are client uploads vs firm attachments
- how many are new since the last pull (compare ids against `.lb_fetched.json`
  if it exists)
- how many checklist items, and **which ones the client answered in the portal
  rather than uploading** — these are the ones a reviewer would otherwise chase
- then: press **Get documents** in the FQ Toolkit app.

## Rules

- **Never invent a document.** If LaunchBay lists nothing, say so. A manifest with
  a plausible-looking guess in it would be downloaded, filed, and believed.
- **Never write to `Original_sourcedocs`.** This skill writes JSON only.
- **Re-running is normal and safe.** The manifest is a snapshot; `lb_fetch.py`
  skips by File ID and by name+size on disk, so nothing downloads twice.
- **Never delete `.lb_fetched.json`.** After the toolkit files documents it also
  renames them, so the name-and-size check will no longer match. From that point
  the id log is the only thing standing between a re-pull and a folder full of
  duplicates.
- **Treat the manifest as sensitive.** Those URLs need no login — anyone holding
  one can read the document. That is why it is written inside the client folder
  and never anywhere general. Don't paste them into chat, email, or tickets.
- **Do not curate.** Record every file with its kind, every subtask with its full
  text, every comment from everyone. The toolkit decides what matters.

## Traps found the hard way

- **Both files get transcribed by accident.** The rule against transcribing the
  manifest is well known; the tasks file is where it keeps happening, because
  subtask text is long and comments look like chatter. On one client the tasks
  file was written with all twelve expanded subtasks marked `done: false` when
  LaunchBay had every one ticked, and with `"comments": []` against a task
  carrying thirteen real comments — including the client's birthdates. The audit
  reported birthdates missing. Nothing about the output looked wrong.
- **`.qbb` QuickBooks backups are ~53 MB each.** They download fine but are
  binary; the classifier identifies them by extension, which is the one place a
  filename is allowed to decide anything. Keep the extension.
- **Ten files arrived with no extension at all.** That is normal and the toolkit
  copes. Don't add one.
- **Sizes are KB, not bytes.** Multiply by 1024. Writing the raw number into
  `bytes` would make every on-disk check fail and re-download the whole project.
- **If the audit prints a `BUILT-IN FALLBACK` banner**, `checklist_reviewed.json`
  did not land where the audit looks. It belongs in the client folder, one level
  above the documents.

## Done means

Running

```
python3 <toolkit>/fq_auditor/audit.py "<client folder>/Original_sourcedocs" --client "<name>"
```

produces a sensible satisfied/missing count against this client's real checklist,
with no `BUILT-IN FALLBACK` banner.

