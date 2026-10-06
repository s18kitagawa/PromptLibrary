"""Per-file analysis: capture date (EXIF or mtime), resolution, sharpness, exposure, pHash.

Metrics are computed on the JPEG preview embedded in RAW files (fast, no demosaicing).
When a RAW has no usable preview, a half-size LibRaw render is used instead.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import exifread
import imagehash
import numpy as np
import rawpy
from PIL import Image, ImageOps

# Bump when the metric definitions change so cached results are recomputed.
METRICS_VERSION = 2  # 2: archive-wide cache, date_source, two-step scan

PREVIEW_MIN_SIDE = 800   # embedded previews smaller than this trigger a LibRaw render
ANALYSIS_SIDE = 1024     # metrics are computed at this long-side size for comparability
GRID = 4                 # sharpness is measured per tile on a GRID x GRID layout

Image.MAX_IMAGE_PIXELS = 300_000_000  # allow large panoramas / 100MP files
logging.getLogger("exifread").setLevel(logging.ERROR)

# LibRaw "flip" values -> PIL transpose
_FLIP = {
    3: Image.Transpose.ROTATE_180,
    5: Image.Transpose.ROTATE_90,   # 90° counter-clockwise
    6: Image.Transpose.ROTATE_270,  # 90° clockwise
}


def read_exif(path: Path) -> dict[str, Any]:
    try:
        with open(path, "rb") as fh:
            tags = exifread.process_file(fh, details=False)
    except Exception:
        return {}

    def get(*keys: str) -> str | None:
        for key in keys:
            if key in tags:
                value = str(tags[key]).strip().strip("\x00")
                if value:
                    return value
        return None

    captured = None
    for key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
        raw_dt = get(key)
        if raw_dt:
            try:  # placeholders like "0000:00:00 00:00:00" fall through to the next tag
                captured = datetime.strptime(raw_dt[:19], "%Y:%m:%d %H:%M:%S").isoformat()
                break
            except ValueError:
                pass
    make, model = get("Image Make"), get("Image Model")
    camera = " ".join(x for x in (make, model) if x) or None
    return {"captured_at": captured, "camera": camera}


def capture_date(path_str: str, mtime: float) -> dict[str, Any]:
    """EXIF capture time, or the file mtime when there is none. Runs in a worker process.

    Returns {"captured_at", "date_source" ("exif" | "mtime"), "camera"}.
    """
    rec = read_exif(Path(path_str))
    if rec["captured_at"]:
        rec["date_source"] = "exif"
    else:
        rec["captured_at"] = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
        rec["date_source"] = "mtime"
    return rec


def load_preview(path: Path, kind: str) -> tuple[Image.Image, int, int]:
    """Return (upright RGB preview, full-resolution width, full-resolution height)."""
    if kind == "raw":
        with rawpy.imread(str(path)) as raw:
            width, height, flip = raw.sizes.width, raw.sizes.height, raw.sizes.flip
            img = None
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    img = Image.open(io.BytesIO(thumb.data))
                    img.load()
                    if img.getexif().get(274, 1) != 1:
                        img = ImageOps.exif_transpose(img)
                    elif flip in _FLIP:
                        img = img.transpose(_FLIP[flip])
                elif thumb.format == rawpy.ThumbFormat.BITMAP:
                    img = Image.fromarray(thumb.data)
                    if flip in _FLIP:
                        img = img.transpose(_FLIP[flip])
            except rawpy.LibRawError:
                img = None
            if img is None or max(img.size) < PREVIEW_MIN_SIDE:
                rgb = raw.postprocess(half_size=True, use_camera_wb=True, output_bps=8)
                img = Image.fromarray(rgb)  # LibRaw already applies the flip
        if flip in (5, 6):
            width, height = height, width
        return img.convert("RGB"), width, height

    img = Image.open(path)
    img.load()
    img = ImageOps.exif_transpose(img)
    width, height = img.size
    return img.convert("RGB"), width, height


def analyze(path_str: str, kind: str) -> dict[str, Any]:
    """Compute the preview metrics for one file. Runs in a worker process."""
    rec: dict[str, Any] = {}
    if kind == "video":
        return rec
    try:
        img, width, height = load_preview(Path(path_str), kind)
    except Exception as exc:  # unreadable / unsupported file
        rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return rec

    rec.update(width=width, height=height, megapixels=round(width * height / 1e6, 2))
    img.thumbnail((ANALYSIS_SIDE, ANALYSIS_SIDE))
    gray = np.asarray(img.convert("L"), dtype=np.uint8)

    lap = cv2.Laplacian(gray, cv2.CV_64F)
    h, w = lap.shape
    tiles = [lap[i * h // GRID:(i + 1) * h // GRID, j * w // GRID:(j + 1) * w // GRID].var()
             for i in range(GRID) for j in range(GRID)]
    rec["sharp_max"] = round(float(max(tiles)), 1)
    rec["sharp_center"] = round(float(lap[h // 4:3 * h // 4, w // 4:3 * w // 4].var()), 1)
    rec["sharp_global"] = round(float(lap.var()), 1)

    rec["mean_luma"] = round(float(gray.mean()), 1)
    rec["clip_high"] = round(float((gray >= 250).mean()), 4)
    rec["clip_low"] = round(float((gray <= 5).mean()), 4)
    rec["phash"] = str(imagehash.phash(img))
    return rec
