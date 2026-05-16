from navigation.set_manager import count_all_sets
from tests.factories import make_set


def test_count_all_sets_empty(db):
    assert count_all_sets() == 0


def test_count_all_sets_with_rows(db):
    make_set(name="A", set_number="1")
    make_set(name="B", set_number="2")
    make_set(name="C", set_number="3")
    assert count_all_sets() == 3


def test_count_all_sets_includes_drafts(db):
    make_set(name="A", set_number="1", status="complete")
    make_set(name="B", set_number="2", status="draft")
    assert count_all_sets() == 2
