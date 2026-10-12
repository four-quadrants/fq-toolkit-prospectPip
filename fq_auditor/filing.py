"""Filing — copy the client's documents into the tree, renaming on the way.

This is the only part of the toolkit that changes anything on disk, so the rules
are deliberately conservative:

  * DRY RUN BY DEFAULT. Nothing is written unless the caller explicitly says so.
  * COPIES, NEVER MOVES. Original_sourcedocs stays exactly as the client sent it.
  * NOTHING IS OVERWRITTEN. A name already taken means the copy is refused and
    flagged, not silently resolved.
  * EVERY COPY IS RECORDED, in the ledger and the filing log, keyed by the
    original's content hash, so a filed document can always be traced back to
    the file the client actually sent — even after it is renamed.

WHY ORIGINALS RATHER THAN REDACTED COPIES
This used to refuse any document without a redacted counterpart. That made sense
when the plan was to redact first and audit second, but the auditor runs locally
and offline against files already on this machine, so redacting first buys no
security — it only costs four times the OCR and destroys the account tails the
filing tree is organised by. The redactor is now an export step for anything
leaving the building, not a gate in front of filing.

WHY COPIES RATHER THAN MOVES
Because people mislabel things. When a document turns out to be filed wrongly,
the untouched flat archive is what you go back to, and it is also the only record
of what actually arrived. The cost is duplicate storage; the benefit is that no
filing mistake is ever destructive.
"""
import os
import shutil


def strip_redacted_suffix(name):
    """"Arvest Free Blue April (redacted).pdf" -> "Arvest Free Blue April.pdf"."""
    stem, ext = os.path.splitext(name or '')
    stem = stem.replace(' (redacted)', '').replace('(redacted)', '').strip()
    return (stem + ext) if stem else name


def _same_file(a, b):
    """Byte-for-byte identical? Size first, so most comparisons cost nothing."""
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        import hashlib
        def digest(p):
            h = hashlib.sha256()
            with open(p, 'rb') as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b''):
                    h.update(chunk)
            return h.hexdigest()
        return digest(a) == digest(b)
    except OSError:
        return False


class Move:
    """One proposed copy, and whether it is allowed to happen.

    Still called Move for the callers' sake; nothing is moved.
    """

    def __init__(self, sha, src, dest_dir, dest_name, source_label):
        self.sha = sha
        self.src = src                      # the original we would copy
        self.dest_dir = dest_dir
        self.dest_name = dest_name
        self.source_label = source_label    # the original's name, for the log
        self.blocked = None                 # why not, if refused

    @property
    def dest(self):
        return os.path.join(self.dest_dir, self.dest_name)

    def as_row(self):
        return {'sha': self.sha, 'from': self.source_label, 'src': self.src,
                'to': self.dest, 'blocked': self.blocked}


def plan_moves(plan, client_folder, src_folder, led=None, review_dir='_Needs Review'):
    """Work out what would be copied where. Nothing touches the disk here.

    `plan` is what build_plan produced. `src_folder` is the flat archive the
    documents arrived in — normally Original_sourcedocs — and every source path
    is resolved inside it.
    """
    import ledger as _ledger
    moves, skipped = [], []

    for p in plan:
        sha = p.get('sha')
        name = p.get('file') or ''

        if led is not None and _ledger.is_filed(led, sha):
            skipped.append((name, 'already filed'))
            continue

        src = p.get('path') or os.path.join(src_folder, name)

        dest_rel = p.get('dest') or review_dir
        dest_dir = os.path.join(client_folder, dest_rel)
        # "(redacted)" is stripped if it is there — the tree holds originals now,
        # so the suffix would be a lie as well as noise.
        dest_name = p.get('new_name') or strip_redacted_suffix(name)

        m = Move(sha, src, dest_dir, dest_name, name)

        if not src or not os.path.exists(src):
            m.blocked = 'the file is not where the audit found it'
        elif os.path.abspath(src) == os.path.abspath(m.dest):
            m.blocked = 'source and destination are the same file'
        elif os.path.exists(m.dest):
            # A file of that name is already there. If it is byte-for-byte the
            # SAME document, this was filed on an earlier pass and the ledger
            # has simply lost track — a folder was copied, a ledger was reset,
            # another operator ran it. Treat it as done rather than refusing:
            # 62 alarming "refused" lines for documents already correctly filed
            # trains people to ignore the refusals that matter.
            #
            # A DIFFERENT document under the same name is a real collision and
            # is still refused, because that is the case where filing would
            # destroy something.
            if _same_file(src, m.dest):
                if led is not None:
                    _ledger.record_filed(led, sha, dest_rel, dest_name)
                skipped.append((name, 'already filed — identical copy in place'))
                continue
            m.blocked = 'a different document of that name is already there'
        moves.append(m)

    return moves, skipped


