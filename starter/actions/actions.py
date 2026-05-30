"""Custom actions for the AI coworker.

Principle (from the Rasa playbook): flows own the *conversation logic*; actions do
the *raw work* and hand results back as slots for the flow to branch on.

All actions read/write to the persistent SQLite work-item store so state survives
Rasa + action-server restarts.
"""

from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

from actions.work_items import (
    create_item,
    get_item,
    list_items,
    update_item,
    utc_now,
)
from actions.tickets import normalise_ticket_id


# ── Create Ticket ───────────────────────────────────────────────────────────

class ActionCreateTicket(Action):
    def name(self) -> Text:
        return "action_create_ticket"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        summary = tracker.get_slot("issue_summary")
        category = tracker.get_slot("issue_category")
        priority = tracker.get_slot("issue_priority")
        email = tracker.get_slot("contact_email")
        
        print(f"ActionCreateTicket called: summary={summary}, category={category}, priority={priority}, email={email}")

        # Clean and normalize priority
        if isinstance(priority, str):
            priority_lower = priority.lower().strip()
            if "urgent" in priority_lower:
                priority = "urgent"
            elif "high" in priority_lower:
                priority = "high"
            elif "med" in priority_lower:
                priority = "medium"
            elif "low" in priority_lower:
                priority = "low"

        # Clean and normalize category
        if isinstance(category, str):
            category_lower = category.lower().strip()
            if "bug" in category_lower:
                category = "bug"
            elif "bill" in category_lower or "pay" in category_lower:
                category = "billing"
            elif "access" in category_lower or "login" in category_lower or "auth" in category_lower:
                category = "access"
            elif "other" in category_lower or "something else" in category_lower:
                category = "other"

        print(f"ActionCreateTicket normalized: summary={summary}, category={category}, priority={priority}, email={email}")

        # Validate inputs
        inputs_valid = True
        if not email or not isinstance(email, str) or "@" not in email or "." not in email.split("@")[-1]:
            inputs_valid = False
        if category not in ["bug", "billing", "access", "other"]:
            inputs_valid = False
        if priority not in ["low", "medium", "high", "urgent"]:
            inputs_valid = False
        if not summary or not isinstance(summary, str) or not summary.strip():
            inputs_valid = False

        print(f"ActionCreateTicket validation: inputs_valid={inputs_valid}")

        if not inputs_valid:
            return [
                SlotSet("inputs_valid", False),
                SlotSet("ticket_id", None),
            ]

        # Persist to SQLite via the work_items store
        item = create_item(
            kind="ticket",
            summary=summary,
            category=category,
            priority=priority,
            reporter_email=email,
            status="open",
            board_column="backlog",
        )
        ticket_id = item["id"]

        print(f"ActionCreateTicket created ticket: {ticket_id}")
        return [
            SlotSet("inputs_valid", True),
            SlotSet("ticket_id", ticket_id),
            SlotSet("issue_category", category),
            SlotSet("issue_priority", priority),
        ]


# ── Lookup Ticket ──────────────────────────────────────────────────────────

class ActionLookupTicket(Action):
    def name(self) -> Text:
        return "action_lookup_ticket"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        raw_ticket_id = tracker.get_slot("lookup_ticket_id")
        print(f"ActionLookupTicket called: raw_ticket_id={raw_ticket_id}")
        if not raw_ticket_id or not isinstance(raw_ticket_id, str):
            return [
                SlotSet("ticket_found", False),
                SlotSet("lookup_ticket_id", None),
                SlotSet("ticket_status", "unknown"),
                SlotSet("ticket_summary", "None"),
            ]

        ticket_id = normalise_ticket_id(raw_ticket_id)
        # Read directly from persistent SQLite store
        item = get_item(ticket_id)
        print(f"ActionLookupTicket lookup: ticket_id={ticket_id}, found={item is not None}")
        if not item:
            return [
                SlotSet("ticket_found", False),
                SlotSet("lookup_ticket_id", ticket_id),
                SlotSet("ticket_status", "unknown"),
                SlotSet("ticket_summary", "None"),
            ]
        return [
            SlotSet("ticket_found", True),
            SlotSet("lookup_ticket_id", ticket_id),
            SlotSet("ticket_status", item.get("status", "open")),
            SlotSet("ticket_summary", item.get("summary", "")),
            SlotSet("ticket_priority", item.get("priority", "")),
            SlotSet("ticket_owner", item.get("owner", "unassigned")),
        ]


