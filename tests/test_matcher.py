import pytest

from entity_matcher import Canonical, Matcher, MatchState, Record, summarize

CATALOGUE = [
    Canonical("P-001", "Laptop Charger 65W USB-C", "MC-1001", "LAPTOP CHARGER"),
    Canonical("P-002", "Laptop Charger 90W USB-C", "MC-1002", "LAPTOP CHARGER"),
    Canonical("P-003", "SSD NVMe 1TB", "MC-1003", "SSD"),
    Canonical("P-004", "Memory DDR4 16GB 3200MHz", "MC-1004", "MEMORY DDR4"),
    Canonical("P-005", "Memory DDR4 32GB 3200MHz", "MC-1005", "MEMORY DDR4"),
    Canonical("P-008", "Monitor 23.8in Full HD", "MC-1008", "MONITOR"),
    Canonical("P-010", "Thermal Paper Roll 80mm", "MC-1010", "THERMAL PAPER"),
]


@pytest.fixture
def matcher():
    return Matcher(CATALOGUE)


def rec(name, code=None, parent=None, ref="X-1", source="test"):
    return Record(source, ref, name, code, parent)


# ---------------------------------------------------------------- stage 1
def test_stage1_master_code_confirms_even_with_a_different_name(matcher):
    m = matcher.match(rec("totally different label", code="MC-1003"))
    assert (m.state, m.canonical_id, m.stage) == (MatchState.CONFIRMED, "P-003", 1)


def test_unknown_master_code_falls_through_to_name_stages(matcher):
    m = matcher.match(rec("SSD NVMe 1TB", code="MC-9999"))
    assert m.stage == 3 and m.canonical_id == "P-003"


# ---------------------------------------------------------------- stage 2
def test_stage2_parent_plus_name_confirms(matcher):
    m = matcher.match(rec("laptop charger 65 W usb-c (pack 20)", parent="LAPTOP CHARGER"))
    assert (m.state, m.canonical_id, m.stage) == (MatchState.CONFIRMED, "P-001", 2)


def test_stage2_wrong_parent_does_not_confirm(matcher):
    m = matcher.match(rec("Laptop Charger 65W USB-C", parent="SOMETHING ELSE"))
    assert m.state is MatchState.PROBABLE and m.stage == 3


# ---------------------------------------------------------------- stage 3
@pytest.mark.parametrize(
    "name, expected",
    [
        ("SSD NVME 1TB - BULK", "P-003"),
        ("ssd nvme 1tb", "P-003"),
        ("Memory DDR4 32 GB 3200 MHz", "P-005"),
        ("Monitor 23,8in Full HD - carton 2", "P-008"),
    ],
)
def test_stage3_identical_normalised_name_is_only_probable(matcher, name, expected):
    m = matcher.match(rec(name))
    assert (m.state, m.canonical_id, m.stage) == (MatchState.PROBABLE, expected, 3)
    assert not m.writable


def test_stage3_duplicate_names_in_catalogue_are_a_conflict():
    dup = Matcher([Canonical("A", "Webcam"), Canonical("B", "Webcam")])
    m = dup.match(rec("webcam"))
    assert m.state is MatchState.CONFLICT and set(m.candidates) == {"A", "B"}


# ---------------------------------------------------------------- stage 4
@pytest.mark.parametrize(
    "name, expected",
    [
        ("Memmory DDR4 16GB 3200MHz", "P-004"),     # typo
        ("Memroy DDR4 32GB 3200MHz", "P-005"),      # typo
        ("Monitr 23,8in Full HD", "P-008"),         # typo + decimal comma
        ("Thermal Paper Rol 80mm", "P-010"),        # typo
    ],
)
def test_stage4_similar_names_with_matching_numbers(matcher, name, expected):
    m = matcher.match(rec(name))
    assert (m.state, m.canonical_id, m.stage) == (MatchState.PROBABLE, expected, 4)
    assert m.score >= matcher.threshold


