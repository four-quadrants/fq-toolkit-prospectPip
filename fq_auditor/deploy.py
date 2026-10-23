#!/usr/bin/env python3
"""Move the toolkit between Macs as a zip you hand over.

    python3 deploy.py package                 # Austin: build the zip to send
    python3 deploy.py install                 # Them: unzip, then run this
    python3 deploy.py status                  # what version is installed here

WHY A ZIP AND NOT GIT OR THE SHARE
The repo is private on GitHub, so a second person needs an account, an access
grant, git installed and a Terminal session before they can get a single file.
Putting a copy on the Analysis share would avoid that, but it leaves an
installable toolkit sitting where anyone browsing can find and run it. A zip
you send deliberately goes to exactly one person and nowhere else.

The cost is honest: updates are a manual handoff, so versions can drift. That
is what VERSION.txt is for — ask them what it says before debugging anything.

Git stays the source of truth. This only carries a copy of it to someone else.

WHAT IT WILL NOT DO
- It never packages client documents. Only code, and by file type at that.
- It never deletes anything outside the toolkit folder it manages.
- It preserves .fq_root, so updating does not reset which folder you work in.
"""
import os
import re
import sys
import time
import shutil
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)                      # the prospectPip folder

# Where the handover zip is written. The Desktop, because the next thing that
# happens to it is being dragged into an email or AirDrop.
PACKAGE_DIR = os.path.expanduser(os.environ.get('FQ_PACKAGE_DIR', '~/Desktop'))

# Where it lands on a Mac. The Desktop, because the person using this needs to
# be able to find it without being told a path.
LOCAL_DIR = os.path.expanduser(os.environ.get('FQ_INSTALL_DIR', '~/Desktop/FQ_Toolkit'))

# Copied by name. An allow-list rather than a deny-list: a deny-list quietly
# ships whatever gets added later, and this is a route out of a folder that
# sits next to client data.
COPY_DIRS = ['fq_auditor']
COPY_FILES = ['Start FQ Toolkit.command', 'Check This Mac.command',
              'Install FQ Toolkit.command',
              'ARCHITECTURE.md', 'NAMING.md', 'RECOVERY.md', 'FQ Toolkit.png']

# What may leave this folder, by extension. An allow-list of DIRECTORIES is not
# an allow-list — the first version listed "fq_auditor" and copied everything
# inside it, which swept up .cache_originals: 202 files of text extracted from
# client documents, including a debt schedule with addresses and balances,
# published to a share other people can read. Naming the file types is the only
# version of this that stays safe as the folder accumulates things.
ALLOW_EXT = {'.py', '.md', '.command', '.png', '.gitignore'}
ALLOW_NAMES = {'README.txt', 'VERSION.txt'}

# Directories that never travel, whatever is in them. Anything beginning with a
# dot is excluded outright: every cache this tool writes is a dot-directory, and
# so is .git.
SKIP_DIRS = {'__pycache__', 'sample_output', 'node_modules'}


def _allowed_file(name):
    if name in ALLOW_NAMES:
        return True
    if name.startswith('.'):
        return False
    return os.path.splitext(name)[1].lower() in ALLOW_EXT


def _allowed_dir(name):
    return not name.startswith('.') and name not in SKIP_DIRS

# Kept across an update: this Mac's own answers, not the code's.
PRESERVE = ['fq_auditor/.fq_root']

VERSION_FILE = 'VERSION.txt'


def _ignore(directory, names):
    """copytree's filter: drop every directory and file not explicitly allowed."""
    out = []
    for n in names:
        full = os.path.join(directory, n)
        if os.path.isdir(full):
            if not _allowed_dir(n):
                out.append(n)
        elif not _allowed_file(n):
            out.append(n)
    return out


def git_stamp():
    """Short hash and date, so two Macs can tell whether they match."""
    try:
        out = subprocess.run(['git', '-C', REPO, 'log', '-1', '--format=%h %cd',
                              '--date=format:%Y-%m-%d %H:%M'],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return 'unknown'


def read_version(folder):
    p = os.path.join(folder, VERSION_FILE)
    if not os.path.isfile(p):
        return None
    try:
        return open(p).read().strip()
    except Exception:
        return None


def copy_tree(src, dst):
    """Replace dst with src, keeping this Mac's own settings."""
    saved = {}
    for rel in PRESERVE:
        p = os.path.join(dst, rel)
        if os.path.isfile(p):
            try:
                saved[rel] = open(p).read()
            except Exception:
                pass

    # Into a sibling first, then swap. A copy that dies halfway through leaves
    # a half-written toolkit that starts and then fails strangely; this way the
    # old one stays intact until the new one is complete.
    staging = dst + '.incoming'
    if os.path.isdir(staging):
        shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    n = 0
    for d in COPY_DIRS:
        s = os.path.join(src, d)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(staging, d), ignore=_ignore)
            n += sum(len(f) for _, _, f in os.walk(os.path.join(staging, d)))
    for f in COPY_FILES:
        s = os.path.join(src, f)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(staging, f))
            n += 1

    old = dst + '.previous'
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(dst):
        os.rename(dst, old)
    os.rename(staging, dst)
    shutil.rmtree(old, ignore_errors=True)

    for rel, body in saved.items():
        p = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            with open(p, 'w') as fh:
                fh.write(body)
        except Exception:
            pass

    # The .command files lose their executable bit on some copies, and a
    # double-click then opens them in a text editor instead of running them.
    for root, _, files in os.walk(dst):
        for f in files:
            if f.endswith('.command'):
                try:
                    os.chmod(os.path.join(root, f), 0o755)
                except Exception:
                    pass
    return n, saved


