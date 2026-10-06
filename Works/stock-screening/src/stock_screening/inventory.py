"""List the files of one year and group copies/derivatives of the same frame."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import Config


@dataclass(frozen=True)
class Item:
    relpath: str  # POSIX path relative to the photo archive root
    path: Path
    kind: str     # "raw" | "image" | "video"
    size: int
    mtime: float


def _exts(cfg: Config, key: str) -> set[str]:
    return {e.lower().lstrip(".") for e in cfg.section("inventory").get(key, [])}


def list_year(cfg: Config, year: str) -> list[Item]:
    """Return every supported file under <photos_root>/<year>, sorted by path."""
    root = cfg.photos_root / year
    if not root.is_dir():
        raise FileNotFoundError(f"year folder not found: {root}")
    raw, image, video = (_exts(cfg, k) for k in
                         ("raw_extensions", "image_extensions", "video_extensions"))
    items: list[Item] = []
    for path in sorted(root.rglob("*")):
        if path.name.startswith(".") or not path.is_file():
            continue
        ext = path.suffix.lower().lstrip(".")
        kind = "raw" if ext in raw else "image" if ext in image else "video" if ext in video else None
        if kind is None:
            continue  # sidecars (.xmp), info.lua, etc.
        st = path.stat()
        items.append(Item(path.relative_to(cfg.photos_root).as_posix(), path, kind,
                          st.st_size, st.st_mtime))
    return items


class StemNormalizer:
    """Map a file to the frame it belongs to: (group key, is_copy, is_derivative)."""

    def __init__(self, cfg: Config):
        inv = cfg.section("inventory")
        self.prefixes: list[str] = list(inv.get("copy_prefixes", []))
        self.suffixes = [re.compile(rx) for rx in inv.get("derivative_suffixes", [])]

    def split(self, relpath: str) -> tuple[str, bool, bool]:
        p = PurePosixPath(relpath)
        stem, is_copy, is_derivative = p.stem, False, False
        for prefix in self.prefixes:
            if stem.startswith(prefix):
                stem, is_copy = stem[len(prefix):], True
                break
        changed = True
        while changed:
            changed = False
            for rx in self.suffixes:
                new = rx.sub("", stem)
                if new != stem:
                    stem, is_derivative, changed = new, True, True
        return f"{p.parent.as_posix()}/{stem.lower()}", is_copy, is_derivative
