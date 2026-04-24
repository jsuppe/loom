"""Ground-truth tests for the TaskQueue bakeoff.

Never shown to Agent B. Agent A knows these exist and their names (via
pytest summary output) but the test bodies are the hidden oracle.
"""
import pytest
from task_queue import TaskQueue


# ---------------------------------------------------------------- REQ-1
class TestAdd:
    def test_add_increases_length(self):
        q = TaskQueue()
        q.add("a")
        q.add("b")
        assert len(q) == 2

    def test_add_rejects_empty_name(self):
        q = TaskQueue()
        with pytest.raises(ValueError):
            q.add("")

    def test_add_default_priority_zero(self):
        q = TaskQueue()
        q.add("a")
        assert q.peek() == ("a", 0)


# ---------------------------------------------------------------- REQ-2
class TestPriorityOrder:
    def test_higher_priority_pops_first(self):
        q = TaskQueue()
        q.add("low", 0)
        q.add("high", 5)
        assert q.pop() == ("high", 5)
        assert q.pop() == ("low", 0)

    def test_fifo_within_same_priority(self):
        q = TaskQueue()
        q.add("first", 0)
        q.add("second", 0)
        q.add("third", 0)
        assert q.pop() == ("first", 0)
        assert q.pop() == ("second", 0)
        assert q.pop() == ("third", 0)

    def test_descending_priority_order_with_ties(self):
        q = TaskQueue()
        q.add("a", 0)
        q.add("b", 1)
        q.add("c", 0)
        q.add("d", 1)
        # p=1 items in insertion order, then p=0 items in insertion order
        assert q.pop() == ("b", 1)
        assert q.pop() == ("d", 1)
        assert q.pop() == ("a", 0)
        assert q.pop() == ("c", 0)


# ---------------------------------------------------------------- REQ-3
class TestPeek:
    def test_peek_returns_next(self):
        q = TaskQueue()
        q.add("x", 2)
        q.add("y", 5)
        assert q.peek() == ("y", 5)

    def test_peek_does_not_remove(self):
        q = TaskQueue()
        q.add("x")
        before = len(q)
        q.peek()
        q.peek()
        assert len(q) == before

    def test_peek_on_empty_returns_none(self):
        q = TaskQueue()
        assert q.peek() is None


# ---------------------------------------------------------------- REQ-4
class TestCancel:
    def test_cancel_returns_true_when_removed(self):
        q = TaskQueue()
        q.add("a")
        assert q.cancel("a") is True
        assert len(q) == 0

    def test_cancel_returns_false_when_missing(self):
        q = TaskQueue()
        q.add("a")
        assert q.cancel("b") is False
        assert len(q) == 1

    def test_cancel_removes_first_insertion_of_duplicate_name(self):
        q = TaskQueue()
        q.add("dup", 0)
        q.add("other", 0)
        q.add("dup", 0)
        q.cancel("dup")
        # First 'dup' removed; order is now [other, dup]
        assert q.pop() == ("other", 0)
        assert q.pop() == ("dup", 0)


# ---------------------------------------------------------------- REQ-5
class TestFilter:
    def test_filter_returns_matching_tasks_in_pop_order(self):
        q = TaskQueue()
        q.add("a", 0)
        q.add("b", 5)
        q.add("c", 0)
        q.add("d", 5)
        result = q.filter(lambda t: t[1] == 5)
        assert result == [("b", 5), ("d", 5)]

    def test_filter_does_not_mutate_queue(self):
        q = TaskQueue()
        q.add("a", 0)
        q.add("b", 1)
        _ = q.filter(lambda t: True)
        assert len(q) == 2
        assert q.pop() == ("b", 1)


# ---------------------------------------------------------------- REQ-6
class TestEmptySemantics:
    def test_pop_on_empty_raises(self):
        q = TaskQueue()
        with pytest.raises(IndexError):
            q.pop()
