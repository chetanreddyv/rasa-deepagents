import pytest
from pathlib import Path
from unittest.mock import patch
import json, tempfile, os

# Point MEMORY_STORE at a temp file so tests don't touch .data/
@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    import actions.tickets as t
    monkeypatch.setattr(t, "MEMORY_STORE", tmp_path / "session_memory.json")

from actions.tickets import append_compact_summary, get_session_context

def test_append_and_retrieve():
    append_compact_summary("user1", "SNAPSHOT task A")
    result = get_session_context("user1")
    assert "SNAPSHOT task A" in result

def test_multiple_summaries_in_order():
    append_compact_summary("user2", "SNAPSHOT task 1")
    append_compact_summary("user2", "SNAPSHOT task 2")
    result = get_session_context("user2")
    assert result.index("task 1") < result.index("task 2")

def test_capped_at_five():
    for i in range(7):
        append_compact_summary("user3", f"SNAPSHOT task {i}")
    import json
    from actions.tickets import MEMORY_STORE, load_memory
    entries = load_memory().get("user3", [])
    assert len(entries) == 5
    assert "task 6" in entries[-1]["summary"]  # most recent kept

def test_empty_sender_returns_empty_string():
    result = get_session_context("nonexistent_user")
    assert result == ""

def test_separate_senders_isolated():
    append_compact_summary("userA", "SNAPSHOT A task")
    append_compact_summary("userB", "SNAPSHOT B task")
    assert "A task" not in get_session_context("userB")
    assert "B task" not in get_session_context("userA")
