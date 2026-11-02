# FQ Toolkit: setting up a Mac, and using it

For the analyst taking the toolkit over. Setup is once per Mac, about 30
minutes. Every command below is typed into **Terminal** (press `Cmd + Space`,
type "terminal", press return), one at a time, exactly as written.

When Terminal asks for your Mac password, **typing shows nothing at all**. That
is normal: type it and press return.

---

## Part 1: install (once per Mac)

### 1. Apple's developer tools

```
xcode-select --install
```

A window opens; click **Install** and wait for it to finish (a few minutes).
If it says they are already installed, carry on.

### 2. Homebrew (how Macs install the tools below)

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

When it finishes it prints **"Next steps"** with two or three commands. Copy and
run those too; Homebrew does not work until you do. Then check:

```
brew --version
```

### 3. Python and the three tools the toolkit uses

```
brew install python@3.13 tesseract poppler git
```

- `python@3.13` runs the toolkit
- `tesseract` reads scanned and photographed pages
- `poppler` lets Claude look at PDF pages directly
- `git` keeps your copy of the toolkit up to date

### 4. Claude Code (how the toolkit asks Claude to read documents)

The toolkit uses Claude on the firm's team seat, not a paid API key.

```
curl -fsSL https://claude.ai/install.sh | bash
```

Then start it once and sign in with your **firm** Claude account:

```
claude
```

Follow the sign-in prompts in the browser, then type `/exit` to leave. Check it
is where the toolkit looks for it:

```
ls ~/.local/bin/claude
```

**Never set an `ANTHROPIC_API_KEY`.** The toolkit refuses to run with one,
because that would bill outside the team subscription.

### 5. The Analysis share (where the client folders live)

In Finder: **Go > Connect to Server** (`Cmd + K`), enter

```
smb://192.168.62.170/Analysis
```

Connect, sign in with your office account and tick **Remember this password in
my keychain**. Prospects live under `Brogan/Prospects/2026` (the folder name is
historical; leave it).

To have it reconnect at login: **System Settings > General > Login Items**, click
**+**, and add the **Analysis** drive.

### 6. The toolkit itself

```
mkdir -p ~/Desktop/FQ_Toolkit
cd ~/Desktop/FQ_Toolkit
git clone https://github.com/four-quadrants/fq-toolkit-prospectPip.git prospectPip
```

You need to have been added to the repo (four-quadrants/fq-toolkit-prospectPip)
with your GitHub account first. The first time, git asks you to sign in to
GitHub in the browser.

**Getting the latest version later:**

```
cd ~/Desktop/FQ_Toolkit/prospectPip && git pull
```

One file is deliberately **not** in git, because it holds masked wording from
a client deck: `deck_examples.json` (box-by-box examples for drafted slide
wording). Copy it from the previous analyst's Mac into
`FQ_Toolkit/prospectPip/fq_auditor/assets/`. Without it the toolkit still
works; drafted wording is just less like the firm's.

### 7. First start

In Finder, open `Desktop/FQ_Toolkit/prospectPip/fq_auditor`, **right-click**
`Open FQ Toolkit.command` and choose **Open**, then **Open** again. (Right-click
the first time only; macOS blocks a downloaded script until you confirm it.)

The first start installs the Python libraries it needs, which takes a few
minutes. Your browser then opens the toolkit. Leave the Terminal window open
while you work; closing it stops the toolkit.

### 8. The Claude side: the FQ Prospect plugin

In the Claude desktop app, install the firm's **FQ Prospect** plugin. It holds
the things only Claude can do for the toolkit:

- pulling a client's documents and checklist from LaunchBay
- loading and pulling in the lead advisor's review pages

The LaunchBay connector must be connected in your Claude account.

---

## Part 2: one client, start to finish

The app's tabs run in this order, and the dots across the top show where each
client stands (green: up to date; orange: something it is built from has
changed). **Update N out of date** rebuilds whatever has gone orange, in order.

| Step | Where | What you do |
|---|---|---|
| Documents | Claude | "Pull [client] from LaunchBay" (or let the scheduled pull do it) |
| 1 Intake | App | Pick the client; it downloads and audits. Review & file, then **Build File Tree** |
| 2 Initial notes | App | Build. Claude reads the credit reports here the first time |
| 3 Cash flow, Assumptions | App | Build each. Claude reads every bank statement (it must tie out to the dollar) and every investment statement |
| 4 Analysis review | Claude | "Load [client]'s analysis review". Share the link with the lead advisor (edit access). He checks what was found and marks the questions; the email to the client writes itself on the page, and he copies it from there |
| Answers come back | App | New documents go through Intake, then **Update** |
| 5 Consult review | Claude | "Load [client]'s consult review". He works through open questions, the plan, recommendations, projections, slides |
| Pull in | Claude | "Pull in [client]'s consult review". Claude reads his notes first |
| Deck | App | **Build the deck**. It opens in Keynote or PowerPoint and stays editable |

The first build of a client takes longer (Claude reading statements and
reports, a few minutes to twenty for a large client). After that, only new
documents are read.

---

## Things worth knowing

- **Originals are never moved.** Filing makes copies; `Original_sourcedocs`
  stays exactly as the client sent it.
- **What Claude reads is checked.** Bank statements must balance to the dollar;
  credit report, account and return figures must appear in the document's own
  text. Anything that does not check out is flagged, never quietly used.
- **The internal audit report lists real account numbers.** Never forward it.
- **Client passwords** are saved in `Original_sourcedocs/_PASSWORDS.txt`; treat
  it as sensitive as the documents.
- **Commits:** always in this order, so the check reads what is about to go in:
  ```
  git add -A && python3 fq_auditor/precommit_check.py && git commit -m "what changed" && git push
  ```
  The check stops anything that looks like an account number, a birthdate or
  other client detail reaching git. If it flags something, replace it with an
  invented example, then run the whole line again.

---

## If something goes wrong

- **"command not found: brew"**: step 2's "Next steps" commands were not run.
- **The window flashes and disappears**: right-click the `.command` file and
  choose Open.
- **The browser says the site can't be reached**: an older copy is still
  running. `pkill -f fq_app.py`, then start it again.
- **"Claude not available"** in a build log: sign in again (`claude`, then
  follow the prompts), and check `ls ~/.local/bin/claude`.
- **The client folders are missing**: the Analysis share unmounted; redo step 5.
- **A statement "DOES NOT TIE"** in the build log: open it and look; usually a
  page missing from the PDF. The account is left out of the cash flow until it
  ties or is replaced.
