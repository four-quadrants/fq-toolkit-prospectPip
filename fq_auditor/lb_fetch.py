#!/usr/bin/env python3
"""Download a client's LaunchBay uploads into their intake folder.

    python3 lb_fetch.py <client folder> [--manifest path] [--dry-run]

HOW THIS FITS
LaunchBay's file list comes from the MCP connector, which lives in a Claude
session. The FILES do not: every upload has a direct filestack URL that needs no
authentication, so the documents are pulled straight from filestack to this
machine. Only the list of names and links passes through Claude.

    Claude session  ->  launchbay_manifest.json   (names, ids, urls)
    this script     ->  Original_sourcedocs/      (the actual documents)

WHAT IT WILL NOT DO
  * Re-download. Every file carries a LaunchBay file ID; ids already recorded in
    .lb_fetched.json are skipped, so running it twice costs nothing.
  * Overwrite. A name already taken gets a numbered suffix rather than clobbering
    what is there.
  * Fetch anything but client uploads. LaunchBay marks uploads as "collection";
    "signature" and "attachment" are forms and samples the firm sent OUT, and
    filing those back in as client documents would be wrong.

A NOTE ON THOSE URLS
They are unauthenticated and CDN-cached for a month. Anyone holding one can read
the document. Treat the manifest as sensitive as the documents themselves — it is
written inside the client folder for that reason, not somewhere general.
"""
import os
import re
import sys
import json
import time
import argparse
import urllib.request
import urllib.error

FETCHED = '.lb_fetched.json'
MANIFEST = os.path.join('_Audit', 'launchbay_manifest.json')
INTAKE = 'Original_sourcedocs'

# Only these are things the client uploaded. See module docstring.
#
# 'upload' was added after Oyler: his practice debt schedule was attached to the
# PROJECT rather than to a request task, and LaunchBay calls that kind 'upload'.
# Accepting only 'collection' skipped it — the one document the team was actively
# chasing him for. 'signature' and 'attachment' stay out: those are forms the
# firm sent OUT, and filing them back as client documents would be wrong.
CLIENT_UPLOAD_TYPES = {'collection', 'upload'}

# An 'attachment' is usually a form the firm sent out, but a client who posts
# a file with a portal comment gets the same label (a prospect's land purchase
# agreement, the one document an item asked for). The firm's own attachments
# are a short, known set of templates and examples; anything else attached is
# taken as the client's.
FIRM_ATTACHMENT = re.compile(r'example|template|privacy principles|ach form|'
                             r'document request|request list|engagement letter|'
                             r'planning agreement|file checklist|four quadrants',
                             re.I)


def _is_client_file(f):
    kind = f.get('kind') or 'collection'
    if kind in CLIENT_UPLOAD_TYPES:
        return True
    return kind == 'attachment' and not FIRM_ATTACHMENT.search(f.get('name') or '')


