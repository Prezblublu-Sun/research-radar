# ADR-0032: Reading marks become repository data

**Status**: Accepted (2026-09-22), first stage implemented
**Supersedes**: ADR-0016 §4 "Out of scope" — multi-device mark sync,
server-side state, direct write-back to git from the browser
**Related**: ADR-0016 (curation UI), ADR-0028 (disposable Pages artifact),
SCOPE.md § Allowed, CLAUDE.md §4 (data-integrity guardrails)

## Context

ADR-0016 deliberately kept marks and notes in one browser: "zero backend work
in exchange for fully ephemeral state", with multi-device sync, server-side
state and browser-to-git write-back all listed out of scope. It also noted
that "if a future ADR upgrades this to a sync backend, the localStorage schema
is forward-compatible".

Two things changed. The user asked for a daily digest of the papers they
marked 待阅读, which a server job cannot assemble from browser-only state; and
they want the marks to seed a human-curated library and a page built on it,
which needs history and durability rather than ephemerality. Both require the
marks to leave the browser.

## The credential problem

The site is a static GitHub Pages artifact. For the browser to write to the
repository it needs a credential, and the only place to keep one is
`localStorage` — where anyone with access to that browser profile can read it.
That is a real cost for a convenience, and it is not the only option:

| Mechanism | Automatic | Credential in the browser |
|---|---|---|
| Fine-grained PAT held by the page | yes | yes |
| Pre-filled issue submitted with the reader's own GitHub session | no, one click | no |
| Manual export and commit | no | no |

## Decision

Adopt the middle row for the first stage. The library page packages the marks
and opens a pre-filled `marks-sync` issue; the reader submits it with the
GitHub session they already have; `.github/workflows/marks-sync.yml` validates
the body and commits it. No credential ever reaches the page.

1. **Storage.** One file per browser at `data/marks/<device>.json`
   (`schema_version`, `device`, `updated_at`, `marks` keyed by identity key).
   The per-mark shape is exactly ADR-0016's localStorage record, so the
   forward-compatibility that ADR promised holds.
2. **Merge.** `pipeline.marks_store.load_all` merges every device file;
   newest `at` wins, ties break on device name so the result is deterministic.
3. **Trust boundary.** The payload is pasted into a public issue, so
   `validate_payload` is strict and size-capped: known states only, ISO
   timestamps, identity keys matching the ADR-0031 prefixes, 5,000 marks and
   4,000 note characters per device, and a device name that cannot escape
   `data/marks/` — validated at full length rather than truncated to the cap,
   which would let two browsers collide on one file. The workflow additionally
   runs only for an issue the repository owner opened, and passes the body
   through an environment variable instead of interpolating it into a shell
   command.
4. **Serialisation.** The job joins the `research-radar-writer` concurrency
   group and pushes through `scripts/git_push_retry.sh`, like every other
   writer (ADR-0030).
5. **Honesty.** The page shows the payload in a textarea whatever happens and
   reports the real outcome of the clipboard copy. A payload too large for a
   URL still gets a submit link, just unfilled. Nothing claims a step the page
   cannot observe — the correction that ADR-0016's mail addendum already had
   to make.

## Consequences

- Marks gain git history, cross-device merge and a server-side reader; the
  daily digest and any curated-library page can be built on `data/marks/`.
- Sync happens when the reader chooses, not continuously. A digest reflects
  the last sync, not the live browser. Any mechanism short of a held
  credential has this property.
- `data/marks/` records what the user wants to read, in a public repository.
  The content is paper metadata already public on the site; the new signal is
  the preference itself. The user accepted this when asking for the feature.
- ADR-0016's "no sync, no server-side state" line in SCOPE.md § Allowed is
  amended in the same commit, as ADR-0016 itself amended SCOPE.md.

## Not in this stage

- The daily digest that reads `data/marks/` and mails it (next stage; the
  sender will be a GitHub issue notification, not SMTP).
- A curated-library page built from the marks.
- Continuous background sync with a held token. Available later as a drop-in
  replacement for the hand-off step; the storage layer and everything above
  it would not change.

## Rollback

Delete the workflow and the library panel; `data/marks/` becomes inert data
and the browser keeps working exactly as it did under ADR-0016. No corpus
record is touched by this ADR.

## Addendum 2026-09-24 — tombstones

The first cut could not express "I cleared this mark". The browser deleted
the localStorage key and `validate_payload` dropped any mark with neither
state nor note, so a clear was an *absence* — and an absence loses a merge
against a device that still holds the old mark. Clearing 忽略 on the laptop
would have been undone by the desktop the next time the digest read
`data/marks/`.

A cleared mark is now a record with an empty state and a timestamp. It takes
part in the merge like any other, and `load_all` drops tombstones only after
the merge has finished, so a clear beats an older mark and a newer mark beats
an older clear. The browser keeps the key rather than deleting it, and the
reading list and the library listing both skip tombstones so nothing blank
appears in the trail. Files written before this change still load: a missing
key is simply a key nobody has an opinion about.

Verified end to end on issue #35 before this addendum: the workflow validated
the payload, committed `data/marks/dev-e2etest1.json`, commented and closed.
That run also showed the trigger firing twice, because creating an issue with
a label emits both `opened` and `labeled`; the workflow now listens for
`opened` only.

## Addendum 2026-09-24 — the digest (implemented)

This ADR's first motivation was "a daily digest of the papers they marked
待阅读". `scripts/marks_digest.py` plus `.github/workflows/marks-digest.yml`
are that job, and the delivery question it had left open is settled the same
way the sync settled the credential question: use GitHub's own notifications
rather than a mail server.

**One standing issue**, labelled `marks-digest` and assigned to the owner:

* its **body** is rewritten every run with the whole current 待阅读 list.
  Editing an issue body sends no notification, so the live list is free.
* a **comment** is posted only when papers appeared since the last run.
  A comment does notify, and that notification — GitHub → the owner's
  registered address → their 163 inbox — is the mail that was asked for.
* nothing new means no comment, no mail, and a silent run.

No SMTP server, no mail credential, nothing in the repository that could
leak an address that is not already the owner's GitHub account.

**"New" is a set difference, not a timestamp.** `data/digest/to-read.json`
remembers the identity keys that were 待阅读 at the last run; the next run
reports `current − previous`. A timestamp watermark would have re-reported
any paper whose note was edited, because ADR-0034 moves `at` on every write.
The state is bounded by the list itself and self-prunes: a paper that leaves
待阅读 and comes back is reported again, which is right.

The watermark is committed **after** the comment is posted. If the job dies
in between, the next run repeats a paper — the failure worth having, against
one that silently swallows it.

Papers that *left* the list are deliberately never named in a comment. A
silent run still advances the watermark, so the departures a comment could
report are an arbitrary slice of the ones since the last run: an accurate
number that reads as a wrong one.

Mark fields are browser-supplied free text that passed only a length check
at the ADR-0032 boundary, so `marks_digest.py` escapes everything it
interpolates into Markdown and percent-encodes link targets (a DOI with
unbalanced parentheses would otherwise end the link early). Nothing from a
mark reaches a shell: the workflow passes `--body-file`, never a string.

`pages.yml` ignores `data/digest/**` for the same reason it ignores
`data/marks/**` — remove both when a published page starts rendering them.