# ── List Tickets ───────────────────────────────────────────────────────────

class ActionListTickets(Action):
    """Return a formatted list of recent tickets/incidents from the persistent store."""

    def name(self) -> Text:
        return "action_list_tickets"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        status_filter = tracker.get_slot("list_status_filter")
        items = list_items(kind="ticket", status=status_filter, limit=10)
        print(f"ActionListTickets called: status_filter={status_filter}, found={len(items)} items")

        if not items:
            msg = "No tickets found."
            if status_filter:
                msg = f"No {status_filter} tickets found."
            dispatcher.utter_message(text=msg)
            return [
                SlotSet("tickets_found", False),
                SlotSet("ticket_list_text", msg),
            ]

        lines = []
        for item in items:
            owner = item.get("owner") or "unassigned"
            lines.append(
                f"• **{item['id']}** [{item['status']}] {item['priority']} — "
                f"{item['summary'][:60]}{'…' if len(item['summary']) > 60 else ''} "
                f"(owner: {owner})"
            )
        text = "\n".join(lines)
        dispatcher.utter_message(text=f"Here are your tickets:\n{text}")
        return [
            SlotSet("tickets_found", True),
            SlotSet("ticket_list_text", text),
        ]


# ── Update Ticket Status ──────────────────────────────────────────────────

class ActionUpdateTicketStatus(Action):
    """Update the status of an existing ticket in the persistent store."""

    def name(self) -> Text:
        return "action_update_ticket_status"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        raw_ticket_id = tracker.get_slot("update_ticket_id")
        new_status = tracker.get_slot("new_ticket_status")

        print(f"ActionUpdateTicketStatus called: raw_id={raw_ticket_id}, new_status={new_status}")

        if not raw_ticket_id or not isinstance(raw_ticket_id, str):
            return [SlotSet("update_success", False)]

        ticket_id = normalise_ticket_id(raw_ticket_id)

        # Normalize status
        if isinstance(new_status, str):
            status_lower = new_status.lower().strip().replace(" ", "_")
            valid_statuses = {"open", "in_progress", "resolved", "closed"}
            # Fuzzy match
            if "progress" in status_lower or "work" in status_lower:
                new_status = "in_progress"
            elif "resolve" in status_lower or "fix" in status_lower:
                new_status = "resolved"
            elif "close" in status_lower or "done" in status_lower:
                new_status = "closed"
            elif "open" in status_lower or "reopen" in status_lower:
                new_status = "open"
            elif status_lower not in valid_statuses:
                return [SlotSet("update_success", False)]

        updated = update_item(ticket_id, status=new_status)
        if not updated:
            print(f"ActionUpdateTicketStatus: ticket {ticket_id} not found")
            return [SlotSet("update_success", False)]

        print(f"ActionUpdateTicketStatus: {ticket_id} → {new_status}")
        return [
            SlotSet("update_success", True),
            SlotSet("update_ticket_id", ticket_id),
            SlotSet("new_ticket_status", new_status),
        ]


# ── Agent-Internal Scratchpad ──────────────────────────────────────────────
# The agent's own planning and progress-tracking memory.  NOT user-facing.
# Inspired by Claude Code's task tracking, LangGraph agent state, and
# ReAct plan-and-execute loops.  Prevents drift in long conversations by
# keeping the agent's plan visible in every LLM turn.

from actions.scratchpad import (  # noqa: E402
    PLAN_TEMPLATES,
    advance_step,
    complete_objective,
    create_objective,
    get_active_objective,
    get_progress_summary,
    render_plan,
    start_step,
)


