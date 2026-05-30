"""Agent-internal scratchpad — the coworker's planning and progress-tracking memory.

This is NOT a user-facing to-do list.  It is the agent's own cognitive state:
an internal working memory inspired by Claude Code's task tracking, LangGraph's
agent state, and ReAct-style plan-and-execute loops.

Purpose:
  1. When the agent starts a complex objective (e.g. incident triage), it records
     its PLAN — what steps it intends to take.
  2. As the agent completes each step, it marks it done and optionally adds notes.
  3. The current plan is injected into the LLM command prompt so the agent
     ALWAYS sees its own plan, preventing drift during long conversations.
  4. When the objective is complete, the plan is marked done.

Backed by SQLite (same DB as work_items) so state survives restarts.
Thread-safe for the Rasa SDK multi-worker action server.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Storage — shares the same DB file as work_items ─────────────────────────
DB_PATH = Path(".data/work_items.db")

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
-- Each objective is a high-level goal the agent is pursuing.
CREATE TABLE IF NOT EXISTS agent_objectives (
    id              TEXT PRIMARY KEY,       -- e.g. "OBJ-0001"
    sender_id       TEXT NOT NULL,          -- conversation / user scope
    title           TEXT NOT NULL,          -- "Triage incident TCK-1002"
    linked_item     TEXT DEFAULT '',        -- ticket/incident id if applicable
    status          TEXT DEFAULT 'active',  -- active | completed | abandoned
    created_at      TEXT NOT NULL,
    completed_at    TEXT DEFAULT ''
);

-- Each step is one planned action within an objective.
CREATE TABLE IF NOT EXISTS agent_steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    objective_id    TEXT NOT NULL REFERENCES agent_objectives(id),
    step_number     INTEGER NOT NULL,       -- ordering within the plan
    description     TEXT NOT NULL,           -- "Collect issue details"
    status          TEXT DEFAULT 'pending',  -- pending | in_progress | done | skipped
    notes           TEXT DEFAULT '',         -- agent's internal notes/observations
    created_at      TEXT NOT NULL,
    completed_at    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_steps_objective ON agent_steps(objective_id);
CREATE INDEX IF NOT EXISTS idx_objectives_sender ON agent_objectives(sender_id);
CREATE INDEX IF NOT EXISTS idx_objectives_status ON agent_objectives(status);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


# ── ID generation ──────────────────────────────────────────────────────────

def _next_objective_id() -> str:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM agent_objectives ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            try:
                last_num = int(row["id"].split("-")[1])
                return f"OBJ-{last_num + 1:04d}"
            except (IndexError, ValueError):
                pass
        return "OBJ-0001"


# ── Objectives CRUD ────────────────────────────────────────────────────────

def create_objective(
    *,
    sender_id: str,
    title: str,
    steps: List[str],
    linked_item: str = "",
) -> Dict[str, Any]:
    """Create a new objective with its planned steps.

    Args:
        sender_id: The conversation/user this objective belongs to.
        title: High-level description of what the agent is trying to accomplish.
        steps: Ordered list of step descriptions (the agent's plan).
        linked_item: Optional ticket/incident ID this objective relates to.

    Returns:
        The full objective dict including its steps.
    """
    obj_id = _next_objective_id()
    now = _utc_now()

    with _conn() as conn:
        conn.execute(
            """INSERT INTO agent_objectives
               (id, sender_id, title, linked_item, status, created_at)
               VALUES (?, ?, ?, ?, 'active', ?)""",
            (obj_id, sender_id, title, linked_item, now),
        )
        for i, desc in enumerate(steps, 1):
            conn.execute(
                """INSERT INTO agent_steps
                   (objective_id, step_number, description, status, created_at)
                   VALUES (?, ?, ?, 'pending', ?)""",
                (obj_id, i, desc, now),
            )

    return get_objective(obj_id)  # type: ignore[return-value]


def get_objective(obj_id: str) -> Optional[Dict[str, Any]]:
    """Fetch an objective with all its steps."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM agent_objectives WHERE id = ?", (obj_id,)
        ).fetchone()
        if not row:
            return None
        obj = _row_to_dict(row)
        step_rows = conn.execute(
            "SELECT * FROM agent_steps WHERE objective_id = ? ORDER BY step_number",
            (obj_id,),
        ).fetchall()
        obj["steps"] = [_row_to_dict(s) for s in step_rows]
        return obj


