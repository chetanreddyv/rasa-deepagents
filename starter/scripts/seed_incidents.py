import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Ensure we can import from the starter package
sys.path.insert(0, str(Path(__file__).parent.parent))

from actions.work_items import create_item, update_item, get_item

def utc_now_offset(minutes: int = 0) -> str:
    """Return ISO-8601 timestamp in UTC, offset by a number of minutes."""
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return dt.isoformat()

print("Seeding realistic incidents into work_items.db...")

# 1. Stale P1 (to trigger heartbeat immediately)
stale_p1 = create_item(
    kind="incident",
    summary="Payments service is down - 500 errors on checkout",
    category="payments",
    priority="urgent",
    severity="P1",
    status="open",
)
# Make it stale (e.g., 10 minutes old)
update_item(stale_p1["id"])
# Manually edit the DB to make it stale since update_item uses utc_now()
import sqlite3
DB_PATH = Path(".data/work_items.db")
with sqlite3.connect(str(DB_PATH)) as conn:
    stale_time = utc_now_offset(minutes=-10)
    conn.execute("UPDATE work_items SET updated_at = ? WHERE id = ?", (stale_time, stale_p1["id"]))
print(f"✅ Created stale P1: {stale_p1['id']} (10 mins old)")

# 2. In-progress P2
inprogress_p2 = create_item(
    kind="incident",
    summary="Slow database queries causing latency spikes in Auth service",
    category="auth",
    priority="high",
    severity="P2",
    status="in_progress",
    owner="oncall-lead",
)
print(f"✅ Created in-progress P2: {inprogress_p2['id']}")

# 3. Open P3
open_p3 = create_item(
    kind="incident",
    summary="Minor UI glitch on the billing dashboard",
    category="billing",
    priority="medium",
    severity="P3",
    status="open",
)
print(f"✅ Created open P3: {open_p3['id']}")

# 4. Resolved incident with memory
resolved_p2 = create_item(
    kind="incident",
    summary="API Gateway rate limit exceeded",
    category="api",
    priority="high",
    severity="P2",
    status="resolved",
)
print(f"✅ Created resolved P2: {resolved_p2['id']}")

print("\nDone! Start the heartbeat monitor to see the stale P1 get picked up:")
print("python scripts/heartbeat.py")