def load_json(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def safe_name(name):
    """Keep the client's filename, minus anything that breaks a path."""
    name = re.sub(r'[/\\:*?"<>|]', '-', name or 'untitled')
    name = re.sub(r'\s+', ' ', name).strip(' .')
    return name or 'untitled'


def unique_path(folder, name):
    """Never overwrite. "x.pdf" -> "x (2).pdf" if taken."""
    dest = os.path.join(folder, name)
    if not os.path.exists(dest):
        return dest
    stem, ext = os.path.splitext(name)
    n = 2
    while os.path.exists(os.path.join(folder, '%s (%d)%s' % (stem, n, ext))):
        n += 1
    return os.path.join(folder, '%s (%d)%s' % (stem, n, ext))


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest, timeout=120):
    req = urllib.request.Request(url, headers={'User-Agent': 'fq-intake/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise IOError('HTTP %s' % r.status)
        tmp = dest + '.part'
        with open(tmp, 'wb') as fh:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
        os.replace(tmp, dest)          # only appears complete, never half-written
    return os.path.getsize(dest)


def fetch(client_folder, manifest_path=None, dry_run=False, quiet=False):
    client_folder = os.path.abspath(os.path.expanduser(client_folder))
    # Be forgiving about which folder we were handed. The manifest lives in the
    # CLIENT folder, but the app's folder picker points at the documents folder
    # inside it, and an operator choosing by hand may pick either. Given
    # Original_sourcedocs, step up rather than fail with "no manifest" while the
    # manifest sits one level away.
    if not manifest_path and not os.path.exists(os.path.join(client_folder, MANIFEST)):
        parent = os.path.dirname(client_folder)
        if os.path.exists(os.path.join(parent, MANIFEST)):
            client_folder = parent
    manifest_path = manifest_path or os.path.join(client_folder, MANIFEST)
    if not os.path.exists(manifest_path):
        legacy = os.path.join(client_folder, os.path.basename(MANIFEST))
        if os.path.exists(legacy):
            manifest_path = legacy
    intake = os.path.join(client_folder, INTAKE)
    state_path = os.path.join(client_folder, FETCHED)

    man = load_json(manifest_path, None)
    if not man:
        print("No document list for this client yet (looked for %s).\n"
              "To get one, open Claude and say: pull this client from LaunchBay." % MANIFEST)
        return 1

    files = man.get('files') or []
    state = load_json(state_path, {})
    os.makedirs(intake, exist_ok=True)

    todo, skipped_seen, skipped_kind = [], 0, 0
    for f in files:
        if not _is_client_file(f):
            skipped_kind += 1
            continue
        fid = str(f.get('id') or f.get('url') or '')
        if fid and fid in state:
            skipped_seen += 1
            continue
        # The id log is the fast path, but it is a file and files get lost — a
        # folder is copied to the server, the state is reset, a second operator
        # runs this. Falling through to a download would then write
        # "Insurance_Plan_Mix consolidated (2).xlsx" beside the original, and
        # the auditor would dutifully classify and file both. So check the disk
        # too: same name, same size means we already have it.
        here = os.path.join(intake, safe_name(f.get('name')))
        if os.path.exists(here) and (not f.get('bytes')
                                     or abs(os.path.getsize(here) - int(f['bytes'])) < 2048):
            state[fid] = {'name': os.path.basename(here),
                          'bytes': os.path.getsize(here),
                          'fetched': 'found already on disk'}
            skipped_seen += 1
            continue
        todo.append(f)

    save_json(state_path, state)   # persist anything recognised on disk above

    if not quiet:
        print("Project : %s" % (man.get('project') or '?'))
        print("Manifest: %d file(s) — %d already here, %d not client uploads"
              % (len(files), skipped_seen, skipped_kind))
        print("To fetch: %d" % len(todo))
        if dry_run:
            for f in todo:
                print("   would fetch  %s" % f.get('name'))
            print("\nNothing downloaded (dry run).")
            return 0

    # Same content, different name. Once the toolkit has renamed a document
    # ("Personal - Debt - Scan ...pdf"), neither the id log (if it was lost or
    # predates the file) nor the name check above recognises it, and a re-pull
    # wrote a second copy beside it. Oyler, 23 October: 22 of 23 "new" files
    # were copies of documents already here. So hash what is already on disk
    # and drop a download whose content matches.
    have = {}
    if todo:
        for n in os.listdir(intake):
            p = os.path.join(intake, n)
            if n.startswith('.') or not os.path.isfile(p):
                continue
            try:
                have.setdefault(sha256_file(p), n)
            except Exception:
                pass

    got, dupes, failed = 0, [], []
    for f in todo:
        name = safe_name(f.get('name'))
        dest = unique_path(intake, name)
        try:
            size = download(f['url'], dest)
            digest = sha256_file(dest)
            if digest in have:
                os.remove(dest)
                state[str(f.get('id') or f['url'])] = {
                    'name': have[digest], 'bytes': size,
                    'fetched': 'already here as %s' % have[digest]}
                save_json(state_path, state)
                dupes.append((name, have[digest]))
                if not quiet:
                    print("   already here  %-52s (as %s)" % (name[:52], have[digest][:50]))
                continue
            have[digest] = os.path.basename(dest)
            state[str(f.get('id') or f['url'])] = {
                'name': os.path.basename(dest),
                'bytes': size,
                'fetched': time.strftime('%Y-%m-%d'),
            }
            save_json(state_path, state)      # after each file, so a crash resumes
            got += 1
            if not quiet:
                print("   fetched  %-58s %6.1f KB" % (os.path.basename(dest)[:58], size / 1024.0))
        except Exception as e:
            failed.append((name, str(e)))
            # Remember the failure, separately from the successes. Without this
            # a document that CANNOT be downloaded is indistinguishable from one
            # that has not been downloaded yet: the app counts it as still
            # waiting, the Audit button stays grey, and pressing Download again
            # produces the same silence. Three of Oyler's files are .html that
            # the CDN will not serve, and nothing on screen said so.
            fails = state.setdefault('__failed__', {})
            fails[str(f.get('id') or f['url'])] = {
                'name': name, 'why': str(e)[:200],
                'tried': time.strftime('%Y-%m-%d %H:%M'),
            }
            save_json(state_path, state)
            if not quiet:
                print("   FAILED   %-58s %s" % (name[:58], e))

    if not quiet:
        print("\n%d new document(s) in %s" % (got, intake))
        if dupes:
            print("%d were already here under another name, so no copy was kept."
                  % len(dupes))
        if failed:
            print("%d could not be fetched:" % len(failed))
            for n, e in failed:
                print("   - %s (%s)" % (n, e))
        if got:
            print("\nRun the audit — the new documents will be picked up.")
    return 0 if not failed else 2


def main():
    ap = argparse.ArgumentParser(description="Pull a client's LaunchBay uploads into their intake folder")
    ap.add_argument('folder', help="the client folder (the one holding Original_sourcedocs)")
    ap.add_argument('--manifest', default=None, help="manifest path (default: <folder>/%s)" % MANIFEST)
    ap.add_argument('--dry-run', action='store_true', help="list what would be fetched, download nothing")
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    if not os.path.isdir(a.folder):
        sys.exit("Not a folder: %s" % a.folder)
    sys.exit(fetch(a.folder, a.manifest, a.dry_run, a.quiet))


if __name__ == '__main__':
    main()
