# How the tool learns

*A handoff page. No technical background assumed.*

---

## The problem this solves

A prospect sends us fifty or sixty documents. Someone has to open each one, work
out what it is, and put it in the right folder. Filenames are no help, because a
client can call a file anything at all.

Today the tool does that with rules we wrote by hand: *if the text near the top
mentions Form 1120-S, it is a business tax return.* There are about 1,600 lines
of rules like that. They work until a new client files something in a shape
nobody anticipated, and then somebody has to write another rule.

Instead, the tool now asks an AI model to read the document and say what it is.
No rules. When a new client sends something unusual, it just reads it.

---

## What gets written down, and where

Every time the tool decides what a document is, it writes that decision down in
two places.

### 1. In the client's own folder

So it never asks the same question twice.

```
<client folder>/.fq_cache/classify/
```

Run that client again next month and every document already seen is answered
instantly, with exactly the same answer as last time. Only genuinely new
documents get looked at. Nothing is re-asked, and nothing drifts.

The file is named after the document's own fingerprint, not its filename. If a
client re-sends the same statement under a different name, it is recognised as
the same document. If they send a corrected version, the fingerprint changes and
it gets read fresh.

### 2. In one running list on the Analysis share

```
_corpus/classifications.jsonl
```

One line per document. Every client. Kept forever.

This is the record of how this firm actually files things.

---

## What each line holds

| | |
|---|---|
| **Which file** | Name, folder, and fingerprint |
| **What it decided** | Document type, whose it is, which year, which account |
| **Why** | The sentence in the document it based that on |
| **Which model, and when** | So we can tell later whether a change in results came from a change in the model |
| **What the person changed it to** | If the reviewer overruled it |

---

## Why the last row is the important one

The model's own answers are not worth much as a record. They are guesses that
happened to be right.

The places where **a person overruled the model** are worth a great deal. That
is your team's judgement, written down: *this looked like a business statement
but it is personal*; *this belongs under Debt, not Investments*.

The review page already captures those corrections. This just keeps them.

---

## What that buys you later

After a few hundred documents you own a record of real filing decisions, made by
your own people, on your own clients' documents.

That is the thing you would use if you ever wanted to stop depending on an
outside service. You would train a small program on your own history, and it
would have learned from what your team actually did, rather than from rules
someone guessed at in advance.

It also gets better the more the tool is used, which the hand-written rules never
did.

---

## Three practical notes

**The list contains real client material.** Client names, account numbers,
snippets of document text. It lives on the Analysis share beside the client
folders, where that data already sits and is already backed up. It must never go
into the code repository.

**The model is asked one kind of question only.** What a document is, and
whether it satisfies a checklist item. It is never asked for a number. Every
figure that reaches a page is still read or calculated by code, checked against
a second source, and carries its own record of where it came from.

**Nothing is filed without a person seeing it.** The review page is unchanged.
The model proposes; the specialist decides. The corrections are the point.

---

## If you are picking this up cold

1. Look at `_corpus/classifications.jsonl` on the Analysis share. One line per
   document. Open it in any text editor.
2. Look at a client's `.fq_cache/classify/` folder. Same records, that client
   only.
3. Delete either one and nothing breaks. The tool re-reads the documents and
   writes them again. The cache is a saving, not a dependency.

That last point is worth keeping true. If the caches ever become something the
tool cannot run without, something has gone wrong.