def get_active_objective(sender_id: str) -> Optional[Dict[str, Any]]:
    """Get the current active objective for a sender (most recent)."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT * FROM agent_objectives
               WHERE sender_id = ? AND status = 'active'
               ORDER BY created_at DESC LIMIT 1""",
            (sender_id,),
        ).fetchone()
        if not row:
            return None
        obj = _row_to_dict(row)
        step_rows = conn.execute(
            "SELECT * FROM agent_steps WHERE objective_id = ? ORDER BY step_number",
            (obj["id"],),
        ).fetchall()
        obj["steps"] = [_row_to_dict(s) for s in step_rows]
        return obj


def complete_objective(obj_id: str) -> Optional[Dict[str, Any]]:
    """Mark an objective as completed."""
    now = _utc_now()
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE agent_objectives SET status = 'completed', completed_at = ? WHERE id = ?",
            (now, obj_id),
        )
        if cur.rowcount == 0:
            return None
    return get_objective(obj_id)


def abandon_objective(obj_id: str) -> Optional[Dict[str, Any]]:
    """Mark an objective as abandoned (user changed direction)."""
    now = _utc_now()
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE agent_objectives SET status = 'abandoned', completed_at = ? WHERE id = ?",
            (now, obj_id),
        )
        if cur.rowcount == 0:
            return None
    return get_objective(obj_id)


# ── Steps CRUD ─────────────────────────────────────────────────────────────

def advance_step(obj_id: str, step_number: int, notes: str = "") -> Optional[Dict[str, Any]]:
    """Mark a step as done and optionally add agent notes."""
    now = _utc_now()
    with _conn() as conn:
        conn.execute(
            """UPDATE agent_steps
               SET status = 'done', notes = ?, completed_at = ?
               WHERE objective_id = ? AND step_number = ?""",
            (notes, now, obj_id, step_number),
        )
        # Auto-advance the next pending step to in_progress
        conn.execute(
            """UPDATE agent_steps
               SET status = 'in_progress'
               WHERE objective_id = ? AND step_number = ? AND status = 'pending'""",
            (obj_id, step_number + 1),
        )
    return get_objective(obj_id)


def start_step(obj_id: str, step_number: int) -> Optional[Dict[str, Any]]:
    """Mark a step as in_progress."""
    with _conn() as conn:
        conn.execute(
            """UPDATE agent_steps SET status = 'in_progress'
               WHERE objective_id = ? AND step_number = ?""",
            (obj_id, step_number),
        )
    return get_objective(obj_id)


def skip_step(obj_id: str, step_number: int, reason: str = "") -> Optional[Dict[str, Any]]:
    """Mark a step as skipped."""
    now = _utc_now()
    with _conn() as conn:
        conn.execute(
            """UPDATE agent_steps
               SET status = 'skipped', notes = ?, completed_at = ?
               WHERE objective_id = ? AND step_number = ?""",
            (reason, now, obj_id, step_number),
        )
    return get_objective(obj_id)


def add_step_notes(obj_id: str, step_number: int, notes: str) -> None:
    """Append notes to a step (agent's observations)."""
    with _conn() as conn:
        existing = conn.execute(
            "SELECT notes FROM agent_steps WHERE objective_id = ? AND step_number = ?",
            (obj_id, step_number),
        ).fetchone()
        if existing:
            current = existing["notes"] or ""
            updated = f"{current}\n{notes}".strip() if current else notes
            conn.execute(
                "UPDATE agent_steps SET notes = ? WHERE objective_id = ? AND step_number = ?",
                (updated, obj_id, step_number),
            )


