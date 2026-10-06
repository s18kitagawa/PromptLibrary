"""Configuration loading and path safety checks."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config.toml"
LOCAL_CONFIG = REPO_ROOT / "config.local.toml"
ENV_PHOTOS_ROOT = "STOCK_SCREENING_PHOTOS_ROOT"
ENV_OUT_DIR = "STOCK_SCREENING_OUT_DIR"


class ConfigError(Exception):
    """Raised when configuration is missing or unsafe."""


def _read_toml(path: Path) -> dict[str, Any]:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Config:
    photos_root: Path
    out_dir: Path
    data: dict[str, Any]

    def section(self, name: str) -> dict[str, Any]:
        return self.data.get(name, {})

    def year_dir(self, year: str) -> Path:
        path = self.out_dir / year
        path.mkdir(parents=True, exist_ok=True)
        return path


def load(photos_root: Path | None = None, out_dir: Path | None = None,
         extra_config: Path | None = None) -> Config:
    data: dict[str, Any] = _read_toml(DEFAULT_CONFIG) if DEFAULT_CONFIG.exists() else {}
    if LOCAL_CONFIG.exists():
        data = _merge(data, _read_toml(LOCAL_CONFIG))
    if extra_config is not None:
        if not extra_config.exists():
            raise ConfigError(f"config file not found: {extra_config}")
        data = _merge(data, _read_toml(extra_config))

    paths = data.get("paths", {})
    photos = photos_root or os.environ.get(ENV_PHOTOS_ROOT) or paths.get("photos_root")
    out = out_dir or os.environ.get(ENV_OUT_DIR) or paths.get("out_dir")
    if not photos:
        raise ConfigError(
            f"photo archive not set: use --photos-root, ${ENV_PHOTOS_ROOT}, "
            "or [paths].photos_root in config.local.toml")
    if not out:
        raise ConfigError(
            f"output folder not set: use --out-dir, ${ENV_OUT_DIR}, "
            "or [paths].out_dir in config.local.toml")

    photos_path = Path(photos).expanduser().resolve()
    out_path = Path(out).expanduser().resolve()
    if not photos_path.is_dir():
        raise ConfigError(f"photo archive not found: {photos_path}")
    # Privacy guard: results (paths, thumbnails, review notes) must never land in the repo.
    if out_path.is_relative_to(REPO_ROOT):
        raise ConfigError("output folder must be outside the code repository "
                          f"({REPO_ROOT}) so results can never be committed")
    # Keep contact sheets out of the archive so Lightroom never imports them.
    if out_path.is_relative_to(photos_path):
        raise ConfigError("output folder must be outside the photo archive")
    out_path.mkdir(parents=True, exist_ok=True)
    return Config(photos_path, out_path, data)
