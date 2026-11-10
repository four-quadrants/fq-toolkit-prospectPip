---
name: fq-prospect-board
description: "Show anyone on the team the Four Quadrants prospects in the pipeline, where each stands, and buttons for the next step. Use when someone says \"show my prospects\", \"what's next\", \"where are my prospects\", \"prospect board\", \"add [client] to my prospects\", \"drop [client]\", \"[client] isn't moving forward\", \"[client] signed\", or opens a session without naming a client. Also use after any step finishes, to show what comes next."
---

# Prospect board

## Where the .json files live

Every .json the toolkit keeps for a client (launchbay_manifest, launchbay_tasks,
checklist_reviewed, claude_checklist, doc_readings, notes, summary,
review_pages, review_decisions, bank_statements and the rest) lives in one
folder beside the clients, never in the client folder:
`Prospects/<year>/4.) Claude outputs/<Surname>/<name>_<Client>.json`, for example
`Prospects/2026/4.) Claude outputs/Example/notes_Example, Jane.json`. Get the exact path
with `python3 fq_auditor/store.py "<client folder>" notes.json` and read and
write it there. Wherever this skill says `_Audit/<name>.json` or a .json "in
the client folder", it means that path. The client folder keeps the documents
and the outputs people open (initial notes, cash flow, deck).

The analyst's front door: one panel in the chat with the prospects they are
working, each one's stage, and buttons that send the next request. They never
need to remember a phrase.

**The board is every client folder in this year's Prospects folder.** The
team makes a folder at the initial call, so a folder is the signal someone is
a prospect. A LaunchBay project with no folder never appears. The board is
built fresh from the share every time, so everyone (analyst, lead advisor,
anyone covering) sees the same prospects at the same stages. There is no page
to keep and nothing to share.

## 1. Folders

Everything is under `/Volumes/Analysis/Brogan/Prospects` (the toolkit is
`Prospects/FQ_Toolkit/prospectPip`, clients are `Prospects/<year>`). If it is
not connected, ask for it with the folder-access tool and tell them only
"click Allow".

## 2. The list

```
python3 <toolkit>/fq_auditor/prospects.py "<Prospects/2026>"
```

It skips the numbered folders (`1.) Not moving forward`, `2.) Signed`,
`3.) Documents`, `4.) Claude outputs`) and `_TEST`.

**Removing a prospect moves their folder; it never deletes anything.**
"Drop Lamberti", "he's gone", "Lamberti isn't moving forward":

1. Find the one folder that matches (ask if two do).
2. Ask to confirm, naming the folder and where it goes: "Move *Lamberti,
   Alberto due 10:19* to *1.) Not moving forward*? Nothing is deleted; it just
   drops off the board for everyone." Wait for a yes.
3. Move it with `mv` (the whole folder, as is) into
   `Prospects/<year>/1.) Not moving forward/`. If a folder of that name is
   already there, stop and ask. Never delete, rename or open files inside.
4. Say it is moved and offer the undo.

"He signed" moves it the same way into `2.) Signed`, after the same
confirmation. "Bring Lamberti back" moves it back into `Prospects/<year>`,
after confirming. The toolkit's own files for the client (in `4.) Claude
outputs`) stay where they are.

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
  **Quiet since <date>** and offer a button "Not moving forward" (it asks
  to confirm, then moves the folder).
- Where LaunchBay's stage disagrees with the folder, trust LaunchBay and say
  so in the status line.

Do not pull, file or build anything here. This step only reads.

## 4. Draw the board

Call the visualize `read_me` (modules: interactive) first if it has not been
called in this session, then `show_widget` with the template in
`references/board.html`, filled in: one row per prospect, most urgent first
(New in the portal, then anything with a consult or debrief date coming up,
then the rest by due date). Each button calls
`sendPrompt` with its request. Keep the free-text box at the bottom.

After the panel, write at most two sentences: what needs attention first,
and anything that dropped off. 

## Rules

- The board never pulls, files, builds or emails. The only thing it changes
  is where a prospect's folder sits, and only after a yes.
- No client data beyond names, stages and dates on the board.
- No em dashes.
