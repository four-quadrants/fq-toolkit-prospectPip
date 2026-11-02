#!/usr/bin/env python3
"""Text out of an Apple Pages or Keynote file, with nothing installed.

    python3 iwork.py "Consult offer call summary-otter.pages"

WHY
The Otter call summaries arrive as .pages files, and they carry what no
financial document does: the client's stated needs, objections, who decides,
what they are worried about. The toolkit listed them as unreadable.

HOW
A .pages file is a zip. The words live in Index/Document.iwa, which is a
series of Snappy-compressed chunks of protobuf. The text runs are stored as
plain UTF-8 inside the protobuf, so decompressing and pulling out the long
readable runs recovers the document's words in order, without needing a
protobuf schema. Formatting is lost, which is fine: it is read, not printed.
"""
import re
import sys
import zipfile


def _snappy(b):
    """Raw Snappy decompression (no framing), enough for iWork chunks."""
    i = n = shift = 0
    while True:
        c = b[i]
        i += 1
        n |= (c & 0x7f) << shift
        shift += 7
        if c < 0x80:
            break
    out = bytearray()
    while i < len(b):
        tag = b[i]
        i += 1
        kind = tag & 3
        if kind == 0:
            ln = tag >> 2
            if ln >= 60:
                k = ln - 59
                ln = int.from_bytes(b[i:i + k], 'little')
                i += k
            ln += 1
            out += b[i:i + ln]
            i += ln
            continue
        if kind == 1:
            ln = ((tag >> 2) & 7) + 4
            off = ((tag >> 5) << 8) | b[i]
            i += 1
        elif kind == 2:
            ln = (tag >> 2) + 1
            off = int.from_bytes(b[i:i + 2], 'little')
            i += 2
        else:
            ln = (tag >> 2) + 1
            off = int.from_bytes(b[i:i + 4], 'little')
            i += 4
        for _ in range(ln):
            out.append(out[-off])
    return bytes(out)


def _iwa(data):
    out, i = bytearray(), 0
    while i + 4 <= len(data):
        ln = int.from_bytes(data[i + 1:i + 4], 'little')
        out += _snappy(data[i + 4:i + 4 + ln])
        i += 4 + ln
    return bytes(out)


RUN = re.compile(rb'[\x09\x0a\x20-\x7e\xc2-\xf4][\x09\x0a\x20-\x7e\x80-\xbf\xc2-\xf4]{19,}')


PROSE = re.compile('[\\t\\n\\x20-\\x7e\\u00a0-\\u00ff\\u2010-\\u2027\\u202f]{20,}')


def text_of(path):
    """The readable text of a .pages or .key file, in document order."""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.startswith('Index/')
                 and n.endswith('.iwa') and ('Document' in n or 'Slide' in n)]
        blobs = [_iwa(z.read(n)) for n in sorted(names)]
    out, seen = [], set()
    for blob in blobs:
        # Runs of readable text in the decoded blob. Matching on raw bytes
        # glued Otter's summary onto a block of binary table data that happens
        # to be valid UTF-8, and the letter filter then threw the whole summary
        # away (Weiler's call notes read as empty).
        for run in PROSE.findall(blob.decode('utf-8', 'ignore')):
            s = run.strip()
            # A protobuf length byte can land on '$' or '*' just before the
            # text ("$Seth Weiler initial call ..."); style names start with
            # '$' and a lower-case word, and stay filtered below.
            s = re.sub(r'^[$*](?=[A-Z])', '', s)
            letters = sum(ch.isalpha() for ch in s)
            if len(s) < 20 or letters < 0.55 * len(s) or s in seen:
                continue
            # Real prose has words; protobuf filler is one character repeated.
            if s.count(' ') < 2 or len(set(s)) < 10:
                continue
            if s.startswith('$') or 'paragraphstyle' in s or 'liststyle' in s:
                continue                          # style names, not words
            seen.add(s)
            out.append(s)
    return '\n'.join(out)


if __name__ == '__main__':
    print(text_of(sys.argv[1]))
