# FQ Toolkit: setting up a Mac, and using it

For anyone on the team who runs the pipeline (the analyst, and the lead
advisor if he wants to run steps himself). Setup is once per Mac, about 15
minutes.

The pipeline runs through the **Claude desktop app**. The toolkit's code runs
inside Claude's own workspace, which already has Python and the PDF and
scanning tools, so your Mac needs very little: the Claude app, the client
folders, and a copy of the toolkit.

---

## Part 1: set up (once per Mac)

### 1. The Claude desktop app

Install it from claude.ai/download and sign in with your **firm** Claude
account (the team seat; never a personal account, never an API key).

### 2. The Analysis share (where the client folders live)

In Finder: **Go > Connect to Server** (`Cmd + K`), enter

```
smb://192.168.62.170/Analysis
```

Connect, sign in with your office account and tick **Remember this password in
my keychain**. Prospects live under `Brogan/Prospects/2026` (the folder name is
historical; leave it).

To have it reconnect at login: **System Settings > General > Login Items**, click
**+**, and add the **Analysis** drive.

### 3. GitHub access

1. Make a GitHub account (github.com) with your work email if you do not have one.
2. Ask an owner of the **four-quadrants** organization to add you to the
   `fq-toolkit-prospectPip` repo (Admin if you will change the toolkit).
   Accept the email invite.

### 4. The toolkit, on your Desktop

It goes in **Desktop > FQ_Toolkit > prospectPip**. Open **Terminal** (press
`Cmd + Space`, type "terminal", press return) and type these, one at a time:

```
xcode-select --install
```

A window opens; click **Install** and wait (a few minutes; this gives your Mac
`git`). If it says they are already installed, carry on. Then:

```
mkdir -p ~/Desktop/FQ_Toolkit
cd ~/Desktop/FQ_Toolkit
git clone https://github.com/four-quadrants/fq-toolkit-prospectPip.git prospectPip
```

The first time, git asks you to sign in to GitHub in the browser.

**Getting the latest version later** (whenever someone says they changed it):

```
cd ~/Desktop/FQ_Toolkit/prospectPip && git pull
```

### 5. Connect the two folders in Claude

In the Claude desktop app, start a new task and connect these two folders
(Claude asks for them the first time, or add them from the folder button):

- `Desktop/FQ_Toolkit`
- `Analysis/Brogan/Prospects/2026`

### 6. The FQ Prospect plugin, and LaunchBay

In the Claude desktop app, install the firm's **FQ Prospect** plugin: it holds
the steps (pull, intake, assumptions, the review pages, the deck) so every
person's Claude runs them the same way. To pull documents yourself, also
connect the **LaunchBay** connector in your Claude account.

### 7. Check it works

In Claude, with both folders connected, type:

```
Check the FQ toolkit is ready
```

