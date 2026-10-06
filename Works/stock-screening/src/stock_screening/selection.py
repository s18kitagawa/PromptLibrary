"""Step 1b: apply duplicate, technical, quality and burst rules to the cached metrics.

Cheap to re-run: tweak thresholds in config and run `select` again without rescanning.
Writes <out>/<year>/screen.csv with one row per file and a pass/reject status.
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from typing import Any

from . import inventory, scan
from .config import Config

SCREEN_NAME = "screen.csv"
SCREEN_FIELDS = ["relpath", "status", "reasons", "kind", "megapixels", "captured_at", "camera",
                 "sharp_max", "sharp_center", "mean_luma", "clip_high", "clip_low",
                 "group", "burst"]


def _hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _gap_seconds(a: dict[str, Any], b: dict[str, Any]) -> float:
    return abs((datetime.fromisoformat(b["captured_at"])
                - datetime.fromisoformat(a["captured_at"])).total_seconds())


def read_screen(cfg: Config, year: str) -> list[dict[str, str]]:
    path = cfg.year_dir(year) / SCREEN_NAME
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `select --year {year}` first")
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def run(cfg: Config, year: str) -> int:
    items = inventory.list_year(cfg, year)
    cache = scan.load_cache(cfg, year)
    missing = [it for it in items if not scan.is_fresh(cache.get(it.relpath), it)]
    if missing:
        print(f"error: {len(missing)} files are not scanned yet - run `scan --year {year}` first")
        return 2

    inv, tech = cfg.section("inventory"), cfg.section("technical")
    qual, bursts_cfg = cfg.section("quality"), cfg.section("bursts")
    norm = inventory.StemNormalizer(cfg)

    rows: list[dict[str, Any]] = []
    for it in items:
        group, is_copy, is_derivative = norm.split(it.relpath)
        rows.append(dict(cache[it.relpath], group=group, burst="",
                         _copy=is_copy, _deriv=is_derivative, _reasons=[]))

    # 1. Files that can never be submitted as photos.
    for r in rows:
        if r["kind"] == "video":
            r["_reasons"].append("video")
        elif r.get("error"):
            r["_reasons"].append("read_error")

    # 2. Copies / derivatives of the same frame: keep one.
    prefer_derivative = bool(inv.get("prefer_derivative", True))
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if not r["_reasons"]:
            groups.setdefault(r["group"], []).append(r)

    def rank(r: dict[str, Any]) -> tuple:
        return (r["_deriv"] if prefer_derivative else not r["_deriv"],
                not r["_copy"], r["kind"] == "raw", r.get("megapixels") or 0, r["relpath"])

    for members in groups.values():
        if len(members) > 1:
            best = max(members, key=rank)
            for r in members:
                if r is not best:
                    r["_reasons"].append(f"duplicate_of:{best['relpath']}")

    # 3. Adobe Stock technical limits and coarse quality checks.
    for r in rows:
        if r["_reasons"]:
            continue
        mp = r.get("megapixels") or 0
        if mp < float(tech.get("min_megapixels", 4.0)):
            r["_reasons"].append("low_resolution")
        if mp > float(tech.get("max_megapixels", 100.0)):
            r["_reasons"].append("too_high_resolution")
        if (r.get("sharp_max") or 0) < float(qual.get("min_sharpness", 100.0)):
            r["_reasons"].append("soft_focus")
        if r.get("clip_high", 0) > float(qual.get("max_clip_high", 0.25)) \
                or r.get("mean_luma", 0) > float(qual.get("max_mean_luma", 235)):
            r["_reasons"].append("overexposed")
        if r.get("clip_low", 0) > float(qual.get("max_clip_low", 0.98)) \
                or r.get("mean_luma", 255) < float(qual.get("min_mean_luma", 12)):
            r["_reasons"].append("underexposed")

    # 4. Bursts: near-identical frames shot seconds apart -> keep the sharpest.
    if bursts_cfg.get("enabled", True):
        max_gap = float(bursts_cfg.get("max_gap_seconds", 30.0))
        max_dist = int(bursts_cfg.get("max_hash_distance", 12))
        cands = sorted((r for r in rows
                        if not r["_reasons"] and r.get("captured_at") and r.get("phash")),
                       key=lambda r: (r["captured_at"], r["relpath"]))
        bursts: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for r in cands:
            if current and _gap_seconds(current[-1], r) <= max_gap \
                    and _hamming(current[-1]["phash"], r["phash"]) <= max_dist:
                current.append(r)
            else:
                if len(current) > 1:
                    bursts.append(current)
                current = [r]
        if len(current) > 1:
            bursts.append(current)
        for n, members in enumerate(bursts, 1):
            best = max(members, key=lambda r: r.get("sharp_max") or 0)
            for r in members:
                r["burst"] = f"B{n:04d}"
                if r is not best:
                    r["_reasons"].append(f"similar_to:{best['relpath']}")

    out_path = cfg.year_dir(year) / SCREEN_NAME
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SCREEN_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            r["status"] = "reject" if r["_reasons"] else "pass"
            r["reasons"] = ";".join(r["_reasons"])
            writer.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in SCREEN_FIELDS})

    passed = sum(1 for r in rows if not r["_reasons"])
    reasons = Counter(r["_reasons"][0].split(":")[0] for r in rows if r["_reasons"])
    print(f"[select {year}] {len(rows)} files -> {passed} pass, {len(rows) - passed} reject")
    for reason, count in reasons.most_common():
        print(f"  {reason:<20} {count}")
    print(f"wrote {out_path}")
    return 0