# ── Plan rendering (for LLM prompt injection) ─────────────────────────────

_STATUS_ICONS = {
    "pending": "○",
    "in_progress": "▶",
    "done": "✓",
    "skipped": "—",
}


def render_plan(sender_id: str) -> str:
    """Render the active objective as a concise text block for prompt injection.

    Returns an empty string if there's no active objective — the prompt template
    can check for this and skip the section entirely.

    Example output:
        OBJECTIVE: Triage incident TCK-1002 [OBJ-0001]
        ✓ 1. Create incident ticket (done — created TCK-1002)
        ▶ 2. Gather severity and impact details (in progress)
        ○ 3. Check for related open tickets
        ○ 4. Assign an owner
        PROGRESS: 1/4 steps done
    """
    obj = get_active_objective(sender_id)
    if not obj:
        return ""

    lines = [f"OBJECTIVE: {obj['title']} [{obj['id']}]"]
    if obj.get("linked_item"):
        lines[0] += f" (linked: {obj['linked_item']})"

    done_count = 0
    total = len(obj.get("steps", []))

    for step in obj.get("steps", []):
        icon = _STATUS_ICONS.get(step["status"], "?")
        line = f"  {icon} {step['step_number']}. {step['description']}"
        if step["status"] == "done":
            done_count += 1
            if step.get("notes"):
                line += f" (done — {step['notes']})"
            else:
                line += " (done)"
        elif step["status"] == "in_progress":
            line += " (in progress)"
        elif step["status"] == "skipped" and step.get("notes"):
            line += f" (skipped — {step['notes']})"
        lines.append(line)

    lines.append(f"PROGRESS: {done_count}/{total} steps done")

    return "\n".join(lines)


def get_progress_summary(sender_id: str) -> Dict[str, Any]:
    """Return a structured progress summary for slot injection."""
    obj = get_active_objective(sender_id)
    if not obj:
        return {"has_plan": False, "summary": "No active objective."}

    steps = obj.get("steps", [])
    done = sum(1 for s in steps if s["status"] == "done")
    total = len(steps)
    current = next((s for s in steps if s["status"] == "in_progress"), None)
    next_pending = next((s for s in steps if s["status"] == "pending"), None)

    return {
        "has_plan": True,
        "objective_id": obj["id"],
        "title": obj["title"],
        "linked_item": obj.get("linked_item", ""),
        "done": done,
        "total": total,
        "current_step": current["description"] if current else None,
        "next_step": next_pending["description"] if next_pending else None,
        "all_done": done == total,
        "summary": render_plan(sender_id),
    }


# ── Plan templates for common flows ───────────────────────────────────────
# Pre-built step lists the agent can use when starting well-known flows.

PLAN_TEMPLATES = {
    "support_ticket": {
        "title": "Log a new support ticket",
        "steps": [
            "Collect issue summary from user",
            "Determine issue category (bug/billing/access/other)",
            "Assess priority level",
            "Get contact email for updates",
            "Create the ticket in the system",
            "Confirm ticket creation to user",
        ],
    },
    "incident_triage": {
        "title": "Triage and manage incident",
        "steps": [
            "Identify the incident and severity",
            "Create or locate the incident ticket",
            "Gather impact details (affected systems, users, timeline)",
            "Check for related open tickets or known issues",
            "Assign an owner / escalation path",
            "Summarize current state and next actions",
        ],
    },
    "ticket_investigation": {
        "title": "Investigate existing ticket",
        "steps": [
            "Look up the ticket by ID",
            "Review current status and history",
            "Provide status summary to user",
            "Determine if any action is needed",
        ],
    },
    "ticket_update": {
        "title": "Update ticket status",
        "steps": [
            "Identify the ticket to update",
            "Determine the new status",
            "Apply the update",
            "Confirm the change to user",
        ],
    },
}
