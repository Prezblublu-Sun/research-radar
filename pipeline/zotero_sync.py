"""Zotero sync: push papers into Zotero, one collection per direction.
Items are tagged with LLM-generated tags + priority. Uses pyzotero."""

from __future__ import annotations
import os
import json
import pathlib
from pyzotero import zotero

ZOT_USER_ID = os.environ.get("ZOTERO_USER_ID", "")
ZOT_API_KEY = os.environ.get("ZOTERO_API_KEY", "")
ZOT_LIBRARY_TYPE = os.environ.get("ZOTERO_LIBRARY_TYPE", "user")

COLLECTION_MAP = {
    "ai_bioprinting": os.environ.get("ZOT_COL_BIOPRINTING", ""),
    "hip_implant":    os.environ.get("ZOT_COL_HIP", ""),
    "fea_surrogate":  os.environ.get("ZOT_COL_FEA", ""),
    "am_biomedical":  os.environ.get("ZOT_COL_AM", ""),
}


def _get_client():
    if not ZOT_USER_ID or not ZOT_API_KEY:
        raise RuntimeError("ZOTERO_USER_ID and ZOTERO_API_KEY must be set")
    missing_cols = [k for k, v in COLLECTION_MAP.items() if not v]
    if missing_cols:
        raise RuntimeError(
            f"Missing ZOT_COL_* env vars for directions: {missing_cols}. "
            "Set them all, or items will silently go to library root."
        )
    return zotero.Zotero(ZOT_USER_ID, ZOT_LIBRARY_TYPE, ZOT_API_KEY)


def _to_zotero_item(paper: dict) -> dict:
    llm = paper.get("llm", {})
    priority = llm.get("priority", "Low")
    direction = paper.get("direction", "")

    tags = [
        {"tag": f"Priority_{priority}"},
        {"tag": f"Direction_{direction}"},
        {"tag": f"Source_{paper.get('source', '')}"},
    ]
    for t in llm.get("tags", []):
        tags.append({"tag": t})

    flags = llm.get("flags", {})
    if flags.get("has_experimental_validation"):
        tags.append({"tag": "Flag_ExperimentalValidation"})
    if flags.get("has_uncertainty_quantification"):
        tags.append({"tag": "Flag_UQ"})
    if flags.get("is_patient_specific"):
        tags.append({"tag": "Flag_PatientSpecific"})

    creators = []
    for full_name in paper.get("authors", []):
        if not full_name:
            continue
        bits = full_name.rsplit(" ", 1)
        if len(bits) == 2:
            creators.append({"creatorType": "author", "firstName": bits[0], "lastName": bits[1]})
        else:
            creators.append({"creatorType": "author", "name": full_name})

    summary = llm.get("summary_zh", {})
    note_blocks = [
        f"<p><b>Priority:</b> {priority} - {llm.get('priority_reason', '')}</p>",
        f"<p><b>Relevance:</b> {llm.get('relevance_to_user', '')}</p>",
        f"<p><b>动机:</b> {summary.get('motivation', '')}</p>",
        f"<p><b>方法:</b> {summary.get('method', '')}</p>",
        f"<p><b>结果:</b> {summary.get('result', '')}</p>",
        f"<p><b>验证:</b> {summary.get('validation', '')}</p>",
    ]
    extra_note = "\n".join(note_blocks)

    item = {
        "itemType": "journalArticle",
        "title": paper.get("title", ""),
        "creators": creators,
        "abstractNote": paper.get("abstract", "")[:2000],
        "publicationTitle": paper.get("venue", ""),
        "date": paper.get("date", ""),
        "DOI": paper.get("doi", ""),
        "url": paper.get("url", ""),
        "tags": tags,
        "extra": extra_note,
    }

    col_key = COLLECTION_MAP.get(direction)
    if col_key:
        item["collections"] = [col_key]

    return item


def sync(papers: list[dict], min_priority: str = "Medium") -> dict:
    import datetime as _dt
    rank = {"High": 3, "Medium": 2, "Low": 1, "Exclude": 0}
    threshold = rank[min_priority]

    eligible = [
        p for p in papers
        if rank.get(p.get("llm", {}).get("priority", "Low"), 0) >= threshold
    ]

    items = [_to_zotero_item(p) for p in eligible]

    zot = _get_client()
    created, failed = 0, 0

    # W1.2 audit log: one JSONL row per paper attempt
    audit_dir = pathlib.Path(__file__).resolve().parent.parent / "data" / "zotero_sync_log"
    audit_dir.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    audit_file = audit_dir / f"{today}.jsonl"
    audit_rows = []

    for i in range(0, len(items), 50):
        batch_papers = eligible[i:i+50]
        batch = items[i:i+50]
        try:
            resp = zot.create_items(batch)
            successful = resp.get("successful", {})
            failed_resp = resp.get("failed", {})
            created += len(successful)
            failed += len(failed_resp)

            for idx_in_batch, paper in enumerate(batch_papers):
                str_idx = str(idx_in_batch)
                if str_idx in successful:
                    item_key = successful[str_idx].get("key", "")
                    status = "created"
                    error = None
                elif str_idx in failed_resp:
                    item_key = ""
                    status = "failed"
                    error = str(failed_resp[str_idx])
                else:
                    item_key = ""
                    status = "unchanged_or_unknown"
                    error = None
                col_list = batch[idx_in_batch].get("collections", [])
                audit_rows.append({
                    "doi": paper.get("doi"),
                    "title": (paper.get("title") or "")[:120],
                    "priority": paper.get("llm", {}).get("priority"),
                    "direction": paper.get("direction"),
                    "target_collection": col_list[0] if col_list else None,
                    "item_key": item_key,
                    "status": status,
                    "error": error,
                })
        except Exception as e:
            failed += len(batch)
            print(f"Zotero batch {i} failed: {e}")
            for paper in batch_papers:
                audit_rows.append({
                    "doi": paper.get("doi"),
                    "title": (paper.get("title") or "")[:120],
                    "priority": paper.get("llm", {}).get("priority"),
                    "direction": paper.get("direction"),
                    "target_collection": None,
                    "item_key": "",
                    "status": "batch_exception",
                    "error": str(e),
                })

    with audit_file.open("a") as fh:
        for row in audit_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(audit_rows)} audit rows to {audit_file}")

    return {"eligible": len(eligible), "created": created, "failed": failed, "audit_file": str(audit_file)}


def list_collections_helper():
    """First-time setup helper: prints all your collections + keys."""
    zot = _get_client()
    cols = zot.collections()
    for c in cols:
        print(f"{c['data']['name']:40s}  key={c['key']}")