class ActionInitPlan(Action):
    """Create an objective with planned steps when the agent starts a complex flow.

    Called at the beginning of multi-step flows.  Reads `plan_template` slot to
    pick a pre-built plan, or accepts a custom plan via `plan_steps` slot.
    """

    def name(self) -> Text:
        return "action_init_plan"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        sender_id = tracker.sender_id or "default"
        template_name = tracker.get_slot("plan_template") or ""
        linked_item = tracker.get_slot("plan_linked_item") or ""

        # Check if there's already an active objective
        existing = get_active_objective(sender_id)
        if existing:
            print(f"ActionInitPlan: active plan already exists — {existing['id']}: {existing['title']}")
            plan_text = render_plan(sender_id)
            return [
                SlotSet("agent_plan", plan_text),
                SlotSet("agent_objective_id", existing["id"]),
            ]

        # Resolve the template
        template = PLAN_TEMPLATES.get(template_name, {})
        title = template.get("title", f"Handle user request ({template_name})")
        steps = template.get("steps", ["Understand the request", "Execute", "Confirm with user"])

        obj = create_objective(
            sender_id=sender_id,
            title=title,
            steps=steps,
            linked_item=linked_item,
        )
        print(f"ActionInitPlan created: {obj['id']} — {title} ({len(steps)} steps)")

        # Mark step 1 as in_progress
        start_step(obj["id"], 1)

        plan_text = render_plan(sender_id)
        return [
            SlotSet("agent_plan", plan_text),
            SlotSet("agent_objective_id", obj["id"]),
        ]


class ActionAdvanceStep(Action):
    """Mark the current step as done and advance to the next one.

    Called between steps in a flow.  Reads `advance_step_number` to know which
    step just finished, and `advance_step_notes` for any agent observations.
    """

    def name(self) -> Text:
        return "action_advance_step"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        sender_id = tracker.sender_id or "default"
        obj = get_active_objective(sender_id)
        if not obj:
            print("ActionAdvanceStep: no active plan")
            return [SlotSet("agent_plan", "")]

        step_number = tracker.get_slot("advance_step_number")
        notes = tracker.get_slot("advance_step_notes") or ""

        # If no explicit step number, find the current in_progress step
        if not step_number:
            for s in obj.get("steps", []):
                if s["status"] == "in_progress":
                    step_number = s["step_number"]
                    break
            if not step_number:
                # Find the first pending step
                for s in obj.get("steps", []):
                    if s["status"] == "pending":
                        step_number = s["step_number"]
                        break

        if step_number:
            step_number = int(step_number)
            advance_step(obj["id"], step_number, notes)
            print(f"ActionAdvanceStep: {obj['id']} step {step_number} → done ({notes})")

            # Check if all steps are done → auto-complete objective
            updated = get_active_objective(sender_id)
            if updated:
                all_done = all(
                    s["status"] in ("done", "skipped")
                    for s in updated.get("steps", [])
                )
                if all_done:
                    complete_objective(updated["id"])
                    print(f"ActionAdvanceStep: objective {updated['id']} auto-completed (all steps done)")

        plan_text = render_plan(sender_id)
        return [
            SlotSet("agent_plan", plan_text),
            SlotSet("advance_step_number", None),
            SlotSet("advance_step_notes", None),
        ]


class ActionCheckPlan(Action):
    """Refresh the agent_plan slot with the current plan state.

    Can be called at any point to re-inject the plan into the LLM's context.
    Useful at the start of each turn or when the agent needs to re-orient.
    """

    def name(self) -> Text:
        return "action_check_plan"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        sender_id = tracker.sender_id or "default"
        progress = get_progress_summary(sender_id)

        plan_text = progress.get("summary", "")
        print(f"ActionCheckPlan: has_plan={progress['has_plan']}, "
              f"progress={progress.get('done', 0)}/{progress.get('total', 0)}")

        events: List[Dict[Text, Any]] = [SlotSet("agent_plan", plan_text)]

        if progress["has_plan"]:
            events.append(SlotSet("agent_objective_id", progress["objective_id"]))

        return events


class ActionCompletePlan(Action):
    """Explicitly mark the current objective as completed.

    Called at the end of a flow to close out the plan.
    """

    def name(self) -> Text:
        return "action_complete_plan"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        sender_id = tracker.sender_id or "default"
        obj = get_active_objective(sender_id)

        if not obj:
            print("ActionCompletePlan: no active plan to complete")
            return [SlotSet("agent_plan", ""), SlotSet("agent_objective_id", None)]

        complete_objective(obj["id"])
        print(f"ActionCompletePlan: {obj['id']} → completed")

        return [
            SlotSet("agent_plan", ""),
            SlotSet("agent_objective_id", None),
        ]

