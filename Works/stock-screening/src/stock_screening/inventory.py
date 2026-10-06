"""List the files of the archive and group copies/derivatives of the same frame.

The folder layout is free-form: years are taken from capture dates (see scan.py), not paths.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
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
    return {e.lower().lstrip(".") for e in cfg.section("inventory")[key]}


def is_excluded(relpath: str, globs: list[str]) -> bool:
    """True if `relpath` or any folder above it is hidden or matches an exclude glob.

    Globs are fnmatch patterns (case-sensitive) on the POSIX path relative to photos_root;
    "*" also matches "/", so "Exports" or "*.lrdata" exclude a whole folder at any depth.
    """
    p = PurePosixPath(relpath)
    return any(q.name.startswith(".") or any(fnmatchcase(str(q), g) for g in globs)
               for q in (p, *p.parents[:-1]))


def list_all(cfg: Config) -> list[Item]:
    """Return every supported file under photos_root (any folder layout), sorted by path."""
    root = cfg.photos_root
    globs = list(cfg.section("inventory")["exclude_globs"])
    raw, image, video = (_exts(cfg, k) for k in
                         ("raw_extensions", "image_extensions", "video_extensions"))
    items: list[Item] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if rel_dir == "." else rel_dir + "/"
        # Prune hidden/excluded folders so we never walk e.g. Lightroom preview caches.
        dirnames[:] = [d for d in dirnames if not is_excluded(prefix + d, globs)]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower().lstrip(".")
            kind = "raw" if ext in raw else "image" if ext in image else "video" if ext in video else None
            if kind is None or is_excluded(prefix + name, globs):
                continue  # sidecars (.xmp), info.lua, hidden or excluded files
            path = Path(dirpath, name)
            st = path.stat()
            items.append(Item(prefix + name, path, kind, st.st_size, st.st_mtime))
    items.sort(key=lambda it: it.relpath)
    return items


class StemNormalizer:
    """Map a file to the frame it belongs to: (group key, is_copy, is_derivative)."""

    def __init__(self, cfg: Config):
        inv = cfg.section("inventory")
        self.prefixes: list[str] = list(inv["copy_prefixes"])
        self.suffixes = [re.compile(rx) for rx in inv["derivative_suffixes"]]

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
