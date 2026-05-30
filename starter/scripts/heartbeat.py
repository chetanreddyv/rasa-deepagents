import time
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(".data/work_items.db")

def check_stale_incidents():
    if not DB_PATH.exists():
        return
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        # Find active incidents/tickets that are high or urgent priority
        rows = conn.execute(
            """SELECT id, summary, priority, updated_at 
               FROM work_items 
               WHERE status IN ('open', 'in_progress') 
               AND priority IN ('high', 'urgent')"""
        ).fetchall()
        
        now = datetime.now(timezone.utc)
        for row in rows:
            try:
                updated_at = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
                diff = (now - updated_at).total_seconds()
                
                # If a high priority incident hasn't been updated in 6 minutes
                if diff > 360:
                    print(f"\n[heartbeat] 🚨 Stale {row['priority'].upper()} detected: {row['id']} — '{row['summary']}' — triggering escalation!\n")
                    # In a real app we'd call Rasa's external event trigger API here.
            except Exception as e:
                pass

if __name__ == "__main__":
    print("[heartbeat] Monitoring work_items.db for stale incidents...")
    while True:
        check_stale_incidents()
        time.sleep(10)
