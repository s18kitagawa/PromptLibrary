"""Step 1a: analyze every file of a year and append results to a JSONL cache.

The cache is append-only (no file deletion or renaming is ever needed), so a run can be
interrupted at any time - e.g. by --time-budget or a shell timeout - and resumed later.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path
from typing import Any

from . import inventory, metrics
from .config import Config

CACHE_NAME = "cache.jsonl"


def cache_path(cfg: Config, year: str) -> Path:
    return cfg.year_dir(year) / CACHE_NAME


def load_cache(cfg: Config, year: str) -> dict[str, dict[str, Any]]:
    """Latest record per relpath (later lines win)."""
    path = cache_path(cfg, year)
    records: dict[str, dict[str, Any]] = {}
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # partial line from an interrupted write
                records[rec["relpath"]] = rec
    return records


def is_fresh(rec: dict[str, Any] | None, item: inventory.Item) -> bool:
    return bool(rec) and rec.get("size") == item.size \
        and abs(rec.get("mtime", 0) - item.mtime) < 1 \
        and rec.get("v") == metrics.METRICS_VERSION


def run(cfg: Config, year: str, time_budget: float = 0, workers: int = 0) -> int:
    start = time.monotonic()
    items = inventory.list_year(cfg, year)
    cache = load_cache(cfg, year)
    # Error records are retried on every scan: the failure may have been transient
    # (e.g. a dropped mount). `select` still accepts them as scanned.
    todo = [it for it in items if not is_fresh(rec := cache.get(it.relpath), it)
            or rec.get("error")]
    print(f"[scan {year}] {len(items)} files: {len(items) - len(todo)} cached, "
          f"{len(todo)} to analyze", flush=True)
    if not todo:
        print("SCAN COMPLETE")
        return 0

    workers = workers or os.cpu_count() or 1
    done = 0
    stopped = False
    queue = iter(todo)
    with open(cache_path(cfg, year), "a", encoding="utf-8") as out, \
            ProcessPoolExecutor(
                max_workers=workers,
                # rawpy/LibRaw uses OpenMP, which can deadlock in forked workers.
                mp_context=multiprocessing.get_context("spawn")) as pool:
        pending: dict[Any, inventory.Item] = {}

        def submit_next() -> None:
            item = next(queue, None)
            if item is not None:
                fut = pool.submit(metrics.analyze, item.relpath, str(item.path), item.kind)
                pending[fut] = item

        for _ in range(workers * 2):
            submit_next()
        while pending:
            finished, _ = wait(list(pending), return_when=FIRST_COMPLETED)
            for fut in finished:
                item = pending.pop(fut)
                try:
                    rec = fut.result()
                except Exception as exc:
                    rec = {"relpath": item.relpath, "kind": item.kind,
                           "error": f"{type(exc).__name__}: {exc}"[:200]}
                rec.update(size=item.size, mtime=item.mtime, v=metrics.METRICS_VERSION)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                done += 1
                if done % 200 == 0:
                    print(f"  ... {done}/{len(todo)}", flush=True)
                if time_budget and time.monotonic() - start > time_budget:
                    stopped = True
                if not stopped:
                    submit_next()

    remaining = len(todo) - done
    if remaining:
        print(f"SCAN INCOMPLETE: {remaining} files left - run the same command again to continue.")
        return 3
    print(f"SCAN COMPLETE ({done} analyzed in {time.monotonic() - start:.0f}s)")
    return 0
