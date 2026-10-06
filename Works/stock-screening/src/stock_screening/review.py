"""Step 2b: record review decisions, report progress, export lists for Lightroom.

<out>/<year>/review.csv is keyed by relpath, so decisions survive re-running
`select`/`sheets` (which may renumber tile IDs).
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from .config import Config

REVIEW_NAME = "review.csv"
REVIEW_FIELDS = ["relpath", "id", "decision", "flags", "note", "reviewed_at"]
DECISIONS = ("candidate", "review", "reject")
FLAGS = ("people", "logo", "text", "landmark", "artwork", "private", "focus", "noise",
         "similar", "composition")


def _path(cfg: Config, year: str) -> Path:
    return cfg.year_dir(year) / REVIEW_NAME


def load(cfg: Config, year: str) -> dict[str, dict[str, str]]:
    path = _path(cfg, year)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        return {row["relpath"]: row for row in csv.DictReader(fh)}


def _save(cfg: Config, year: str, rows: dict[str, dict[str, str]]) -> None:
    with open(_path(cfg, year), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for row in sorted(rows.values(), key=lambda r: (r.get("id") or "", r["relpath"])):
            writer.writerow({k: row.get(k, "") for k in REVIEW_FIELDS})


def parse_ids(spec: str) -> list[int]:
    """'1-4, 9,12' -> [1, 2, 3, 4, 9, 12]"""
    out: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            out.extend(range(lo, hi + 1))
        else:
            out.append(int(part))
    return out


def compress_ids(ids: list[int]) -> str:
    ids = sorted(set(ids))
    parts, i = [], 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[j] + 1:
            j += 1
        parts.append(f"{ids[i]}" if i == j else f"{ids[i]}-{ids[j]}")
        i = j + 1
    return ",".join(parts)


def mark(cfg: Config, year: str, ids: str, decision: str, flags: list[str], note: str) -> int:
    from .sheets import read_index

    if decision not in DECISIONS:
        print(f"error: decision must be one of {', '.join(DECISIONS)}")
        return 2
    bad_flags = [f for f in flags if f not in FLAGS]
    if bad_flags:
        print(f"error: unknown flag(s) {bad_flags}; allowed: {', '.join(FLAGS)}")
        return 2
    index = read_index(cfg, year)
    numbers = parse_ids(ids)
    unknown = [n for n in numbers if f"{n:04d}" not in index]
    if unknown:
        print(f"error: IDs not in the current sheets: {compress_ids(unknown)}")
        return 2
    rows = load(cfg, year)
    now = datetime.now().isoformat(timespec="seconds")
    for n in numbers:
        tile_id = f"{n:04d}"
        relpath = index[tile_id]["relpath"]
        rows[relpath] = {"relpath": relpath, "id": tile_id, "decision": decision,
                         "flags": ";".join(flags), "note": note, "reviewed_at": now}
    _save(cfg, year, rows)
    print(f"marked {len(numbers)} as {decision}: {compress_ids(numbers)}")
    return 0


def status(cfg: Config, year: str) -> int:
    from . import inventory, scan, selection, sheets

    items = inventory.list_year(cfg, year)
    cache = scan.load_cache(cfg, year)
    scanned = sum(1 for it in items if scan.is_fresh(cache.get(it.relpath), it))
    print(f"[status {year}]")
    print(f"  files            {len(items)}")
    print(f"  scanned          {scanned}" + ("" if scanned == len(items) else "  (run scan)"))
    try:
        screen = selection.read_screen(cfg, year)
        passed = [r for r in screen if r["status"] == "pass"]
        print(f"  screen pass      {len(passed)} / {len(screen)}")
    except FileNotFoundError:
        print("  screen           not run (run select)")
        return 0
    rows = load(cfg, year)
    counts = Counter(r["decision"] for r in rows.values())
    print("  reviewed         " + (", ".join(f"{d} {counts[d]}" for d in DECISIONS)))
    try:
        index = sheets.read_index(cfg, year)
    except FileNotFoundError:
        print("  sheets           not rendered (run sheets)")
        return 0
    pending = [int(i) for i, row in index.items() if row["relpath"] not in rows]
    n_sheets = len({row["sheet"] for row in index.values()})
    print(f"  sheets           {n_sheets} sheets, IDs 0001-{len(index):04d}")
    print(f"  not yet reviewed {len(pending)}" + (f"  IDs {compress_ids(pending)}" if pending else ""))
    return 0


def export(cfg: Config, year: str, decision: str, path_prefix: str | None) -> int:
    rows = [r for r in load(cfg, year).values() if r["decision"] == decision]
    rows.sort(key=lambda r: r["relpath"])
    out = cfg.year_dir(year) / f"export_{decision}.txt"
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((f"{path_prefix.rstrip('/')}/{r['relpath']}" if path_prefix
                      else r["relpath"]) + "\n")
    print(f"[export {year}] {len(rows)} '{decision}' files -> {out}")
    return 0
