"""Persistent work-item store — the coworker's long-term memory for tickets & incidents.

Uses SQLite so records survive Rasa + action-server restarts.  The schema is
richer than the original flat JSON (status, severity, owner, board_column,
timeline, last_summary, etc.) and is designed to evolve toward full incident
management without breaking existing flows.

All public functions are safe to call from multiple Rasa SDK workers.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Storage location ────────────────────────────────────────────────────────
DB_PATH = Path(".data/work_items.db")

# Thread-local connections for safety in the action server.
_local = threading.local()


@contextmanager
def _conn():
    """Yield a thread-local SQLite connection, auto-committing on success."""
    if not hasattr(_local, "connection") or _local.connection is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.connection = sqlite3.connect(str(DB_PATH))
        _local.connection.row_factory = sqlite3.Row
        _local.connection.execute("PRAGMA journal_mode=WAL")
        _local.connection.execute("PRAGMA foreign_keys=ON")
        _ensure_schema(_local.connection)
    try:
        yield _local.connection
        _local.connection.commit()
    except Exception:
        _local.connection.rollback()
        raise


# ── Schema ──────────────────────────────────────────────────────────────────
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS work_items (
    id              TEXT PRIMARY KEY,       -- e.g. "TCK-1001" or "INC-0042"
    kind            TEXT NOT NULL DEFAULT 'ticket',  -- ticket | incident
    summary         TEXT NOT NULL,
    description     TEXT DEFAULT '',
    category        TEXT DEFAULT '',
    priority        TEXT DEFAULT 'medium',  -- low | medium | high | urgent
    severity        TEXT DEFAULT '',        -- sev1..sev5, empty for tickets
    status          TEXT DEFAULT 'open',    -- open | in_progress | resolved | closed
    owner           TEXT DEFAULT '',        -- assignee
    reporter_email  TEXT DEFAULT '',
    board_column    TEXT DEFAULT 'backlog', -- backlog | todo | doing | review | done
    last_summary    TEXT DEFAULT '',        -- LLM-generated recap of latest state
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     TEXT NOT NULL REFERENCES work_items(id),
    event_type  TEXT NOT NULL,   -- created | status_change | comment | reassign | escalate
    detail      TEXT DEFAULT '',
    actor       TEXT DEFAULT 'system',
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_timeline_item ON timeline_events(item_id);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)


# ── Helpers ─────────────────────────────────────────────────────────────────

def utc_now() -> str:
    """ISO-8601 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


# ── CRUD: Work Items ───────────────────────────────────────────────────────

def next_id(prefix: str = "TCK") -> str:
    """Generate the next sequential ID for a given prefix (TCK or INC)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM work_items WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
            (f"{prefix}-%",),
        ).fetchone()
        if row:
            last_num = int(row["id"].split("-")[1])
            return f"{prefix}-{last_num + 1:04d}"
        return f"{prefix}-1001"


def create_item(
    *,
    item_id: Optional[str] = None,
    kind: str = "ticket",
    summary: str,
    description: str = "",
    category: str = "",
    priority: str = "medium",
    severity: str = "",
    status: str = "open",
    owner: str = "",
    reporter_email: str = "",
    board_column: str = "backlog",
    last_summary: str = "",
) -> Dict[str, Any]:
    """Insert a new work item and return its full dict."""
    prefix = "INC" if kind == "incident" else "TCK"
    if not item_id:
        item_id = next_id(prefix)

    now = utc_now()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO work_items
               (id, kind, summary, description, category, priority, severity,
                status, owner, reporter_email, board_column, last_summary,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_id, kind, summary, description, category, priority,
                severity, status, owner, reporter_email, board_column,
                last_summary, now, now,
            ),
        )
        _add_timeline(conn, item_id, "created", f"{kind} created: {summary}")

    return get_item(item_id)  # type: ignore[return-value]


def get_item(item_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single work item by ID, or None if not found."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM work_items WHERE id = ?", (item_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None


def list_items(
    kind: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List work items, optionally filtered by kind and/or status."""
    clauses: List[str] = []
    params: List[Any] = []
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM work_items {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def update_item(item_id: str, **fields) -> Optional[Dict[str, Any]]:
    """Update one or more fields on a work item.  Returns updated dict or None."""
    allowed = {
        "summary", "description", "category", "priority", "severity",
        "status", "owner", "reporter_email", "board_column", "last_summary",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_item(item_id)

    updates["updated_at"] = utc_now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [item_id]

    with _conn() as conn:
        cur = conn.execute(
            f"UPDATE work_items SET {set_clause} WHERE id = ?", values
        )
        if cur.rowcount == 0:
            return None
        # Record changes on the timeline
        for field, value in updates.items():
            if field != "updated_at":
                _add_timeline(conn, item_id, "field_update", f"{field} → {value}")

    return get_item(item_id)


def delete_item(item_id: str) -> bool:
    """Delete a work item and its timeline. Returns True if it existed."""
    with _conn() as conn:
        conn.execute("DELETE FROM timeline_events WHERE item_id = ?", (item_id,))
        cur = conn.execute("DELETE FROM work_items WHERE id = ?", (item_id,))
        return cur.rowcount > 0


# ── Timeline ───────────────────────────────────────────────────────────────

def _add_timeline(
    conn: sqlite3.Connection,
    item_id: str,
    event_type: str,
    detail: str,
    actor: str = "system",
) -> None:
    conn.execute(
        """INSERT INTO timeline_events (item_id, event_type, detail, actor, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (item_id, event_type, detail, actor, utc_now()),
    )


def add_timeline_event(
    item_id: str,
    event_type: str,
    detail: str,
    actor: str = "system",
) -> None:
    """Public interface: append an event to a work item's timeline."""
    with _conn() as conn:
        _add_timeline(conn, item_id, event_type, detail, actor)


def get_timeline(item_id: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Return the most recent timeline events for a work item."""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM timeline_events WHERE item_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (item_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


# ── Migration: import legacy JSON tickets ──────────────────────────────────

_LEGACY_JSON = Path(".data/tickets.json")


def migrate_legacy_tickets() -> int:
    """One-shot import from the old tickets.json into SQLite.

    Idempotent — skips IDs that already exist.  Returns count of imported items.
    """
    if not _LEGACY_JSON.exists():
        return 0
    try:
        raw = json.loads(_LEGACY_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    imported = 0
    for ticket_id, data in raw.items():
        if get_item(ticket_id) is not None:
            continue
        create_item(
            item_id=ticket_id,
            kind="ticket",
            summary=data.get("summary", ""),
            category=data.get("category", ""),
            priority=data.get("priority", "medium"),
            reporter_email=data.get("email", ""),
            status=data.get("status", "open"),
        )
        imported += 1
    return imported
