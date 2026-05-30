# Rasa Coworker Hardening Progress

This document tracks changes made to ensure deterministic data handling, input validation, and conversational predictability.

## 1. Deterministic Data Handling
* **Sequential Ticket IDs**: Refactored `new_ticket_id` in `starter/actions/tickets.py` to identify the highest existing standard ticket ID (e.g., `TCK-1002`) and increment it sequentially, replacing random ID generation.
* **Fault-Tolerant Normalization**: Upgraded `normalise_ticket_id` in `tickets.py` to strip prefix noise and format any numeric or partial inputs into standard `TCK-####` format.

## 2. Hardened Action Logic & Validation
* **Inputs Validation Guard**: Added validation checks for all required fields (`issue_summary`, `issue_category`, `issue_priority`, `contact_email`) in `ActionCreateTicket` in `starter/actions/actions.py`, returning a boolean `inputs_valid` slot.
* **Guaranteed Lookup Slot State**: Updated `ActionLookupTicket` to always return and set all relevant slots (`ticket_found`, `lookup_ticket_id`, `ticket_status`, `ticket_summary`), avoiding unassigned state on errors or not-found results.

## 3. Grounded Flows and Domain
* **Conditional Branching**: Updated `log_support_ticket` in `starter/data/flows/support_triage.yml` to evaluate `slots.inputs_valid`, routing to `utter_ticket_created` or `utter_inputs_invalid` accordingly.
* **Domain Slot Declarations**: Registered the `inputs_valid` slot and defined `utter_inputs_invalid` in `starter/domain/support_triage.yml`.
* **Flow Trigger Boundaries**: Sharpened the triggering description of `check_ticket_status` in `starter/data/flows/ticket_status.yml` to prevent false-positive switching during conversations.

## 4. Restriction of Generative Behavior
* **NLG Rephrasing Disabled**: Commented out the NLG rephraser endpoint configuration in `starter/endpoints.yml` to ensure exact template-grounded responses.
* **Standardized Dialog Fallbacks**: Defined explicit templates for `utter_chitchat` and `utter_cannot_handle` in `starter/domain/shared.yml`.

## 5. Command Syntax V1→V2 Fix (Root Cause)
* **Root Cause**: `CompactLLMCommandGenerator` uses V2 command syntax (`start flow`, `set slot`) but the custom prompt template was teaching the LLM V1 syntax (`StartFlow()`, `SetSlot()`). The V2 regex parser rejected all LLM output → `CannotHandleCommand` on every turn.
* **Fix**: Rewrote `custom_command_prompt.jinja2` to use V2 action syntax throughout, matching what the parser expects.
* **Config**: Added `prompt_template: custom_command_prompt.jinja2` in `config.yml` under `CompactLLMCommandGenerator`.
* **Domain**: Restored `categorical` types for `issue_category` and `issue_priority` — exposes `allowed_values` in the prompt for tighter LLM extraction.

## 6. Test Suite
* **log_support_ticket.yml**: Restored original assertion grouping (category + priority from single turn). Stub sets `inputs_valid: true`.
* **lookup_ticket_found.yml**: New test — verifies `check_ticket_status` flow with a found ticket (uses `utter_name` assertions).
* **lookup_ticket_not_found.yml**: New test — verifies `check_ticket_status` flow with a missing ticket.
* **Result**: 3/3 tests pass, 100% accuracy across all assertion types (`flow_started`, `action_executed`, `slot_was_set`, `bot_uttered`).

## 7. Step 2 — Persistent State (Long-Lived Conversations & World State)

### 7a. Persistent Tracker Store (Conversation Context)
* **File**: `endpoints.yml` — added `tracker_store` block using SQLite (`.data/rasa_tracker.db`).
* **Effect**: Conversation history, slots, and events survive Rasa server restarts. Users can resume conversations across sessions.
* **Upgrade path**: Swap `dialect: "sqlite"` for `"postgresql"` + credentials for production.

### 7b. Rich Persistent Work-Item Store
* **File**: `actions/work_items.py` (NEW) — SQLite-backed (`.data/work_items.db`) with full incident-grade schema:
  - `id`, `kind` (ticket/incident), `summary`, `description`, `category`, `priority`, `severity`
  - `status` (open/in_progress/resolved/closed), `owner`, `reporter_email`, `board_column`
  - `last_summary` (for future LLM-generated recaps), `created_at`, `updated_at`
  - **Timeline events** table: audit trail of every change (status_change, comment, reassign, escalate).
* **Thread-safe**: Uses thread-local SQLite connections + WAL mode for concurrent action-server workers.
* **Legacy migration**: `migrate_legacy_tickets()` auto-imports `.data/tickets.json` entries on first run (idempotent).

### 7c. Backward-Compatible Shim
* **File**: `actions/tickets.py` — rewritten as thin wrapper over `work_items`. All existing function signatures (`load_tickets`, `save_tickets`, `new_ticket_id`, `normalise_ticket_id`, `utc_now`) preserved.

### 7d. Enhanced Actions
* **File**: `actions/actions.py` — all actions now read/write the SQLite store:
  - `ActionCreateTicket`: creates via `work_items.create_item()`
  - `ActionLookupTicket`: reads via `work_items.get_item()`, now returns `ticket_priority` + `ticket_owner` slots
  - `ActionListTickets` (NEW): lists recent tickets with optional status filter
  - `ActionUpdateTicketStatus` (NEW): changes ticket status with fuzzy matching

### 7e. New Flows & Domain
* **Flows**: `data/flows/list_tickets.yml`, `data/flows/update_ticket.yml`
* **Domain**: `domain/list_tickets.yml`, `domain/update_ticket.yml`, enriched `domain/ticket_status.yml`
* All flows read/write the persistent store — no dependence on in-memory tracker state for work-item data.
## 8. Step 3 — Internal Agent Scratchpad (Cognitive State)
* **Store (`scratchpad.py`)**: Added SQLite tracker for internal agent task plans (objectives and steps).
* **Actions**: Added plan-tracking actions (`ActionInitPlan`, `ActionAdvanceStep`, `ActionCheckPlan`, `ActionCompletePlan`).
* **Integration**: Injected `agent_plan` slot via `domain/scratchpad.yml` to give the LLM cognitive state, and wired core flows to autonomously advance plan steps.
