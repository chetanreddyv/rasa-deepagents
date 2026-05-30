from typing import Any, Dict, List

from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.actions import (
    ActionCreateTicket,
    ActionLookupTicket,
    ActionUpdateTicketStatus,
)
from actions import work_items


class DummyDispatcher(CollectingDispatcher):
    def __init__(self):
        super().__init__()


def _tracker_with_slots(slots: Dict[str, Any]) -> Tracker:
    return Tracker(
        sender_id="test",
        slots=slots,
        latest_message={"text": "", "intent": {}, "entities": []},
        events=[],
        paused=False,
        followup_action=None,
        active_loop={},
        latest_action_name=None,
    )


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


def test_action_create_ticket_valid():
    tracker = _tracker_with_slots(
        {
            "issue_summary": "Wrong invoice totals",
            "issue_category": "billing",
            "issue_priority": "urgent",
            "contact_email": "rod@example.com",
        }
    )
    dispatcher = DummyDispatcher()
    action = ActionCreateTicket()

    events: List[Dict[str, Any]] = action.run(dispatcher, tracker, {})
    slot_events = {e["name"]: e["value"] for e in events if isinstance(e, dict) and e.get("event") == "slot"}

    assert slot_events["inputs_valid"] is True
    assert slot_events["ticket_id"].startswith("TCK-")

    item = work_items.get_item(slot_events["ticket_id"])
    assert item is not None
    assert item["summary"] == "Wrong invoice totals"
    assert item["priority"] == "urgent"
    assert item["category"] == "billing"


def test_action_create_ticket_invalid_email():
    tracker = _tracker_with_slots(
        {
            "issue_summary": "Bad",
            "issue_category": "billing",
            "issue_priority": "urgent",
            "contact_email": "not-an-email",
        }
    )
    dispatcher = DummyDispatcher()
    action = ActionCreateTicket()

    events = action.run(dispatcher, tracker, {})
    slot_events = {e["name"]: e["value"] for e in events if isinstance(e, dict) and e.get("event") == "slot"}

    assert slot_events["inputs_valid"] is False
    assert slot_events["ticket_id"] is None


def test_action_lookup_ticket_found_and_not_found():
    # create a ticket directly in the store
    item = work_items.create_item(kind="ticket", summary="Foo")
    tracker_found = _tracker_with_slots({"lookup_ticket_id": item["id"]})
    tracker_missing = _tracker_with_slots({"lookup_ticket_id": "TCK-9999"})

    dispatcher = DummyDispatcher()
    action = ActionLookupTicket()

    events_found = action.run(dispatcher, tracker_found, {})
    slots_found = {e["name"]: e["value"] for e in events_found if isinstance(e, dict) and e.get("event") == "slot"}
    assert slots_found["ticket_found"] is True
    assert slots_found["ticket_status"] == item["status"]

    events_missing = action.run(dispatcher, tracker_missing, {})
    slots_missing = {e["name"]: e["value"] for e in events_missing if isinstance(e, dict) and e.get("event") == "slot"}
    assert slots_missing["ticket_found"] is False
    assert slots_missing["ticket_status"] == "unknown"


def test_action_update_ticket_status_normalization():
    item = work_items.create_item(kind="ticket", summary="Foo", status="open")
    tracker = _tracker_with_slots(
        {"update_ticket_id": item["id"], "new_ticket_status": "mark this as in progress"}
    )
    dispatcher = DummyDispatcher()
    action = ActionUpdateTicketStatus()

    events = action.run(dispatcher, tracker, {})
    slots = {e["name"]: e["value"] for e in events if isinstance(e, dict) and e.get("event") == "slot"}

    assert slots["update_success"] is True
    assert slots["new_ticket_status"] == "in_progress"

    updated = work_items.get_item(item["id"])
    assert updated["status"] == "in_progress"
