const express = require('express');
const { createServer } = require('http');
const { Server } = require('socket.io');
const { spawn } = require('child_process');
const path = require('path');

const app = express();
const httpServer = createServer(app);
const io = new Server(httpServer);

const STARTER_DIR = path.join(__dirname, '..');
const VENV_PYTHON = path.join(STARTER_DIR, '.venv', 'bin', 'python');

app.use(express.static(path.join(__dirname, 'public')));

// Commands to run
const services = [
  { id: 'mcp', name: 'MCP Server', command: 'make', args: ['run-mcp'] },
  { id: 'actions', name: 'Action Server', command: 'make', args: ['run-actions'] },
  { id: 'rasa', name: 'Rasa Agentic', command: 'make', args: ['run-rasa-agentic'] },
  { id: 'heartbeat', name: 'Heartbeat', command: 'make', args: ['run-heartbeat'] }
];

const childProcesses = {};

// Keep a rolling buffer of the last N log lines per service so late-joining
// browsers instantly see recent output instead of blank panes.
const MAX_LOG_LINES = 200;
const logBuffers = {};
services.forEach(s => { logBuffers[s.id] = []; });

function pushLog(serviceId, entry) {
  const buf = logBuffers[serviceId];
  if (!buf) return;
  buf.push(entry);
  if (buf.length > MAX_LOG_LINES) buf.shift();
}

function startService(serviceId) {
  const service = services.find(s => s.id === serviceId);
  if (!service) return;

  if (childProcesses[serviceId]) {
    console.log(`[${service.name}] already running.`);
    return;
  }

  // Clear the log buffer when restarting so we don't mix old + new output
  logBuffers[serviceId] = [];

  // Force Python to not buffer stdout/stderr so logs appear immediately
  const env = Object.assign({}, process.env, { PYTHONUNBUFFERED: '1' });

  const child = spawn(service.command, service.args, {
    cwd: STARTER_DIR,
    env: env
  });

  childProcesses[serviceId] = child;

  child.stdout.on('data', (data) => {
    const text = data.toString();
    console.log(`[${service.name}] ${text.trimEnd()}`);
    const entry = { id: service.id, type: 'stdout', data: text };
    pushLog(service.id, entry);
    io.emit('log', entry);
  });

  child.stderr.on('data', (data) => {
    const text = data.toString();
    // Rasa / MCP / Sanic log everything to stderr; treat it as normal output
    console.log(`[${service.name}] ${text.trimEnd()}`);
    const entry = { id: service.id, type: 'stderr', data: text };
    pushLog(service.id, entry);
    io.emit('log', entry);
  });

  child.on('close', (code) => {
    console.log(`[${service.name}] exited with code ${code}`);
    const entry = { id: service.id, type: 'system', data: `\n--- Process exited with code ${code} ---\n` };
    pushLog(service.id, entry);
    io.emit('log', entry);
    childProcesses[serviceId] = null;
    io.emit('status', { id: service.id, running: false });
  });

  io.emit('status', { id: service.id, running: true });
}

function stopService(serviceId) {
  const child = childProcesses[serviceId];
  if (child) {
    console.log(`Killing service ${serviceId}...`);
    child.kill('SIGINT');
  }
}

io.on('connection', (socket) => {
  console.log('Client connected to dashboard');
  socket.emit('init', services.map(s => s.id));

  // Replay buffered logs so the new client sees recent history
  services.forEach(s => {
    socket.emit('status', { id: s.id, running: !!childProcesses[s.id] });
    logBuffers[s.id].forEach(entry => socket.emit('log', entry));
  });

  // Immediately send current DB state
  pollDatabase(socket);

  socket.on('restart', (serviceId) => {
    stopService(serviceId);
    setTimeout(() => {
      startService(serviceId);
    }, 1500);
  });

  socket.on('kill', (serviceId) => {
    stopService(serviceId);
  });
});

console.log('Starting background services...');

services.forEach(service => {
  startService(service.id);
});

// ── Database Poller ──────────────────────────────────────────────────────────
// Reads tickets + runbooks from the SQLite DB and pushes to clients.
// Uses the project's venv Python so sqlite3 is always available.

let lastDbJson = '';  // deduplicate: only emit when data actually changes

function pollDatabase(targetSocket) {
  const script = `
import sqlite3, json, os, sys
db = os.path.join('.data', 'work_items.db')
tickets_file = os.path.join('.data', 'tickets.json')
result = {"tickets": [], "plans": [], "json_tickets": []}

# SQLite work_items + objectives
if os.path.exists(db):
    try:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        result["tickets"] = [dict(r) for r in conn.execute("SELECT id, kind, summary, priority, status FROM work_items ORDER BY created_at DESC LIMIT 10").fetchall()]
        result["plans"]   = [dict(r) for r in conn.execute("SELECT id, title, status FROM agent_objectives ORDER BY created_at DESC LIMIT 10").fetchall()]
        conn.close()
    except Exception as e:
        result["db_error"] = str(e)

# JSON tickets file
if os.path.exists(tickets_file):
    try:
        with open(tickets_file) as f:
            data = json.load(f)
        for tid, t in list(data.items())[-5:]:
            result["json_tickets"].append({"id": tid, "summary": t.get("summary",""), "status": t.get("status",""), "priority": t.get("priority","")})
    except Exception:
        pass

print(json.dumps(result))
`;

  const child = spawn(VENV_PYTHON, ['-c', script], { cwd: STARTER_DIR });

  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (d) => stdout += d.toString());
  child.stderr.on('data', (d) => stderr += d.toString());
  child.on('close', () => {
    if (stderr) console.error('[DB Poller ERR]', stderr.trimEnd());
    try {
      const parsed = JSON.parse(stdout);
      const json = JSON.stringify(parsed);
      // If a specific socket was given (initial connection), always send.
      // Otherwise only broadcast when data changed.
      if (targetSocket) {
        targetSocket.emit('db-state', parsed);
      } else if (json !== lastDbJson) {
        lastDbJson = json;
        io.emit('db-state', parsed);
      }
    } catch (e) {
      console.error('[DB Poller] Failed to parse:', stdout.substring(0, 200));
    }
  });
}

setInterval(() => pollDatabase(null), 2000);

// ── Cleanup ──────────────────────────────────────────────────────────────────
process.on('SIGINT', () => {
  console.log('Dashboard stopping. Killing child processes...');
  Object.values(childProcesses).forEach(child => {
    if (child) child.kill('SIGINT');
  });
  process.exit(0);
});

const PORT = 3000;
httpServer.listen(PORT, () => {
  console.log(`\n======================================================`);
  console.log(`🚀 Dashboard running at http://localhost:${PORT}`);
  console.log(`======================================================\n`);
});
