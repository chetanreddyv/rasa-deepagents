Here is the final, chronological Demo Day script. It is ordered exactly how you should present it on stage, from the behind-the-scenes setup to the final mic-drop closing line.

***

# 🎮 Demo Day Script: The Always-On AI Coworker

## ⚙️ T-2 Minutes (Pre-Demo Setup)

Do this off-screen before the judges walk over. You want the dashboard already open and populated when they arrive.

1. **Kill old processes for a clean slate:**
   ```bash
   for port in 3000 5005 5055 8000; do lsof -ti :$port | xargs kill -9 2>/dev/null; done
   ```
2. **Seed the Database (Crucial for history features):**
   ```bash
   # Make sure you are in the starter directory
   ./.venv/bin/python scripts/seed_incidents.py
   ```
3. **Start the System:**
   ```bash
   cd dashboard
   npm start
   ```
4. **Open the Dashboard:** Open `http://localhost:3000` in your browser. Wait for all 4 terminal panes to show green indicators.

***

## 🎬 Phase 1: The Intro & Persistent State

*Start your demo here. The dashboard should be full of seeded data.*

**What it proves:** This isn't an ephemeral chat window. It's a persistent system.
**Action:**
1. Point to the **Active Incidents** column on the left.
2. **Say:** *"Most AI assistants forget everything when you refresh the page. Wally is backed by a persistent database. It's been running since before this hackathon started. These tickets are real, persistent state."*
3. **Type in Chat:** 
   `you › What is the status of ticket INC-1002?`
4. **Expected:** Coworker replies instantly with the status. 
5. **Say:** *"It remembers our state exactly."*

***

## 🚨 Phase 2: Proactive Detection & Live Checklists

*The Heartbeat monitor is set to fire every 30 seconds. By the time you finish Phase 1, it should have triggered.*

**What it proves:** Push-based, proactive AI & stateful execution.
**Action:**
1. **Wait** until the `Heartbeat Monitor` pane logs a `SYSTEM_ALERT`.
2. **Point to Kanban:** A new Active Runbook (`OBJ-XXXX: Triage and manage incident`) automatically pops into the middle column.
3. **Say:** *"I didn't start this. While we were talking, Wally detected an anomaly, woke itself up, and started a triage runbook before anyone in this room knew there was a problem."*
4. **Expand the Runbook Card:** Point out that the first 2 checklist steps (`Identify incident`, `Locate ticket`) are already marked `✓`.
5. **Say:** *"It's managing a stateful checklist. Let's give it the context it needs to advance."*
6. **Type in Chat (Answer its prompts):**
   - `Coworker › Which service or system is affected?`
   - `you › payments`
   - `Coworker › What is the symptom?`
   - `you › checkout is returning 500 errors`
   - `Coworker › Severity?`
   - `you › P1`
7. **Point to Kanban:** As you hit enter on each answer, show the judges how the checkboxes automatically tick off live in the UI!

***

## 🧠 Phase 3: Agentic Triage & Human-in-the-Loop

**What it proves:** MCP tool calling, grounded LLM reasoning, and safety.
**Action:**
1. Right after you answer `P1`, the Agent takes over.
2. **Point to MCP Terminal Pane:** Show the HTTP requests hitting the FastMCP server.
3. **Say:** *"It's not guessing or hallucinating. It's using MCP tools to securely search our past incident history to find out how we solved this last time."*
4. **Point to Chat:** The agent returns a grounded remediation plan based on its search. 
5. **The Approval Gate:** The agent pauses and asks: `Review the runbook above. Confirm to proceed (yes) or abort (no).`
6. **Say:** *"90% autonomous, but it stops for a human decision at the critical moment. That's the design."*
7. **Type:** `you › Yes`
8. **Point to Kanban:** The final steps execute, and the Runbook card slides gracefully to the **Completed** column on the right.

***

## 📋 Phase 4: Standard CALM Flow (Contrast)

**What it proves:** Fallback to strict deterministic flows when LLMs aren't needed.
**Action:**
1. **Say:** *"Not everything needs an expensive LLM. We still support strict, deterministic business logic."*
2. **Type quickly:**
   - `you › I need to report a bug`
   - `you › Login page crashes on mobile`
   - `you › bug`
   - `you › high`
   - `you › dev@example.com`
3. **Expected:** A new ticket appears instantly in the left **Active Incidents** column. Show how fast and rigid it is.

***

## 🎤 The Mic-Drop Closing

*(Look directly at the judges. Do not look at the screen.)*

*"Most AI waits for you to ask it a question. Wally was already 3 steps into solving a production outage before anyone in this room realized the payments service went down. That is not a chatbot. That is a coworker."*