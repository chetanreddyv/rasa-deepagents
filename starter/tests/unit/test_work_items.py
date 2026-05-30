import os
from pathlib import Path

from actions import work_items


def setup_function(_):
    # Close any open connection and start each test with a fresh DB
    if hasattr(work_items._local, "connection") and work_items._local.connection is not None:
        try:
            work_items._local.connection.close()
        except Exception:
            pass
        work_items._local.connection = None

    db_path = work_items.DB_PATH
    if db_path.exists():
        db_path.unlink()


def test_create_and_get_item():
    item = work_items.create_item(
        kind="ticket",
        summary="Test ticket",
        category="billing",
        priority="high",
        reporter_email="user@example.com",
        status="open",
    )
    assert item["id"].startswith("TCK-")
    assert item["summary"] == "Test ticket"

    fetched = work_items.get_item(item["id"])
    assert fetched is not None
    assert fetched["id"] == item["id"]
    assert fetched["status"] == "open"


def test_update_item_and_timeline():
    item = work_items.create_item(
        kind="ticket",
        summary="Initial",
        status="open",
    )
    updated = work_items.update_item(item["id"], status="in_progress", owner="alice")
    assert updated is not None
    assert updated["status"] == "in_progress"
    assert updated["owner"] == "alice"

    history = work_items.get_timeline(item["id"])
    # at least: created + two field_update events
    assert any(ev["event_type"] == "created" for ev in history)
    assert any("status" in ev["detail"] for ev in history)
    assert any("owner" in ev["detail"] for ev in history)


def test_list_items_filters_by_kind_and_status():
    t1 = work_items.create_item(kind="ticket", summary="t1", status="open")
    t2 = work_items.create_item(kind="ticket", summary="t2", status="closed")
    i1 = work_items.create_item(kind="incident", summary="i1", status="open")

    open_tickets = work_items.list_items(kind="ticket", status="open")
    assert {it["id"] for it in open_tickets} == {t1["id"]}

    incidents = work_items.list_items(kind="incident")
    assert {it["id"] for it in incidents} == {i1["id"]}
