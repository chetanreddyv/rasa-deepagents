import time
import requests
import json
from pathlib import Path
from datetime import datetime, timezone

RASA_URL = "http://localhost:5005/webhooks/rest/webhook"
SENDER   = "monitor_bot"
POLL_INTERVAL = 30  # seconds

def check_for_incidents():
    """Read .data/incidents.json or work_items.db and return any P1s not yet triaged."""
    db_path = Path(".data/work_items.db")
    if not db_path.exists():
        return []
    import sqlite3
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT id, summary, priority FROM work_items "
            "WHERE priority='urgent' AND status='open' "
            "ORDER BY created_at DESC LIMIT 3"
        ).fetchall()
    return rows

def inject_incident(incident_id, summary, priority):
    """POST a synthetic message into Rasa as the monitor sender."""
    message = f"SYSTEM_ALERT: {priority.upper()} incident detected — {summary} (ref: {incident_id})"
    try:
        resp = requests.post(
            RASA_URL,
            json={"sender": SENDER, "message": message},
            timeout=5,
        )
        print(f"[{datetime.now(timezone.utc).isoformat()}] Injected: {message} → {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print("Rasa not reachable yet, retrying...")

if __name__ == "__main__":
    print(f"Heartbeat monitor started. Polling every {POLL_INTERVAL}s.")
    notified = set()
    while True:
        incidents = check_for_incidents()
        for inc_id, summary, priority in incidents:
            if inc_id not in notified:
                inject_incident(inc_id, summary, priority)
                notified.add(inc_id)
        time.sleep(POLL_INTERVAL)