def package(dest_dir=None):
    """Build the zip to hand over. Staged in a temp folder, then zipped."""
    import tempfile
    dest_dir = dest_dir or PACKAGE_DIR
    if not os.path.isdir(dest_dir):
        print("No such folder: %s" % dest_dir)
        return 1

    stamp_line = git_stamp()
    tag = stamp_line.split()[0] if stamp_line != 'unknown' else time.strftime('%Y%m%d')

    tmp = tempfile.mkdtemp(prefix='fqpkg-')
    try:
        inner = os.path.join(tmp, 'FQ Toolkit')
        n, _ = copy_tree(REPO, inner)
        stamp = '%s\npackaged %s from %s' % (
            stamp_line, time.strftime('%Y-%m-%d %H:%M'), os.uname().nodename)
        with open(os.path.join(inner, VERSION_FILE), 'w') as fh:
            fh.write(stamp + '\n')

        base = os.path.join(dest_dir, 'FQ Toolkit %s' % tag)
        out = shutil.make_archive(base, 'zip', root_dir=tmp, base_dir='FQ Toolkit')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    size = os.path.getsize(out) / 1024.0
    print("\nPackaged %d file(s) — %.0f KB\n  %s\n" % (n, size, out))
    print("Version: %s" % stamp.replace('\n', ' · '))
    print("""
Send that zip to whoever needs it. Tell them to:

  1. Unzip it (double-click).
  2. Open the 'FQ Toolkit' folder it makes.
  3. RIGHT-CLICK 'Install FQ Toolkit.command' and choose Open, then Open again.
     macOS blocks a plain double-click on anything that arrived from elsewhere.

It installs to their Desktop and keeps any settings they already had, so the
same zip works for updates as well as first-time installs.
""")
    return 0


def install(src=None, dest=None):
    """Copy an unzipped toolkit onto this Mac, keeping local settings."""
    src = src or os.path.dirname(HERE)
    dest = dest or LOCAL_DIR
    if not os.path.isdir(os.path.join(src, 'fq_auditor')):
        print("This does not look like the toolkit folder:\n  %s\n" % src)
        print("Unzip the toolkit file you were sent, then run this from inside the")
        print("'FQ Toolkit' folder it creates.")
        return 1
    if os.path.abspath(src) == os.path.abspath(dest):
        print("\nThis is already the installed copy — nothing to do.\n")
        return 0
    have = read_version(dest)
    coming = read_version(src)
    n, saved = copy_tree(src, dest)
    print("\nInstalled %d file(s) to:\n  %s\n" % (n, dest))
    if have and coming and have.split('\n')[0] == coming.split('\n')[0]:
        print("(Same version you already had — nothing has changed.)")
    elif have:
        print("Updated from:  %s" % have.split('\n')[0])
        print("          to:  %s" % (coming or 'unknown').split('\n')[0])
    if saved:
        print("Kept your existing settings (%s)." % ', '.join(saved))
    print("\nNext: double-click 'Check This Mac.command' in that folder.\n")
    return 0


def status(_unused=None, local=None):
    local = local or LOCAL_DIR
    print("\nthis checkout : %s" % git_stamp())
    print("installed here: %s" % (read_version(local) or 'not installed').split('\n')[0])
    print("")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Move the toolkit between Macs")
    ap.add_argument('mode', choices=['package', 'install', 'status'])
    ap.add_argument('--from', dest='src', default=None,
                    help="the unzipped toolkit folder to install from")
    ap.add_argument('--to', default=None, help="where to put it on this Mac")
    a = ap.parse_args()
    if a.mode == 'package':
        return package(a.to)
    if a.mode == 'install':
        return install(a.src, a.to)
    return status(None, a.to)


if __name__ == '__main__':
    sys.exit(main())