def apply_rename_plan(plan, csv_path):
    """Overlay a reviewed rename plan onto the audit's filing plan.

    The audit decides where a document goes from its own classification. Where
    Claude read the document and proposed a folder and a name, and a person has
    left that proposal standing, it wins: it was made with the page in front of
    it rather than from a rule.

    A row whose collision is still unresolved is skipped entirely. Those are
    the cases where two documents wanted one name and nothing in either
    filename told them apart, and filing either one would destroy the other.
    """
    import csv as _csv
    try:
        with open(csv_path) as fh:
            rows = {r['sha']: r for r in _csv.DictReader(fh) if r.get('sha')}
    except (OSError, KeyError, ValueError):
        return plan, 0

    applied = 0
    for p in plan:
        row = rows.get(p.get('sha'))
        if not row:
            continue
        if str(row.get('collision', '')).startswith('UNRESOLVED'):
            continue
        if row.get('rejected', '').strip():
            continue                       # a person struck this one out
        if row.get('proposed_folder'):
            p['dest'] = row['proposed_folder']
        if row.get('proposed_name'):
            p['new_name'] = row['proposed_name']
        applied += 1
    return plan, applied


def execute(moves, led=None, dry_run=True, client_folder=None):
    """Copy everything that is not blocked. Returns (done, refused).

    With dry_run left True — the default — this reports what it would do and
    changes nothing.
    """
    import ledger as _ledger
    done, refused = [], []

    for m in moves:
        if m.blocked:
            refused.append(m)
            continue
        if dry_run:
            done.append(m)
            continue
        try:
            os.makedirs(m.dest_dir, exist_ok=True)
            # Re-check immediately before writing: the plan may have been made
            # minutes ago, and two documents in one run can want the same name.
            if os.path.exists(m.dest):
                m.blocked = 'a file of that name appeared before the copy'
                refused.append(m)
                continue
            # copy2 keeps the timestamps, so the tree still shows when a
            # document actually arrived rather than when it was filed.
            shutil.copy2(m.src, m.dest)
            if led is not None:
                where = m.dest_dir
                if client_folder:
                    try:
                        where = os.path.relpath(m.dest_dir, start=client_folder)
                    except ValueError:
                        pass
                _ledger.record_filed(led, m.sha, where, m.dest_name)
            done.append(m)
        except Exception as e:
            m.blocked = 'could not copy it: %s' % e
            refused.append(m)
    return done, refused


def report(moves, skipped, done, refused, dry_run=True):
    """Plain-language account of what happened, or would happen."""
    L = []
    verb = 'would be filed' if dry_run else 'filed'
    L.append('%d document(s) %s.' % (len(done), verb))
    if done and not dry_run:
        L.append('Originals are untouched — everything above was copied.')
    if skipped:
        L.append('%d skipped — already filed on an earlier pass.' % len(skipped))
    if refused:
        L.append('')
        L.append('%d refused:' % len(refused))
        by_reason = {}
        for m in refused:
            by_reason.setdefault(m.blocked, []).append(m.source_label)
        for reason, files in sorted(by_reason.items(), key=lambda x: -len(x[1])):
            L.append('  %s (%d)' % (reason, len(files)))
            for f in sorted(files)[:8]:
                L.append('      - %s' % f)
            if len(files) > 8:
                L.append('      … and %d more' % (len(files) - 8))
    if dry_run:
        L.append('')
        L.append('Nothing has been copied. Re-run with filing turned on to carry this out.')
    return L


def build_move_log(done, refused):
    rows = ['action,original_name,filed_to,sha256,note']
    for m in done:
        rows.append(','.join('"%s"' % str(x or '').replace('"', "'") for x in
                             ['filed', m.source_label, m.dest, m.sha, '']))
    for m in refused:
        rows.append(','.join('"%s"' % str(x or '').replace('"', "'") for x in
                             ['refused', m.source_label, m.dest, m.sha, m.blocked]))
    return '\n'.join(rows) + '\n'
