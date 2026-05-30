from unittest.mock import MagicMock, patch
from actions.actions import ActionCompletePlan
from rasa_sdk.events import SlotSet

def make_tracker(slots: dict, sender_id="test_user"):
    tracker = MagicMock()
    tracker.sender_id = sender_id
    tracker.current_slot_values.return_value = slots
    return tracker

@patch("actions.actions.get_active_objective")
@patch("actions.actions.complete_objective")
def test_compact_sets_agent_context_summary(mock_complete, mock_get_active, tmp_path, monkeypatch):
    import actions.tickets as t
    monkeypatch.setattr(t, "MEMORY_STORE", tmp_path / "mem.json")
    
    mock_get_active.return_value = {"id": "OBJ-123"}

    action = ActionCompletePlan()
    tracker = make_tracker({
        "issue_summary": "login broken",
        "issue_category": "bug",
        "issue_priority": "urgent",
        "contact_email": "dev@co.com",
        "ticket_id": "TCK-0001",
        "return_value": None,
        "agent_context_summary": None,
    })
    dispatcher = MagicMock()
    domain = {}

    events = action.run(dispatcher, tracker, domain)
    
    slot_events = {e["name"]: e["value"] for e in events if e.get("event") == "slot"}
    assert "agent_context_summary" in slot_events
    assert "login broken" in slot_events["agent_context_summary"]
    assert "urgent" in slot_events["agent_context_summary"]

@patch("actions.actions.get_active_objective")
@patch("actions.actions.complete_objective")
def test_compact_skips_null_slots(mock_complete, mock_get_active, tmp_path, monkeypatch):
    import actions.tickets as t
    monkeypatch.setattr(t, "MEMORY_STORE", tmp_path / "mem.json")
    
    mock_get_active.return_value = {"id": "OBJ-123"}

    action = ActionCompletePlan()
    tracker = make_tracker({
        "issue_summary": "disk full",
        "issue_category": None,   # not yet filled
        "return_value": None,
    })
    dispatcher, domain = MagicMock(), {}
    events = action.run(dispatcher, tracker, domain)

    slot_events = {e["name"]: e["value"] for e in events if e.get("event") == "slot"}
    assert "issue_category" not in slot_events["agent_context_summary"]
    assert "disk full" in slot_events["agent_context_summary"]
