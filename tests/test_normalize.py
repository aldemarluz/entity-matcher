import pytest

from entity_matcher import extract_numbers, normalize


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Laptop Charger 65W", "LAPTOP CHARGER 65W"),
        ("laptop charger 65w", "LAPTOP CHARGER 65W"),
        ("  Laptop   Charger  65W ", "LAPTOP CHARGER 65W"),
        ("Laptop Charger 65W - box of 10", "LAPTOP CHARGER 65W"),
        ("Laptop Charger 65W (pack 20)", "LAPTOP CHARGER 65W"),
        ("Laptop Charger 65W bulk", "LAPTOP CHARGER 65W"),
        ("Memória DDR4 16GB - Caixa 10 un", "MEMORIA DDR4 16GB"),
        ("Monitor 23.8in / CARTON", "MONITOR 23.8IN"),
        ("Monitor 23,8in Full HD", "MONITOR 23.8IN FULL HD"),
        ("Memory DDR4 16 GB", "MEMORY DDR4 16GB"),
        ("Net. Cbl. Cat6 3m", "NETWORK CABLE CAT6 3M"),
        ("Wrls. Mouse - pack 12", "WIRELESS MOUSE"),
        ("Wireless Mouse - pallet", "WIRELESS MOUSE"),
        ("Wireless Mouse 50 pcs", "WIRELESS MOUSE"),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Laptop Charger 65W - box of 10", ("65",)),
        ("Laptop Charger 65 W", ("65",)),
        ("Monitor 23.8in pack 2", ("23.8",)),
        ("Monitor 23,8in", ("23.8",)),
        ("Monitor 23.80in", ("23.8",)),
        ("Charger 065W", ("65",)),
        ("Wireless Mouse", ()),
        ("Splitter 10/90", ("10", "90")),
        ("Splitter 90/10", ("10", "90")),
        ("Product 10.0", ("10",)),
    ],
)
def test_extract_numbers(raw, expected):
    assert extract_numbers(raw) == expected


def test_packaging_never_changes_the_numbers():
    base = extract_numbers("Laptop Charger 65W")
    for pkg in ["box of 10", "pack 20", "bulk", "50 pcs", "carton 24"]:
        assert extract_numbers(f"Laptop Charger 65W {pkg}") == base


def test_normalize_is_idempotent():
    once = normalize("Memória DDR4 16GB - Caixa 10 un")
    assert normalize(once) == once