Claude runs a quick check (it can find the toolkit and the Prospects folder,
and the code's libraries load) and says what, if anything, is missing.

## Part 2: one client, start to finish

Every step is asked for in Claude (the desktop app, with the `FQ_Toolkit` and
Prospects folders connected). Claude runs the toolkit, reads the documents,
checks what it read, and tells you what came out. The work comes in three
stages; nothing from a later stage is built early.

**Stage 1, initial review**

| Step | Say to Claude | What you get |
|---|---|---|
| Documents | "Pull [client] from LaunchBay" | The client's uploads and checklist |
| Intake | "Run [client]'s intake" | Documents filed into Documents/Business and Personal; what is missing; the follow-up email to copy into Outlook |
| Initial notes | "Build [client]'s initial notes" | Initial notes .xlsx in the client folder. Claude pulls from LaunchBay and runs the intake first if they have not been done, so this one line is enough |

Then the consult offer call. If the client accepts, send the Expanded List.

**Stage 2, consult accepted**

| Step | Say to Claude | What you get |
|---|---|---|
| Documents | "Pull [client] again" and "run [client]'s intake" | The expanded documents filed, and what is still missing |
| Cash flow | "Build [client]'s cash flow" | Every bank statement read and tied to the dollar; the cash flow |
| Portfolio | "Run [client]'s portfolio analysis" | Accounts, returns and fees |

**Stage 3, the lead advisor's deep dive and the consult**

| Step | Say to Claude | What you get |
|---|---|---|
| Assumptions: your check | "Build [client]'s assumptions" or "Load [client]'s analysis review" (the same step) | Runs the cash flow and the investment accounts first if they are not done, then builds the assumptions and opens the review page on them (the Assumptions and What we found tabs). Comment on any section that is wrong or missing, then "pull in my check": Claude fixes what you flagged and refreshes the page. Repeat until it is clean |
| Hand it over | Press **Ready for the lead advisor** (click twice) | The page shows its link and the steps: **Share** menu, add him with **Can edit**, send him the link. Or ask Claude for the link |
| Analysis review: lead advisor | He checks the assumptions and findings, comments, picks his questions, presses Done | The email to the client is built on the page; copy it into Outlook. Then "pull in [client]'s analysis review" |
| Answers come back | "Run [client]'s intake", then "update [client]" | New documents filed; anything they change rebuilt |
| Consult review | "Load [client]'s consult review" | A page for the plan, recommendations, projections and slides |
| Pull in | "Pull in [client]'s consult review" | His decisions saved |
| Deck | "Build [client]'s deck" | Consult deck .pptx, editable in Keynote or PowerPoint |

The first time Claude reads a client's statements and reports it takes a few
minutes. After that, only new documents are read.

---

## Part 3: changing the toolkit yourself

The toolkit is meant to be changed by whoever runs it, with Claude doing the
coding. Set this up once.

### GitHub access

1. Make a GitHub account (github.com) with your work email if you do not have one.
2. Ask an owner of the **four-quadrants** organization to invite you, and to
   give you **Admin** on the `fq-toolkit-prospectPip` repo
   (repo **Settings > Collaborators and teams**). Accept the email invite.
3. Sign this Mac in to GitHub so git can push:
   ```
   brew install gh
   gh auth login
   ```
   Choose **GitHub.com**, **HTTPS**, **Yes** (authenticate git), **Login with a
   web browser**, and follow it.
4. Tell git who you are (shows on each change):
   ```
   git config --global user.name "Your Name"
   git config --global user.email "you@4quadrant.com"
   ```

### Making a change

1. Get the latest first:
   ```
   cd ~/Desktop/FQ_Toolkit/prospectPip && git pull
   ```
2. Ask Claude to make the change. Either:
   - in the **Claude desktop app** (Cowork), with the `FQ_Toolkit` folder and the
     Prospects folder connected: describe what you want ("the cash flow should
     treat X as Y"; "add this to the deck"); or
   - in **Terminal**: `cd ~/Desktop/FQ_Toolkit/prospectPip && claude`, then
     describe it.

   Claude reads `CLAUDE.md` at the top of the repo first: the map of the code
   and the rules (client data never goes into git, test on `_TEST` copies, how
   to check its work).
3. Test it: restart the app, run the step you changed on a `_TEST` client, and
   compare with what you expect.
4. Save it to GitHub (always this order):
   ```
   cd ~/Desktop/FQ_Toolkit/prospectPip && git add -A && python3 fq_auditor/precommit_check.py && git commit -m "what changed" && git push
   ```
5. Everyone else gets it with `git pull`, then restarts the app.

If two people change the same file, `git pull` may say there is a conflict;
ask Claude ("git pull says there is a conflict, sort it out") and it will
merge the two.

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

---

## Appendix: the old app (fallback only)

Before Claude became the front door, the toolkit ran as a local web app. It is
kept in case it is ever needed, and needs more installed on the Mac
(Homebrew, Python, Tesseract, poppler, and the Claude command-line tool). The
original steps:



#### 1. Apple's developer tools

```
xcode-select --install
```

A window opens; click **Install** and wait for it to finish (a few minutes).
If it says they are already installed, carry on.

#### 2. Homebrew (how Macs install the tools below)

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

When it finishes it prints **"Next steps"** with two or three commands. Copy and
run those too; Homebrew does not work until you do. Then check:

```
brew --version
```

#### 3. Python and the three tools the toolkit uses

```
brew install python@3.13 tesseract poppler git
```

- `python@3.13` runs the toolkit
- `tesseract` reads scanned and photographed pages
- `poppler` lets Claude look at PDF pages directly
- `git` keeps your copy of the toolkit up to date

#### 4. Claude Code (how the toolkit asks Claude to read documents)

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

#### 5. The Analysis share (where the client folders live)

In Finder: **Go > Connect to Server** (`Cmd + K`), enter

```
smb://192.168.62.170/Analysis
```

Connect, sign in with your office account and tick **Remember this password in
my keychain**. Prospects live under `Brogan/Prospects/2026` (the folder name is
historical; leave it).

To have it reconnect at login: **System Settings > General > Login Items**, click
**+**, and add the **Analysis** drive.

#### 6. The toolkit itself

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

#### 7. First start

In Finder, open `Desktop/FQ_Toolkit/prospectPip/fq_auditor`, **right-click**
`Open FQ Toolkit.command` and choose **Open**, then **Open** again. (Right-click
the first time only; macOS blocks a downloaded script until you confirm it.)

The first start installs the Python libraries it needs, which takes a few
minutes. Your browser then opens the toolkit. Leave the Terminal window open
while you work; closing it stops the toolkit.

#### 8. The Claude side: the FQ Prospect plugin

In the Claude desktop app, install the firm's **FQ Prospect** plugin. It holds
the things only Claude can do for the toolkit:

- pulling a client's documents and checklist from LaunchBay
- loading and pulling in the lead advisor's review pages

The LaunchBay connector must be connected in your Claude account.

---

