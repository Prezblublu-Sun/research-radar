"""Synced reading marks — the durable half of ADR-0016's curation trail.

ADR-0016 kept marks in one browser on purpose ("zero backend work in exchange
for fully ephemeral state") and listed sync under "Out of scope". ADR-0032
reverses that: the marks are now the seed of a human-curated library, so they
need git history, cross-device merge, and a server-side reader for the daily
digest.

On-disk shape, one file per browser at ``data/marks/<device>.json``::

    {
      "schema_version": 1,
      "device": "dev-1a2b3c4d",
      "updated_at": "2026-09-22T12:00:00Z",
      "marks": {
        "<identity_key>": {
          "state": "to-read" | "read" | "interesting" | "ignore" | "",
          "at": "2026-09-22T11:00:00Z",
          "note": "free text",
          "title": "...", "date": "...",
          "direction": "...", "priority": "..."
        }
      }
    }

Payloads arrive pasted into a public GitHub issue, so :func:`validate_payload`
is deliberately strict and size-capped: it is a trust boundary, not a
convenience check. The workflow additionally refuses issues opened by anyone
other than the repository owner.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

SCHEMA_VERSION = 1

STATES = {"to-read", "read", "interesting", "ignore", ""}

# A device name becomes a filename, so it may not travel outside data/marks/.
DEVICE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")
# Identity keys are produced by render/identity.py: doi:/arxiv:/pmid:/openalex:
# or the renderer's noid:<hex> fallback.
IDENTITY_RE = re.compile(r"^(doi|arxiv|pmid|openalex|noid):[\x21-\x7e]{1,190}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

MAX_MARKS = 5000
MAX_NOTE = 4000
MAX_FIELD = 500


class MarksPayloadError(ValueError):
    """The pasted payload is not a well-formed marks file."""


def _clean(value, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise MarksPayloadError(f"expected a string, got {type(value).__name__}")
    text = value.replace("\r\n", "\n").strip()
    return text[:limit]


def validate_payload(data) -> dict:
    """Return a normalised payload, or raise :class:`MarksPayloadError`.

    Unknown top-level and per-mark keys are dropped rather than rejected so a
    newer browser bundle can add fields without breaking the sync.
    """
    if not isinstance(data, dict):
        raise MarksPayloadError("payload must be a JSON object")
    if int(data.get("schema_version") or 0) != SCHEMA_VERSION:
        raise MarksPayloadError(
            f"unsupported schema_version {data.get('schema_version')!r}; "
            f"this radar expects {SCHEMA_VERSION}"
        )
    # Deliberately not _clean()'d: truncating an over-long name to the cap
    # would accept it as a different, shorter device and let two browsers
    # collide on one file. Case is normalised, length is validated.
    raw_device = data.get("device")
    if not isinstance(raw_device, str):
        raise MarksPayloadError("device must be a string")
    device = raw_device.strip().lower()
    if not DEVICE_RE.match(device):
        raise MarksPayloadError(
            f"device {device!r} must match {DEVICE_RE.pattern}"
        )
    marks_in = data.get("marks")
    if not isinstance(marks_in, dict):
        raise MarksPayloadError("marks must be a JSON object keyed by identity")
    if len(marks_in) > MAX_MARKS:
        raise MarksPayloadError(
            f"{len(marks_in)} marks exceeds the {MAX_MARKS} cap"
        )

    marks: dict[str, dict] = {}
    for key, value in marks_in.items():
        if not isinstance(key, str) or not IDENTITY_RE.match(key):
            raise MarksPayloadError(f"not an identity key: {key!r}")
        if not isinstance(value, dict):
            raise MarksPayloadError(f"mark {key!r} must be an object")
        state = _clean(value.get("state"), 32)
        if state not in STATES:
            raise MarksPayloadError(f"mark {key!r} has unknown state {state!r}")
        at = _clean(value.get("at"), 40)
        if at and not ISO_RE.match(at):
            raise MarksPayloadError(f"mark {key!r} has a non-ISO timestamp {at!r}")
        note = _clean(value.get("note"), MAX_NOTE)
        if not state and not note and not at:
            continue  # no state, no note, no timestamp: nothing at all
        # `state: ""` with a timestamp is a tombstone: the reader cleared the
        # mark. It has to survive the round trip, because another device's
        # file may still hold the old mark and the merge needs something
        # newer to beat it with. load_all() drops tombstones after merging.
        marks[key] = {
            "state": state,
            "at": at,
            "note": note,
            "title": _clean(value.get("title"), MAX_FIELD),
            "date": _clean(value.get("date"), 32),
            "direction": _clean(value.get("direction"), 64),
            "priority": _clean(value.get("priority"), 32),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "device": device,
        "updated_at": _clean(data.get("updated_at"), 40) or utc_now(),
        "marks": marks,
    }


def utc_now() -> str:
    return (dt.datetime.now(dt.timezone.utc)
            .isoformat(timespec="seconds").replace("+00:00", "Z"))


def extract_payload(text: str) -> dict:
    """Pull the marks JSON out of an issue body.

    Accepts a fenced ```json block (what the page prefills) or a body that is
    nothing but the object. Anything else is a paste mistake worth reporting.
    """
    if not isinstance(text, str) or not text.strip():
        raise MarksPayloadError("the issue body is empty")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = fenced.group(1) if fenced else text.strip()
    if not raw.startswith("{"):
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise MarksPayloadError("no JSON object found in the issue body")
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise MarksPayloadError(f"payload is not valid JSON: {error}") from error


def device_path(data_root: pathlib.Path, device: str) -> pathlib.Path:
    if not DEVICE_RE.match(device):
        raise MarksPayloadError(f"refusing to write device {device!r}")
    return pathlib.Path(data_root) / "marks" / f"{device}.json"


def write_device(data_root: pathlib.Path, payload: dict) -> pathlib.Path:
    """Persist one validated device payload. Returns the path written."""
    path = device_path(data_root, payload["device"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                             sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def is_tombstone(mark: dict) -> bool:
    """A cleared mark: no state and no note left, only the time it happened."""
    return not mark.get("state") and not mark.get("note")


def load_all(data_root: pathlib.Path) -> dict[str, dict]:
    """Merge every device file into one identity -> mark mapping.

    Newest ``at`` wins; a tie falls back to the device name so the result is
    deterministic no matter what order the files are read in. Each returned
    mark carries the ``device`` it came from.

    Tombstones take part in the merge and are then dropped, so clearing a
    mark on one device removes it everywhere instead of being resurrected by
    a device that has not synced since.
    """
    merged: dict[str, dict] = {}
    marks_dir = pathlib.Path(data_root) / "marks"
    if not marks_dir.is_dir():
        return merged
    for path in sorted(marks_dir.glob("*.json")):
        try:
            payload = validate_payload(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue  # a corrupt device file must not break the digest
        device = payload["device"]
        for key, mark in payload["marks"].items():
            current = merged.get(key)
            if current is None or (mark.get("at", ""), device) > (
                    current.get("at", ""), current.get("device", "")):
                merged[key] = {**mark, "device": device}
    return {key: mark for key, mark in merged.items() if not is_tombstone(mark)}


def by_state(marks: dict[str, dict], state: str) -> list[tuple[str, dict]]:
    """Identity/mark pairs in one state, newest mark first."""
    chosen = [(key, mark) for key, mark in marks.items()
              if mark.get("state") == state]
    chosen.sort(key=lambda item: (item[1].get("at", ""), item[0]), reverse=True)
    return chosen