# ---------------------------------------------------------------- numeric guard
@pytest.mark.parametrize(
    "name",
    [
        "Memory DDR4 8GB 3200MHz",  # capacity that does not exist
        "Laptop Charger 45W USB-C",  # other wattage
        "Monitor 21.5in Full HD",    # 21.5 vs 23.8
        "Thermal Paper Roll 57mm",
    ],
)
def test_numeric_guard_rejects_similar_names_with_other_numbers(matcher, name):
    m = matcher.match(rec(name))
    assert m.state is MatchState.CONFLICT
    assert m.canonical_id is None
    assert "numeric guard" in m.reason


def test_16gb_and_32gb_never_cross_match(matcher):
    small = matcher.match(rec("Memory DDR4 16GB 3200MHz - box of 10"))
    large = matcher.match(rec("Memory DDR4 32GB 3200MHz - box of 10"))
    assert small.canonical_id == "P-004"
    assert large.canonical_id == "P-005"


# ---------------------------------------------------------------- orphan
@pytest.mark.parametrize("name", ["Mechanical Keyboard", "Webcam", "xyz"])
def test_orphan_when_nothing_is_close(matcher, name):
    m = matcher.match(rec(name))
    assert m.state is MatchState.ORPHAN and m.canonical_id is None and m.stage is None


# ---------------------------------------------------------------- guards on config
def test_threshold_must_be_valid():
    with pytest.raises(ValueError):
        Matcher(CATALOGUE, threshold=0)
    with pytest.raises(ValueError):
        Matcher(CATALOGUE, threshold=1.5)


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        Matcher([Canonical("A", "x"), Canonical("A", "y")])


def test_duplicate_master_codes_rejected():
    with pytest.raises(ValueError):
        Matcher([Canonical("A", "x", "MC"), Canonical("B", "y", "MC")])


def test_ambiguous_fuzzy_match_is_a_conflict():
    m = Matcher([Canonical("A", "Router Alpha 10"), Canonical("B", "Router Alphb 10")])
    r = m.match(rec("Router Alphc 10"))
    assert r.state is MatchState.CONFLICT and set(r.candidates) == {"A", "B"}


# ---------------------------------------------------------------- determinism
def test_same_input_same_output_every_time(matcher):
    records = [rec(n, ref=str(i)) for i, n in enumerate(
        ["Memmory DDR4 16GB 3200MHz", "Laptop Charger 45W USB-C", "Webcam", "ssd nvme 1tb"])]
    first = matcher.match_all(records)
    for _ in range(20):
        assert matcher.match_all(records) == first


def test_order_of_catalogue_does_not_change_results():
    a = Matcher(CATALOGUE)
    b = Matcher(list(reversed(CATALOGUE)))
    for name in ["Memmory DDR4 16GB 3200MHz", "Monitr 23,8in Full HD", "Laptop Charger 45W USB-C"]:
        assert a.match(rec(name)).canonical_id == b.match(rec(name)).canonical_id
        assert a.match(rec(name)).state == b.match(rec(name)).state


# ---------------------------------------------------------------- invariants
def test_only_confirmed_is_writable(matcher):
    names = ["x", "Memmory DDR4 16GB 3200MHz", "ssd nvme 1tb", "Laptop Charger 45W USB-C"]
    for m in matcher.match_all(rec(n) for n in names):
        assert m.writable is (m.state is MatchState.CONFIRMED)
    assert matcher.match(rec("y", code="MC-1001")).writable


def test_every_result_explains_itself(matcher):
    for n in ["Laptop Charger 65W USB-C", "Webcam", "Laptop Charger 45W USB-C", "Memmory DDR4 16GB 3200MHz"]:
        assert matcher.match(rec(n)).reason


def test_summarize_counts_all_states(matcher):
    out = summarize(matcher.match_all([rec("Webcam"), rec("x", code="MC-1001")]))
    assert out == {"confirmed": 1, "probable": 0, "conflict": 0, "orphan": 1}
