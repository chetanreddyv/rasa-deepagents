"""Backward-compatible ticket helpers — thin shim over the new work_items store.

Existing code that calls load_tickets(), save_tickets(), new_ticket_id(), etc.
continues to work unchanged.  Under the hood everything goes through SQLite.

On first import the module auto-migrates any legacy .data/tickets.json entries.
"""

from __future__ import annotations

from typing import Any, Dict
import json
from pathlib import Path

from actions.work_items import (
    create_item,
    get_item,
    list_items,
    migrate_legacy_tickets,
    next_id,
    update_item,
    utc_now,
)

# Re-export utc_now so callers don't need to change imports.
__all__ = [
    "load_tickets",
    "save_tickets",
    "new_ticket_id",
    "normalise_ticket_id",
    "utc_now",
]


# ── Auto-migrate legacy JSON on first import ───────────────────────────────
_migrated = migrate_legacy_tickets()
if _migrated:
    print(f"[tickets] Migrated {_migrated} legacy JSON tickets → SQLite")


# ── Compatibility layer ────────────────────────────────────────────────────

def load_tickets() -> Dict[str, Dict[str, Any]]:
    """Return all tickets as {id: {field: value, …}} dict — same shape as before."""
    items = list_items(kind="ticket", limit=9999)
    return {
        item["id"]: {
            "summary": item["summary"],
            "category": item["category"],
            "priority": item["priority"],
            "email": item["reporter_email"],
            "status": item["status"],
            "created_at": item["created_at"],
            # New fields available for callers that want them:
            "severity": item.get("severity", ""),
            "owner": item.get("owner", ""),
            "board_column": item.get("board_column", "backlog"),
            "last_summary": item.get("last_summary", ""),
            "description": item.get("description", ""),
            "updated_at": item.get("updated_at", ""),
        }
        for item in items
    }


def save_tickets(tickets: Dict[str, Dict[str, Any]]) -> None:
    """Upsert tickets into SQLite — kept for backward compat only.

    Prefer create_item() / update_item() from work_items directly.
    """
    for ticket_id, data in tickets.items():
        existing = get_item(ticket_id)
        if existing:
            update_item(
                ticket_id,
                summary=data.get("summary"),
                category=data.get("category"),
                priority=data.get("priority"),
                reporter_email=data.get("email"),
                status=data.get("status"),
            )
        else:
            create_item(
                item_id=ticket_id,
                kind="ticket",
                summary=data.get("summary", ""),
                category=data.get("category", ""),
                priority=data.get("priority", "medium"),
                reporter_email=data.get("email", ""),
                status=data.get("status", "open"),
            )


def new_ticket_id(existing: Dict[str, Dict[str, Any]] | None = None) -> str:
    """Generate the next sequential TCK-#### id."""
    return next_id("TCK")


def normalise_ticket_id(raw: str | None) -> str:
    """Accept 'TCK-1234', 'tck 1234', or bare '1234' and return canonical form 'TCK-####'."""
    if not raw:
        return ""
    # Convert to uppercase, remove spaces, dashes, underscores, hash signs, and the word "TICKET(S)"
    cleaned = raw.upper()
    cleaned = cleaned.replace("TICKETS", "").replace("TICKET", "")
    for char in ["#", "-", "_", " "]:
        cleaned = cleaned.replace(char, "")

    if cleaned.startswith("TCK"):
        digits = cleaned[3:]
    else:
        digits = cleaned

    # Extract only digits
    digits = "".join(c for c in digits if c.isdigit())

    if digits:
        # Format as TCK-#### where #### is 4 digits, zero-padded if length is smaller
        if len(digits) <= 4:
            digits = f"{int(digits):04d}"
        return f"TCK-{digits}"

    return raw.strip()


# ── Session Memory ─────────────────────────────────────────────────────────

MEMORY_STORE = Path(".data/session_memory.json")

def load_memory() -> dict:
    if not MEMORY_STORE.exists():
        return {}
    try:
        return json.loads(MEMORY_STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def save_memory(memory: dict) -> None:
    MEMORY_STORE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_STORE.write_text(json.dumps(memory, indent=2), encoding="utf-8")

def append_compact_summary(sender_id: str, summary: str) -> None:
    memory = load_memory()
    if sender_id not in memory:
        memory[sender_id] = []
    memory[sender_id].append({
        "summary": summary,
        "saved_at": utc_now(),
    })
    # Keep last 5 summaries per sender
    memory[sender_id] = memory[sender_id][-5:]
    save_memory(memory)

def get_session_context(sender_id: str) -> str:
    memory = load_memory()
    entries = memory.get(sender_id, [])
    if not entries:
        return ""
    parts = [e["summary"] for e in entries]
    return "\n\n".join(parts)
