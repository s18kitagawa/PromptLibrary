"""Checks for the pure-logic helpers. Run: uv run python tests/test_logic.py (or pytest)."""

import os
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

from stock_screening import config, inventory, metrics, review


def test_ids_roundtrip():
    assert review.parse_ids("1-4, 9,12") == [1, 2, 3, 4, 9, 12]
    assert review.compress_ids([12, 1, 2, 3, 4, 9, 3]) == "1-4,9,12"
    for bad in ("abc", "1-x", "5-3"):
        try:
            review.parse_ids(bad)
        except ValueError:
            continue
        raise AssertionError(f"parse_ids accepted {bad!r}")


def test_stem_grouping():
    data = config._read_toml(config.DEFAULT_CONFIG)
    norm = inventory.StemNormalizer(config.Config(Path("."), Path("."), data))
    d = "2020/2020-01-01"
    assert norm.split(f"{d}/DSC0001.ARW") == (f"{d}/dsc0001", False, False)
    assert norm.split(f"{d}/LRG_DSC0001.JPG") == (f"{d}/dsc0001", True, False)
    assert norm.split(f"{d}/DSC0001-Enhanced-NR-Edit.dng") == (f"{d}/dsc0001", False, True)
    assert norm.split(f"{d}/DSC0001-強化-NR.dng") == (f"{d}/dsc0001", False, True)


def test_capture_date():
    mtime = datetime(2021, 6, 1, 12, 0).timestamp()
    with tempfile.TemporaryDirectory() as tmp:
        with_exif, without_exif = Path(tmp, "a.jpg"), Path(tmp, "b.jpg")
        exif = Image.Exif()
        exif.get_ifd(0x8769)[0x9003] = "2019:05:01 10:00:00"  # DateTimeOriginal
        Image.new("RGB", (8, 8)).save(with_exif, exif=exif)
        Image.new("RGB", (8, 8)).save(without_exif)
        for p in (with_exif, without_exif):
            os.utime(p, (mtime, mtime))
        rec = metrics.capture_date(str(with_exif), mtime)
        assert (rec["captured_at"], rec["date_source"]) == ("2019-05-01T10:00:00", "exif")
        rec = metrics.capture_date(str(without_exif), mtime)
        assert (rec["captured_at"], rec["date_source"]) == ("2021-06-01T12:00:00", "mtime")


def test_exclude_globs():
    globs = ["*.lrdata", "Exports", "*/Edited/*"]
    assert inventory.is_excluded("Lightroom/Previews.lrdata/a/b.jpg", globs)
    assert inventory.is_excluded("Exports/x.jpg", globs)
    assert inventory.is_excluded("Trip/Edited/x.jpg", globs)
    assert inventory.is_excluded("Trip/.thumbs/x.jpg", [])       # hidden folder
    assert inventory.is_excluded(".DS_Store", [])                 # hidden file
    assert not inventory.is_excluded("Trip/Exports2/x.jpg", globs)
    assert not inventory.is_excluded("Camera/IMG_0001.jpg", globs)


if __name__ == "__main__":
    test_ids_roundtrip()
    test_stem_grouping()
    test_capture_date()
    test_exclude_globs()
    print("ok")
