import pytest

from entity_matcher import Canonical, Executor, Matcher, NotWritable, Proposal, Record, split
from entity_matcher.gate import assert_writable

MATCHER = Matcher([
    Canonical("P-001", "Laptop Charger 65W USB-C", "MC-1001"),
    Canonical("P-004", "Memory DDR4 16GB 3200MHz", "MC-1004"),
])


def confirmed():
    return MATCHER.match(Record("sales", "S-1", "anything", "MC-1001"))


def probable():
    return MATCHER.match(Record("sales", "S-2", "Memmory DDR4 16GB 3200MHz"))


def conflict():
    return MATCHER.match(Record("sales", "S-3", "Memory DDR4 32GB 3200MHz"))


def orphan():
    return MATCHER.match(Record("sales", "S-4", "Webcam"))


def prop(match, value=10.0, field="cost"):
    return Proposal(match, field, value, proposed_by="cost-agent")


@pytest.mark.parametrize("factory", [probable, conflict, orphan])
def test_non_confirmed_can_never_be_written(factory):
    with pytest.raises(NotWritable):
        assert_writable(prop(factory()))


def test_split_routes_uncertain_matches_to_review():
    ps = [prop(confirmed()), prop(probable()), prop(conflict()), prop(orphan())]
    writable, review = split(ps)
    assert len(writable) == 1 and len(review) == 3


def test_dry_run_is_the_default_and_changes_nothing():
    target = {}
    ex = Executor(target)
    out = ex.apply([prop(confirmed())])
    assert out.dry_run is True
    assert target == {}
    assert len(ex.audit) == 1 and ex.audit[0]["dry_run"] is True


def test_real_run_writes_only_confirmed():
    target = {}
    ex = Executor(target, dry_run=False)
    out = ex.apply([prop(confirmed(), 12.5), prop(probable(), 99), prop(orphan(), 1)])
    assert target == {"P-001": {"cost": 12.5}}
    assert len(out.applied) == 1 and len(out.queued_for_review) == 2


def test_same_proposal_twice_is_written_once():
    target, ledger = {}, set()
    ex = Executor(target, dry_run=False, ledger=ledger)
    ex.apply([prop(confirmed(), 12.5)])
    out = ex.apply([prop(confirmed(), 12.5)])
    assert out.skipped_duplicate and not out.applied
    assert len(ex.audit) == 1


def test_new_value_is_a_new_write_with_before_and_after():
    target = {}
    ex = Executor(target, dry_run=False)
    ex.apply([prop(confirmed(), 12.5)])
    ex.apply([prop(confirmed(), 13.0)])
    assert target["P-001"]["cost"] == 13.0
    assert ex.audit[-1]["before"] == 12.5 and ex.audit[-1]["after"] == 13.0


def test_proposal_key_is_stable_and_content_based():
    a, b = prop(confirmed(), 1.0), prop(confirmed(), 1.0)
    assert a.key == b.key
    assert prop(confirmed(), 2.0).key != a.key
    assert prop(confirmed(), 1.0, field="price").key != a.key


def test_audit_records_who_proposed():
    ex = Executor({}, dry_run=False)
    ex.apply([prop(confirmed())])
    assert ex.audit[0]["proposed_by"] == "cost-agent"
