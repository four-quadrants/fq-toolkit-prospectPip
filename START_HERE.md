# START HERE: set up the FQ Toolkit on a new Mac

**For Claude.** A teammate has connected this Prospects folder and said
something like "read START HERE and set me up". Walk them through the setup
below, one step at a time. Check each step yourself wherever you can, say
plainly what you checked and what you found, and only ask the person to do
what you cannot do for them. Keep each message short: one step, what to click
or paste, and wait for them before moving on.

The person is an analyst or the lead advisor, not a developer. Plain words, no
jargon. When they need Terminal, give the exact lines to paste, one block at a
time, and tell them Terminal shows nothing while they type a password.

---

## Rules that hold from the first message

- **Firm Claude account only.** If anything shows an `ANTHROPIC_API_KEY`, stop
  and tell them to remove it: the toolkit never bills outside the team seat.
- **No client data in git**, ever. **Test on `_TEST` copies** under
  `Prospects/2026/_TEST/`; do not enter a live client folder unless they ask.
- **Never send email, never change who a page is shared with, never enter a
  password or credential.** Those are always the person's own clicks.
- **No em dashes** in anything you write for them.

---

## The setup, in order

Keep a short checklist in your replies (done / still to do) so they always
know where they are.

### 1. The firm Claude account

Ask them to confirm they are signed in to the Claude desktop app with their
**work** account. You cannot check this yourself; take their word and move on.

### 2. The client folders

They connected this folder to read this file, so the share is mounted. Check
that `Prospects/2026` lists client folders and a `_TEST` folder. If the share
ever disappears, the fix is Finder, **Go > Connect to Server** (`Cmd + K`),
`smb://192.168.62.170/Analysis`, sign in, tick **Remember this password**; and
to reconnect at login, **System Settings > General > Login Items**, add the
**Analysis** drive.

### 3. GitHub access

The toolkit's code lives in the firm's GitHub repo
`four-quadrants/fq-toolkit-prospectPip`. Ask whether they have a GitHub account
that has been added to it.

- No account: they make one at github.com with their work email, then send
  the username to an owner of the `four-quadrants` organization to be added
  (Admin on the repo if they will change the toolkit). They accept the email
  invite. Wait for this before step 4; there is nothing to clone until it is
  done.

### 4. The toolkit, on their Desktop

First ask for the folder `~/Desktop/FQ_Toolkit` to be connected (request the
directory). If it does not exist yet, or has no `prospectPip` inside it, have
them open **Terminal** (`Cmd + Space`, type "terminal", return) and paste:

```
xcode-select --install
```

A window opens; **Install**, and wait. If it says the tools are already
installed, carry on. Then paste:

```
mkdir -p ~/Desktop/FQ_Toolkit && cd ~/Desktop/FQ_Toolkit && git clone https://github.com/four-quadrants/fq-toolkit-prospectPip.git prospectPip
```

The first time, git opens a browser to sign in to GitHub. When it finishes,
connect `~/Desktop/FQ_Toolkit` and check `prospectPip/CLAUDE.md` is there.
From here on, **read `prospectPip/CLAUDE.md`**: it is the map and the rules.

If the toolkit is already there, have them update it instead:

```
cd ~/Desktop/FQ_Toolkit/prospectPip && git pull
```

### 5. The ready check

Run, in the shell, from the toolkit folder:

```
python3 fq_auditor/readycheck.py "<the Prospects/2026 folder>"
```

Install anything it lists with the command it prints, run it again, and tell
them "Ready" once it is clean.

### 6. The FQ Prospect plugin

It holds the steps (pull, intake, initial notes, assumptions, the review
pages, the deck), so every person's Claude runs them the same way. If it is
not installed, zip `prospectPip/plugin/fq-prospect` into `fq-prospect.plugin`
in your outputs folder, present the file, and ask them to install it from the
card. Confirm it shows in their plugins afterwards.

### 7. LaunchBay (only if they will pull documents)

Pulling a client's documents needs the LaunchBay connector in their Claude
account. If they will do pulls, ask them to connect it (Claude's connectors
settings) and confirm you can see it. The lead advisor usually does not need it.

### 8. One real test, on a _TEST client

Build the initial notes for a _TEST client into your outputs folder (not into
the client folder), for example:

```
cd fq_auditor && python3 build_outputs.py "<Prospects/2026/_TEST/Weiler, Seth - TEST>" --what workbook --outdir "<your outputs folder>"
```

Present the workbook so they see it open. If it fails, read the error, fix
what you can (usually a missing library from step 5), and run it again.

### 9. The tour (five minutes)

- The eight steps, who does each, and what to say for each: the Prospect
  Pipeline Showcase, https://claude.ai/artifact/1DwNs2bqHXXuAeFemNXpWm
- The analyst guide: `prospectPip/fq_auditor/SETUP.md`, Part 2.
- How to change the toolkit: say what is wrong and propose a solution, ask for
  a preview of the fix on a _TEST client, save it once verified with the commit
  line Claude gives. Getting everyone else's changes: `git pull`.

If a link does not open for them, it has not been shared with them yet; tell
them to ask whoever owns it.

### 10. Wrap up

Finish with the checklist: what is set up, anything still waiting (GitHub
invite, LaunchBay), and the one sentence to start real work: "Pull [client]
from LaunchBay", or "Run [client]'s intake".
