---
name: fq-prospect-board
description: "Show the analyst the Four Quadrants prospects they are working, where each stands, and buttons for the next step. Use when someone says \"show my prospects\", \"what's next\", \"where are my prospects\", \"prospect board\", \"add [client] to my prospects\", \"drop [client]\", or opens a session without naming a client. Also use after any step finishes, to show what comes next."
---

# Prospect board

## Where the .json files live

Every .json the toolkit keeps for a client (launchbay_manifest, launchbay_tasks,
checklist_reviewed, claude_checklist, doc_readings, notes, summary,
review_pages, review_decisions, bank_statements and the rest) lives in one
folder beside the clients, never in the client folder:
`Prospects/<year>/Claude outputs/<name>_<Client>.json`, for example
`Prospects/2026/Claude outputs/notes_Example, Jane.json`. Get the exact path
with `python3 fq_auditor/store.py "<client folder>" notes.json` and read and
write it there. Wherever this skill says `_Audit/<name>.json` or a .json "in
the client folder", it means that path. The client folder keeps the documents
and the outputs people open (initial notes, cash flow, deck).

The analyst's front door: one panel in the chat with the prospects they are
working, each one's stage, and buttons that send the next request. They never
need to remember a phrase.

**The board is every client folder in this year's Prospects folder, minus
the ones the analyst removed.** The team makes a folder at the initial call,
so a folder is the signal someone is a prospect. A LaunchBay project with no
folder never appears. Prospects that go quiet stay until the analyst removes
them.

## 1. Folders

Everything is under `/Volumes/Analysis/Brogan/Prospects` (the toolkit is
`Prospects/FQ_Toolkit/prospectPip`, clients are `Prospects/<year>`). If it is
not connected, ask for it with the folder-access tool and tell the analyst
only "click Allow".

## 2. The list: folders, minus what the analyst removed

The removals live on a page in the analyst's own Claude account, titled
**My Prospects**, never in a file on the share. It is owned by whoever runs
the pipeline (the analyst), who shares it with the team.

- Find it with the Artifact tool, `action: "list"`, `scope: "all"`, title
  "My Prospects". If the analyst has none, create it: load the
  `artifact-capabilities` skill, then publish `references/my_prospects.html`
  as a new artifact in their account with `capabilities: {"db": {}, "user": {}}`
  and icon `list`. Tell them in one line to share it with the team from its
  Share menu (Can edit). Never publish it from anyone else's account.
- Read it: `ArtifactData` `list` of collection `prospects`. Documents with
  `hidden: true` were removed by the analyst.
- Run the folder scan, passing each removed one:

```
python3 <toolkit>/fq_auditor/prospects.py "<Prospects/2026>" --hide "Lamberti" --hide "Smith"
```

- Sync the page in one `ArtifactData` `batch`: for every folder, `update`
  (or `set` if new) `prospects/<slug>` with `name`, `folder`, `stage`, a
  one-line `note` and any `flag`, never touching `hidden`; `delete` the
  documents whose folder is gone (moved to Signed or Not moving forward), and
  say so in one line. Slug = lower-case surname and first name, hyphens.
- "Drop Lamberti" / "he's gone": `update` `prospects/<slug>` with
  `{hidden: true, removed: <today>}`. "Bring Lamberti back": `hidden: false`.

## 3. Add LaunchBay, for the prospects on the board only

With the LaunchBay connector, for each prospect on the board:

- Find its project (`find-projects`; match by surname, allowing for changed
  or hyphenated names, e.g. folder "Tanksley" and project "Prather
  (Tanksley)").
- `get-project-activity`. If the client uploaded a file or wrote a comment
  after the folder's last pull (`pulled`; none means never pulled), mark it
  **New in the portal** with the date, and make its first button "New info
  came in", sending: "<Name> sent more in the portal. Pull them again, run
  the intake and show me what changed and what is still open."
- If nothing has come in for 3 weeks while documents are still due, mark it
  **Quiet since <date>** and offer a button "Remove from my prospects".
- Where LaunchBay's stage disagrees with the folder, trust LaunchBay and say
  so in the status line.

Do not pull, file or build anything here. Apart from the page sync, this step only reads.

## 4. Draw the board

Call the visualize `read_me` (modules: interactive) first if it has not been
called in this session, then `show_widget` with the template in
`references/board.html`, filled in: one row per prospect, most urgent first
(New in the portal, then anything with a consult or debrief date coming up,
then the rest by due date). Each button calls
`sendPrompt` with its request. Keep the free-text box at the bottom.

After the panel, write at most two sentences: what needs attention first,
and anything that dropped off. Mention how many are removed, with a button
"Show removed prospects".

## Rules

- Read only. The board never pulls, files, builds or emails.
- No client data beyond names, stages and dates on the board.
- No em dashes.
