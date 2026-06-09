# 🤖 Wally: The Always-On AI Coworker

**Wally** is a persistent, stateful, proactive AI agent that handles real workflows. Built during the Rasa Boston Tech Week 2026 hackathon, Wally moves beyond the simple 5-minute ephemeral chat window to become a long-term digital coworker.

## ✨ Key Features

- **Persistent State**: Backed by a live SQLite database and persistent chat history. Wally remembers your context across sessions. The tickets and runbooks you see are real, persistent state.
- **Proactive Detection (Heartbeat)**: Wally doesn't just wait for you to ask a question. A background heartbeat monitor detects system anomalies (e.g., checkout returning 500 errors) and triggers an incident triage runbook automatically before anyone even asks.
- **Agentic Triage & Human-in-the-Loop**: When triage is needed, Wally securely searches past incident histories using MCP (Model Context Protocol) tools to formulate grounded remediation plans. At critical moments, Wally pauses for explicit human approval.
- **Deterministic CALM Flows**: For strict business logic like reporting bugs, Wally supports rigid, deterministic flows without expensive LLM calls.
- **Full Control Dashboard**: A dedicated web interface with real-time Kanban step tracking, a live chat UI, and multi-pane terminal logs for monitoring Wally's internal processes.

## 🚀 Quickstart

1. **Install Dependencies**
   Ensure you have Python 3.10+ and Node.js installed.
   ```bash
   cd starter
   cp .env.example .env      # Add your Rasa, Nebius, and Speechmatics keys
   make install
   make train-agentic
   ```

2. **Seed the Database**
   Populate the database with initial mock data (crucial for history and MCP search features):
   ```bash
   # Make sure you are in the starter directory
   python scripts/seed_incidents.py
   ```

3. **Start the System**
   The dashboard acts as the orchestrator and will spin up the MCP server, Action server, Rasa Agentic, and the Heartbeat monitor.
   ```bash
   cd dashboard
   npm install
   npm start
   ```

4. **Open the Dashboard**
   Navigate to [http://localhost:3000](http://localhost:3000) in your browser. Wait for all terminal panes to show green indicators. 

## 🎬 Demo Workflow

Try out Wally with this flow:
1. **Persistent State Check**: Ask *"What is the status of ticket INC-1002?"* to verify state persistence.
2. **Proactive Runbooks**: Wait for the Heartbeat monitor to trigger an anomaly. Wally will automatically start a new triage runbook (`OBJ-XXXX`).
3. **Agentic Checklist**: Help Wally advance through the checklist by answering its prompts (e.g., Service: `payments`, Symptom: `checkout 500 errors`, Severity: `P1`).
4. **Approval Gate**: Review the MCP-generated remediation plan and approve it to see Wally execute the final steps.
5. **Standard Flows**: Say *"I need to report a bug"* to see the strict deterministic fallback in action.

---

*Built for the Always-On AI Coworker Hackathon (Boston Tech Week 2026).*