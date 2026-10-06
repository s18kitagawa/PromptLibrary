"""Checks for the pure-logic helpers. Run: uv run python tests/test_logic.py (or pytest)."""

from pathlib import Path

from stock_screening import config, inventory, review


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


if __name__ == "__main__":
    test_ids_roundtrip()
    test_stem_grouping()
    print("ok")
