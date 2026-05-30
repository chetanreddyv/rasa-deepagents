"""A tiny MCP server exposing mock "internal runbooks" so the ops_assistant
sub-agent has something real to call. Replace these tools with your own APIs.

Run:  make run-mcp   ->  http://localhost:8000/mcp
"""

import json
import sqlite3
from pathlib import Path

from fastmcp import FastMCP

RUNBOOKS = json.loads((Path(__file__).parent / "runbooks.json").read_text(encoding="utf-8"))
mcp = FastMCP("Ops Tools")


@mcp.tool()
def search_runbooks(query: str) -> str:
    """Search internal runbooks by keyword. Returns matching ids and titles."""
    q = query.lower()
    hits = [
        {"id": r["id"], "title": r["title"], "tags": r["tags"]}
        for r in RUNBOOKS
        if q in r["title"].lower() or any(q in t for t in r["tags"]) or any(t in q for t in r["tags"])
    ]
    return json.dumps({"results": hits or [{"note": "no exact match", "all": [r["id"] for r in RUNBOOKS]}]})


@mcp.tool()
def get_runbook(runbook_id: str) -> str:
    """Fetch the full body of a runbook by id, e.g. RB-002."""
    for r in RUNBOOKS:
        if r["id"].lower() == runbook_id.strip().lower():
            return json.dumps(r)
    return json.dumps({"error": f"Runbook {runbook_id} not found."})


@mcp.tool()
def search_past_incidents(service_name: str) -> str:
    """Search past incidents and tickets for a specific service or symptom."""
    # Resolve path relative to THIS file, not CWD
    db_path = Path(__file__).parents[4] / ".data" / "work_items.db"

    if not db_path.exists():
        # Return graceful fallback instead of error so LLM doesn't hallucinate
        return json.dumps({
            "results": [],
            "note": "No incident history found. This may be the first incident for this service."
        })

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # Use SQL LIKE for DB-level filtering instead of Python loop
            pattern = f"%{service_name.lower()}%"
            rows = conn.execute(
                "SELECT id, summary, category, status, priority, created_at "
                "FROM work_items "
                "WHERE lower(summary) LIKE ? OR lower(category) LIKE ? "
                "ORDER BY created_at DESC LIMIT 5",
                (pattern, pattern),
            ).fetchall()
        return json.dumps({"results": [dict(r) for r in rows]})
    except Exception as e:
        return json.dumps({"error": str(e), "results": []})


@mcp.tool()
def get_session_memory(service_name: str = None) -> str:
    """Retrieve the compacted summaries from previous triage sessions. Optionally filter by service name."""
    mem_path = Path(".data/session_memory.json")
    if not mem_path.exists():
        return json.dumps({"results": "No prior sessions found."})
    
    try:
        memory = json.loads(mem_path.read_text(encoding="utf-8"))
        all_entries = []
        for sender_id, entries in memory.items():
            if service_name:
                service_lower = service_name.lower()
                entries = [e for e in entries if service_lower in e.get("summary", "").lower()]
            all_entries.extend(entries)
        # Sort by saved_at desc
        all_entries.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
        return json.dumps({"results": all_entries[:5]})
    except Exception as e:
        return json.dumps({"error": str(e)})



if __name__ == "__main__":
    print("Ops Tools MCP server -> http://localhost:8000/mcp")
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp")
