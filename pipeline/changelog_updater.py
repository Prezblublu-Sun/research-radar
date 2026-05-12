"""Auto-maintained CHANGELOG. Detects changes between today's config and
the most recent manifest's config, then prepends a dated entry to CHANGELOG.md."""

from __future__ import annotations
import pathlib
import yaml

DEFAULT_HEADER = """# CHANGELOG

This file is automatically updated whenever `config/directions.yaml` or
`prompts/scorer_*.txt` change between daily runs. Manual edits below the
auto-update marker are preserved.

<!-- AUTO-UPDATE-BELOW -->
"""


def _load_yaml_or_empty(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _diff_directions(old: dict, new: dict) -> list[str]:
    lines: list[str] = []
    old_dirs = (old.get("directions") or {})
    new_dirs = (new.get("directions") or {})

    added = set(new_dirs) - set(old_dirs)
    removed = set(old_dirs) - set(new_dirs)
    common = set(old_dirs) & set(new_dirs)

    for d in sorted(added):
        lines.append(f"- direction added: `{d}`")
    for d in sorted(removed):
        lines.append(f"- direction removed: `{d}`")

    for d in sorted(common):
        old_d = old_dirs[d]
        new_d = new_dirs[d]
        for field in ("strong_keywords", "must_pair_with", "llm_prompt_focus"):
            o = old_d.get(field)
            n = new_d.get(field)
            if o == n:
                continue
            if isinstance(o, list) and isinstance(n, list):
                added_items = [x for x in n if x not in o]
                removed_items = [x for x in o if x not in n]
                if added_items:
                    lines.append(f"- `{d}.{field}` added: {added_items}")
                if removed_items:
                    lines.append(f"- `{d}.{field}` removed: {removed_items}")
            else:
                lines.append(f"- `{d}.{field}` changed")

        o_src = old_d.get("sources", {}) or {}
        n_src = new_d.get("sources", {}) or {}
        for field in ("arxiv_categories", "openalex_keywords", "openalex_concepts", "pubmed_terms"):
            o = o_src.get(field, [])
            n = n_src.get(field, [])
            if o != n:
                a = [x for x in n if x not in o]
                r = [x for x in o if x not in n]
                if a:
                    lines.append(f"- `{d}.sources.{field}` added: {a}")
                if r:
                    lines.append(f"- `{d}.sources.{field}` removed: {r}")

    o_excl = old.get("exclusions", {}) or {}
    n_excl = new.get("exclusions", {}) or {}
    for field in ("hard_exclude_if_only_about", "ambiguous_terms_require_pairing"):
        o = o_excl.get(field, [])
        n = n_excl.get(field, [])
        if o != n:
            a = [x for x in n if x not in o]
            r = [x for x in o if x not in n]
            if a:
                lines.append(f"- `exclusions.{field}` added: {a}")
            if r:
                lines.append(f"- `exclusions.{field}` removed: {r}")

    return lines


def update_changelog(
    *,
    today: str,
    config_path: pathlib.Path,
    last_config_snapshot: pathlib.Path | None,
    prompt_path: pathlib.Path,
    last_prompt_hash: str | None,
    new_prompt_hash: str,
    changelog_path: pathlib.Path,
    run_id: str,
    counts: dict,
) -> bool:
    new_cfg = _load_yaml_or_empty(config_path)
    old_cfg = _load_yaml_or_empty(last_config_snapshot) if last_config_snapshot else {}
    cfg_lines = _diff_directions(old_cfg, new_cfg)

    prompt_changed = (last_prompt_hash is not None and last_prompt_hash != new_prompt_hash)

    if not cfg_lines and not prompt_changed:
        return False

    entry = [f"## {today} (run {run_id})", ""]
    entry.append(f"Counts: fetched={counts.get('fetched',0)}, "
                 f"after_dedup={counts.get('after_dedup',0)}, "
                 f"after_routing={counts.get('after_routing',0)}, "
                 f"High={counts.get('priority_counts',{}).get('High',0)}, "
                 f"Medium={counts.get('priority_counts',{}).get('Medium',0)}")
    entry.append("")
    if prompt_changed:
        entry.append(f"- scorer prompt changed: file=`{prompt_path.name}`, "
                     f"hash {last_prompt_hash} -> {new_prompt_hash}")
    entry.extend(cfg_lines)
    entry.append("")
    entry_text = "\n".join(entry)

    if not changelog_path.exists():
        changelog_path.write_text(DEFAULT_HEADER + "\n" + entry_text)
        return True

    content = changelog_path.read_text()
    marker = "<!-- AUTO-UPDATE-BELOW -->"
    if marker in content:
        head, tail = content.split(marker, 1)
        new_content = head + marker + "\n\n" + entry_text + tail
    else:
        new_content = entry_text + "\n\n" + content
    changelog_path.write_text(new_content)
    return True


def save_config_snapshot(config_path: pathlib.Path, snapshot_path: pathlib.Path) -> None:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(config_path.read_text())
