"""Step 1a: date every file of the archive, then analyze the files of one capture year.

Two steps, both recorded in one archive-wide JSONL cache (<out>/cache.jsonl):
  1. capture date - EXIF date (or file mtime as a fallback) for every new or changed file;
     cheap, but the first run has to touch the whole archive.
  2. analysis - preview metrics, only for the files whose capture year is --year.

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
from typing import Any, Callable

from . import inventory, metrics
from .config import Config

CACHE_NAME = "cache.jsonl"


def cache_path(cfg: Config) -> Path:
    return cfg.out_dir / CACHE_NAME


def load_cache(cfg: Config) -> dict[str, dict[str, Any]]:
    """Latest record per relpath (later lines win)."""
    path = cache_path(cfg)
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
    """The record matches the file on disk, so at least its capture date is known."""
    return bool(rec) and rec.get("size") == item.size \
        and abs(rec.get("mtime", 0) - item.mtime) < 1 \
        and rec.get("v") == metrics.METRICS_VERSION


def is_analyzed(rec: dict[str, Any] | None, item: inventory.Item) -> bool:
    return is_fresh(rec, item) and bool(rec.get("analyzed"))


def year_files(cfg: Config, year: str) -> tuple[list[inventory.Item], dict[str, dict[str, Any]],
                                                 list[inventory.Item]]:
    """(all archive files, cache, files captured in `year`).

    Files whose capture date is not cached yet are in no year; `undated()` counts them.
    """
    items = inventory.list_all(cfg)
    cache = load_cache(cfg)
    targets = [it for it in items if is_fresh(rec := cache.get(it.relpath), it)
               and year_of(rec) == year]
    return items, cache, targets


def year_of(rec: dict[str, Any]) -> str:
    return (rec.get("captured_at") or "")[:4]


def undated(items: list[inventory.Item], cache: dict[str, dict[str, Any]]) -> int:
    return sum(1 for it in items if not is_fresh(cache.get(it.relpath), it))


def _drain(pool: ProcessPoolExecutor, todo: list[inventory.Item], workers: int,
           deadline: float | None, task: Callable[[inventory.Item], tuple],
           record: Callable[[inventory.Item, dict[str, Any]], None]) -> int:
    """Run pool.submit(*task(item)) for each item, keeping `workers * 2` in flight, and pass
    each result to record(). Stops submitting at the deadline; returns the number left."""
    queue = iter(todo)
    pending: dict[Any, inventory.Item] = {}

    def submit_next() -> None:
        item = next(queue, None)
        if item is not None:
            pending[pool.submit(*task(item))] = item

    for _ in range(workers * 2):
        submit_next()
    done = 0
    while pending:
        finished, _ = wait(list(pending), return_when=FIRST_COMPLETED)
        for fut in finished:
            item = pending.pop(fut)
            try:
                res = fut.result()
            except Exception as exc:
                res = {"error": f"{type(exc).__name__}: {exc}"[:200]}
            record(item, res)
            done += 1
            if done % 500 == 0:
                print(f"  ... {done}/{len(todo)}", flush=True)
            if deadline is None or time.monotonic() < deadline:
                submit_next()
    return len(todo) - done


def _incomplete(step: int, left: int) -> int:
    print(f"SCAN INCOMPLETE (step {step}/2): {left} files left - "
          "run the same command again to continue.")
    return 3


def run(cfg: Config, year: str, time_budget: float = 0, workers: int = 0) -> int:
    start = time.monotonic()
    deadline = start + time_budget if time_budget else None
    workers = workers or os.cpu_count() or 1
    items = inventory.list_all(cfg)
    cache = load_cache(cfg)

    with open(cache_path(cfg), "a", encoding="utf-8") as out, \
            ProcessPoolExecutor(
                max_workers=workers,
                # rawpy/LibRaw uses OpenMP, which can deadlock in forked workers.
                mp_context=multiprocessing.get_context("spawn")) as pool:

        def write(rec: dict[str, Any]) -> None:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            cache[rec["relpath"]] = rec

        # Step 1: capture dates for the whole archive. A worker crash leaves no
        # captured_at, so such files are simply retried on the next run.
        todo = [it for it in items if not is_fresh(rec := cache.get(it.relpath), it)
                or not rec.get("captured_at")]
        print(f"[scan {year}] step 1/2 capture dates: {len(items)} files in the archive, "
              f"{len(todo)} to read", flush=True)

        def record_date(item: inventory.Item, res: dict[str, Any]) -> None:
            write({"relpath": item.relpath, "kind": item.kind, **res,
                   "size": item.size, "mtime": item.mtime, "v": metrics.METRICS_VERSION})

        left = _drain(pool, todo, workers, deadline,
                      lambda it: (metrics.capture_date, str(it.path), it.mtime), record_date)
        if left:
            return _incomplete(1, left)

        # Step 2: preview metrics for the files of `year`. Error records are retried on
        # every scan: the failure may have been transient (e.g. a dropped mount).
        targets = [it for it in items if year_of(cache[it.relpath]) == year]
        todo = [it for it in targets if not is_analyzed(rec := cache[it.relpath], it)
                or rec.get("error")]
        print(f"[scan {year}] step 2/2 analysis: {len(targets)} files captured in {year}, "
              f"{len(todo)} to analyze", flush=True)
        if todo and deadline is not None and time.monotonic() >= deadline:
            return _incomplete(2, len(todo))  # step 1 used up the budget

        def record_metrics(item: inventory.Item, res: dict[str, Any]) -> None:
            base = {k: v for k, v in cache[item.relpath].items() if k != "error"}
            write({**base, **res, "analyzed": True})

        left = _drain(pool, todo, workers, deadline,
                      lambda it: (metrics.analyze, str(it.path), it.kind), record_metrics)
        if left:
            return _incomplete(2, left)

    print(f"SCAN COMPLETE ({time.monotonic() - start:.0f}s)")
    return 0
