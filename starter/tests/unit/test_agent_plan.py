from typing import Any, Dict, List
import sqlite3
from pathlib import Path

from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.actions import ActionInitPlan, ActionAdvanceStep
from actions import scratchpad

class DummyDispatcher(CollectingDispatcher):
    def __init__(self):
        super().__init__()
        self.messages = []

    def utter_message(self, text: str = None, **kwargs):
        self.messages.append(text)

def _tracker_with_slots(slots: Dict[str, Any], events: List[Dict[str, Any]] = None) -> Tracker:
    return Tracker(
        sender_id="test",
        slots=slots,
        latest_message={"text": "", "intent": {}, "entities": []},
        events=events or [],
        paused=False,
        followup_action=None,
        active_loop={},
        latest_action_name=None,
    )

def setup_function(_):
    if hasattr(scratchpad._local, "connection") and scratchpad._local.connection is not None:
        try:
            scratchpad._local.connection.close()
        except Exception:
            pass
        scratchpad._local.connection = None
        
    db_path = scratchpad.DB_PATH
    wall_path = db_path.with_name(db_path.name + "-wal")
    shm_path = db_path.with_name(db_path.name + "-shm")
    for p in [db_path, wall_path, shm_path]:
        if p.exists():
            p.unlink()

def test_missing_plan_template_silence():
    tracker = _tracker_with_slots({})
    dispatcher = DummyDispatcher()
    action = ActionInitPlan()
    events = action.run(dispatcher, tracker, {})
    slot_events = {e["name"]: e["value"] for e in events if e.get("event") == "slot"}
    
    assert dispatcher.messages[0] == "[Internal: plan_template not set or unknown. Skipping plan init.]"
    assert "agent_plan" not in slot_events

def test_step_ordering_is_deterministic():
    tracker_init = _tracker_with_slots({"plan_template": "ticket_update", "update_ticket_id": "TCK-1234"})
    dispatcher = DummyDispatcher()
    init_action = ActionInitPlan()
    events = init_action.run(dispatcher, tracker_init, {})
    
    slots = {e["name"]: e["value"] for e in events if e.get("event") == "slot"}
    obj_id = slots["agent_objective_id"]
    
    tracker_advance = _tracker_with_slots({
        "agent_objective_id": obj_id,
        "advance_step_number": "5",
        "update_ticket_id": "TCK-1234"
    }, events=[])
    
    advance_action = ActionAdvanceStep()
    advance_events = advance_action.run(dispatcher, tracker_advance, {})
    
    plan_text = next(e["value"] for e in advance_events if e.get("name") == "agent_plan")
    assert "2." in plan_text
    assert "5." not in plan_text or "(pending)" in plan_text
