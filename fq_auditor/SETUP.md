# Setting up the FQ Toolkit on a Mac

You do this once. After that, everything is a double-click.

Nothing you install sends client documents anywhere. The toolkit reads files on
your own Mac and on the Analysis share, and writes its results back to the
client's folder. There is no cloud account and no login.

---

## Step 1 — Install the two things it needs

About ten minutes, once, and you never need Terminal again afterwards.

Open **Terminal**: press `Cmd + Space`, type "terminal", press return. A window
with a text prompt appears.

**a) Install Homebrew**, which is how Macs install tools like this. Copy the
line below, paste it, press return:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It asks for your Mac password. **Typing shows nothing at all** — no dots, no
asterisks. That is normal. Type it and press return.

This takes several minutes and prints a lot of text. If it finishes by telling
you to run two more commands under a heading like "Next steps", copy and run
those too — Homebrew does not work until you do.

**b) Install Python and the text reader.** Paste this, press return:

```
brew install python tesseract
```

---

## Step 2 — Connect to the Analysis share

The client folders live on the office server, not on your Mac.

In Finder: **Go → Connect to Server** (`Cmd + K`), enter:

```
smb://192.168.62.170/Analysis
```

Click Connect and sign in with your office account. Tick "Remember this
password in my keychain" so you are not asked every morning.

You should end up with an **Analysis** drive in the Finder sidebar. Prospects
live under `Brogan/Prospects/2026`.

---

## Step 3 — Check it worked

Double-click **`Check This Mac.command`** in the main folder.

It prints a line per item and tells you plainly what, if anything, is wrong —
with the exact command that fixes it. Anything marked `STOP` has to be sorted
before the toolkit will run; anything marked `note` is worth knowing but is not
blocking.

If macOS refuses to open it because it came from somewhere else: right-click
the file, choose **Open**, then **Open** again in the box. You only do this
once per file.

---

## Step 4 — Start it

Double-click **`Start FQ Toolkit.command`**.

A Terminal window opens and your browser opens the toolkit. **Leave the Terminal
window alone while you work** — closing it shuts the toolkit down.

You will see four tabs.

### 1 · Download Files

Pick the client's folder, then press **Download from LaunchBay** to pull
everything they have uploaded.

The **Audit** button beside it turns **green with a tick** when every document
LaunchBay lists is already on your Mac — that is your signal there is nothing
left to fetch. It stays grey if documents are missing, and also if the list
itself is out of date, because "nothing new" from a stale list looks exactly
like a client who has sent nothing.

### 2 · Audit & File

Press **Run the audit**. The first run on a client takes a few minutes because
it reads every page of every document. After that it is quick — it remembers
what it read, keyed to the contents of each file, so renaming or moving
documents does not cause a re-read, and a client sending five more documents
means only those five are read.

### 3 · Review

This is where the work happens.

- **The checklist is at the top.** Outstanding items first. Each one names the
  documents that answered it, and clicking a document name opens it — PDFs as
  a page image, spreadsheets as a proper grid with column letters and row
  numbers.
- **"Your call" on every item.** The auditor reads text; it cannot open a debt
  schedule and judge whether the rows under the practice loans are the doctor's
  car. When you know better, say so: satisfied, practice side only, personal
  side only, not applicable, or still missing, plus a note. Your answer carries
  into the chase list and the client email, not just the screen.
- **Decide these** lists documents it could not place confidently.
- **Save decisions** as often as you like. It confirms, then re-arms as soon as
  you change anything else.
- **Build File Tree**, at the bottom, files everything. It re-runs the audit
  itself, so it picks up whatever you just saved.

Hovering any number under "Where this client stands" tells you what it is
counting.

### 4 · Redact

For producing shareable copies with identifiers removed. Not needed for
ordinary intake.

---

## Things worth knowing

**Originals are never moved.** Filing makes copies. If something is filed
wrongly, the original is still sitting in `Original_sourcedocs` exactly where
the client put it.

**The internal report is internal.** Its residual-PII section lists real account
and ID numbers found in the documents. Never forward it to a client. The draft
email is generated separately and checked automatically — if an account number
or ID would leak into it, the tool refuses to write the email at all rather than
hand you something unsafe.

**Passwords the client sent are saved beside the documents**, in
`Original_sourcedocs/_PASSWORDS.txt`, copied word for word. This means an
encrypted return can actually be opened — and it also means that file is as
sensitive as the documents themselves.

---

## If something goes wrong

Run **`Check This Mac.command`** first. It rules out the boring causes in about
two seconds.

**"command not found: brew"** — Homebrew did not finish installing, or the
"Next steps" commands it printed were not run. Redo step 1a and read the last
few lines it prints.

**The window flashes and disappears** — right-click the `.command` file and
choose Open rather than double-clicking.

**The browser says the site can't be reached** — an older copy of the toolkit is
probably still running and holding the port. Close every Terminal window running
it and start again, or run `pkill -f fq_app.py`.

**A preview says the app is older than the page** — exactly what it says. Quit
the toolkit and start it again.

**A preview says a PDF is encrypted** — the client sent it locked and did not
send us a password that opens it. Ask them for it.

**The client folders are missing** — the Analysis share has unmounted. Redo
step 2.

**A document comes out unrecognised** — usually a scan too faint to read, or a
document type the classifier has not been taught yet. It appears in the
unexpected section rather than being silently ignored. Send it to Austin and it
can be added.
