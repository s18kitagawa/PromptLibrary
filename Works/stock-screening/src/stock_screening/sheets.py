"""Step 2a: render numbered contact sheets of the files that passed `select`.

Each tile shows a 4-digit ID and the capture time. <out>/<year>/sheets/index.csv maps
IDs to files; `mark` uses it to record review decisions.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import metrics, review, selection
from .config import Config

INDEX_NAME = "index.csv"
INDEX_FIELDS = ["id", "sheet", "relpath", "captured_at"]


def sheets_dir(cfg: Config, year: str) -> Path:
    path = cfg.year_dir(year) / "sheets"
    path.mkdir(exist_ok=True)
    return path


def read_index(cfg: Config, year: str) -> dict[str, dict[str, str]]:
    path = sheets_dir(cfg, year) / INDEX_NAME
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `sheets --year {year}` first")
    with open(path, newline="", encoding="utf-8") as fh:
        return {row["id"]: row for row in csv.DictReader(fh)}


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def run(cfg: Config, year: str, include_reviewed: bool = False) -> int:
    opts = cfg.section("sheets")
    cols, rows_n = int(opts.get("columns", 5)), int(opts.get("rows", 4))
    tile = int(opts.get("tile_px", 440))
    quality = int(opts.get("jpeg_quality", 82))

    reviewed = set() if include_reviewed else set(review.load(cfg, year))
    passed = [r for r in selection.read_screen(cfg, year)
              if r["status"] == "pass" and r["relpath"] not in reviewed]
    passed.sort(key=lambda r: (r.get("captured_at") or "", r["relpath"]))
    out = sheets_dir(cfg, year)
    if not passed:
        print(f"[sheets {year}] nothing to review"
              + ("" if include_reviewed else " (already-reviewed files are skipped)"))
        return 0

    label_h = max(28, tile // 16)
    box_h = int(tile * 0.8)
    cell_w, cell_h, pad = tile, box_h + label_h, 8
    per_sheet = cols * rows_n
    n_sheets = math.ceil(len(passed) / per_sheet)
    font_id, font_small = _font(label_h - 6), _font(max(12, label_h // 2))
    index_rows: list[dict[str, str]] = []

    for s in range(n_sheets):
        chunk = passed[s * per_sheet:(s + 1) * per_sheet]
        sheet = Image.new("RGB", (pad + cols * (cell_w + pad), pad + rows_n * (cell_h + pad)),
                          (40, 40, 40))
        draw = ImageDraw.Draw(sheet)
        name = f"sheet_{s + 1:03d}.jpg"
        for k, row in enumerate(chunk):
            tile_id = f"{s * per_sheet + k + 1:04d}"
            x = pad + (k % cols) * (cell_w + pad)
            y = pad + (k // cols) * (cell_h + pad)
            try:
                img, _, _ = metrics.load_preview(cfg.photos_root / row["relpath"], row["kind"])
                img.thumbnail((cell_w, box_h))
                sheet.paste(img, (x + (cell_w - img.width) // 2, y + (box_h - img.height) // 2))
            except Exception:
                draw.text((x + 10, y + 10), "preview error", fill=(255, 90, 90), font=font_small)
            draw.rectangle([x, y + box_h, x + cell_w - 1, y + cell_h - 1], fill=(0, 0, 0))
            draw.text((x + 8, y + box_h + 2), tile_id, fill=(255, 220, 0), font=font_id)
            when = (row.get("captured_at") or "")[:16].replace("T", " ")
            draw.text((x + cell_w - 8, y + box_h + label_h // 2), when, fill=(200, 200, 200),
                      font=font_small, anchor="rm")
            index_rows.append({"id": tile_id, "sheet": name, "relpath": row["relpath"],
                               "captured_at": row.get("captured_at", "")})
        sheet.save(out / name, quality=quality, optimize=True)

    with open(out / INDEX_NAME, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(index_rows)

    # Remove sheets left over from a previous, larger run (best effort: some sandboxes
    # forbid deletion; index.csv is authoritative either way).
    stale = []
    for old in sorted(out.glob("sheet_*.jpg")):
        try:
            if int(old.stem.split("_")[1]) > n_sheets:
                old.unlink()
        except (ValueError, IndexError):
            continue
        except OSError:
            stale.append(old.name)

    print(f"[sheets {year}] {len(passed)} images on {n_sheets} sheets "
          f"(sheet_001.jpg - sheet_{n_sheets:03d}.jpg) in {out}")
    if stale:
        print(f"note: could not delete {len(stale)} stale sheets from an earlier run "
              f"({stale[0]} ...); ignore them - index.csv lists the current set")
    return 0
