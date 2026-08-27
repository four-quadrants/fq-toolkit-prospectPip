# Setting up the Intake Auditor on a Mac

You do this once. After that, running an audit is a double-click.

Nothing here needs an Apple Developer account, and nothing you install sends
client documents anywhere — the auditor reads the files on your own Mac and
writes its report to the same folder.

---

## Step 1 — Install the two tools it needs (about 10 minutes, once)

Open **Terminal**. It's in Applications → Utilities, or press `Cmd + Space`,
type "terminal", and press return. A window with a text prompt appears.

**a) Install Homebrew**, which is how Macs install this kind of tool. Copy the
line below, paste it into Terminal, and press return:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It will ask for your Mac password. Typing shows nothing at all — no dots, no
asterisks. That's normal; type it and press return. This step takes several
minutes and prints a lot of text. If it finishes by telling you to run two extra
commands ("Next steps"), copy and run those too.

**b) Install the text reader and Python.** Paste this and press return:

```
brew install tesseract python
```

**c) Check it worked.** Paste this:

```
tesseract --version && python3 --version
```

You should see a version number for each. If you do, you're done with setup —
you never need Terminal again.

---

## Step 2 — Run an audit

1. Open the `fq_auditor` folder.
2. Double-click **`Run Intake Auditor.command`**.

   The very first time, macOS may refuse to open it because it came from
   somewhere else. If so: right-click the file, choose **Open**, then click
   **Open** in the box that appears. You only do this once.

3. It asks you three things:
   - **The client's folder.** Don't type the path — drag the folder from Finder
     into the Terminal window and press return.
   - **The client's checklist PDF.** Drag it in the same way. (Press return with
     nothing typed to use the standard built-in checklist.)
   - **The client's name** and how the email should greet them.

4. It shows you **how it read the checklist** and waits. Read that list. Each
   item shows what document satisfies it and what it will ask the client for.
   Anything it's unsure about is marked `>> CHECK`.

   If something is wrong, open `checklist_reviewed.json` in the client's folder,
   fix it, and save. It's an ordinary text file. Then type `y` and press return.

5. It reads every page and writes two files into the client's folder:

   - **`<Client> - Internal Audit.docx`** — for us. Opens in Pages. Satisfied,
     mismatched, missing and unexpected items, statement months that never
     arrived, files whose contents don't match their name, duplicates, and a
     residual-PII section.
   - **`<Client> - Client Email.txt`** — a draft "here's what we still need"
     email, ready to paste in and adjust.

Both open automatically when it finishes.

---

## Two things to know

**The internal report is internal.** Its residual-PII section lists real account
and ID numbers found in supposedly-redacted files. Never forward that report to
a client. The draft email is generated separately and is checked automatically
for account numbers, ID numbers and internal filenames — if any turn up, the tool
refuses to write the email at all rather than hand you something unsafe.

**First run is slow, later runs are fast.** The auditor reads every page of every
document, which for a few hundred pages takes a few minutes. It remembers what it
read, keyed to the file's contents, so running it again is nearly instant. When a
client sends five more documents, only those five are read. Renaming or moving a
file doesn't cause a re-read.

---

## If something goes wrong

**"command not found: brew"** — Homebrew didn't finish installing, or the "Next
steps" commands it printed weren't run. Run step 1a again and read the last few
lines it prints.

**The window flashes and disappears** — right-click `Run Intake Auditor.command`
and choose Open instead of double-clicking.

**"That isn't a folder"** — the folder was typed rather than dragged in. Drag it
from Finder; the path fills in correctly by itself.

**A document comes out as "Unrecognised"** — it's usually a scan too faint to
read, or a document type the classifier hasn't been taught yet. It'll be listed
in the unexpected section of the report so it isn't silently ignored. Send the
file along and it can be added.

**The report says the client email wasn't written** — that's the safety check
doing its job. The message lists what would have leaked. Tell Austin; it's a bug
in the email wording, not something you did wrong.
