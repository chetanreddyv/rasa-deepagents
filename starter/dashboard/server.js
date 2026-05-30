const express = require('express');
const { createServer } = require('http');
const { Server } = require('socket.io');
const { spawn } = require('child_process');
const path = require('path');

const app = express();
const httpServer = createServer(app);
const io = new Server(httpServer);

app.use(express.static(path.join(__dirname, 'public')));

// Commands to run
const services = [
  { id: 'mcp', name: 'MCP Server', command: 'make', args: ['run-mcp'] },
  { id: 'actions', name: 'Action Server', command: 'make', args: ['run-actions'] },
  { id: 'rasa', name: 'Rasa Agentic', command: 'make', args: ['run-rasa-agentic'] },
  { id: 'heartbeat', name: 'Heartbeat', command: 'make', args: ['run-heartbeat'] }
];

const childProcesses = {};

function startService(serviceId) {
  const service = services.find(s => s.id === serviceId);
  if (!service) return;

  if (childProcesses[serviceId]) {
    console.log(`[${service.name}] already running.`);
    return;
  }

  // Force Python to not buffer stdout/stderr so logs appear immediately
  const env = Object.assign({}, process.env, { PYTHONUNBUFFERED: '1' });

  const child = spawn(service.command, service.args, { 
    cwd: path.join(__dirname, '..'),
    env: env
  });
  
  childProcesses[serviceId] = child;

  child.stdout.on('data', (data) => {
    const text = data.toString();
    console.log(`[${service.name}] ${text.trim()}`);
    io.emit('log', { id: service.id, type: 'stdout', data: text });
  });

  child.stderr.on('data', (data) => {
    const text = data.toString();
    console.error(`[${service.name} ERR] ${text.trim()}`);
    io.emit('log', { id: service.id, type: 'stderr', data: text });
  });

  child.on('close', (code) => {
    console.log(`[${service.name}] exited with code ${code}`);
    io.emit('log', { id: service.id, type: 'system', data: `\n--- Process exited with code ${code} ---\n` });
    childProcesses[serviceId] = null;
    io.emit('status', { id: service.id, running: false });
  });

  io.emit('status', { id: service.id, running: true });
}

function stopService(serviceId) {
  const child = childProcesses[serviceId];
  if (child) {
    console.log(`Killing service ${serviceId}...`);
    child.kill('SIGINT'); // Try graceful kill first
  }
}

io.on('connection', (socket) => {
  console.log('Client connected to dashboard');
  socket.emit('init', services.map(s => s.id));
  
  // Send current status
  services.forEach(s => {
    socket.emit('status', { id: s.id, running: !!childProcesses[s.id] });
  });

  socket.on('restart', (serviceId) => {
    stopService(serviceId);
    setTimeout(() => {
      startService(serviceId);
    }, 1000); // give it a sec to unbind port
  });

  socket.on('kill', (serviceId) => {
    stopService(serviceId);
  });
});

console.log('Starting background services...');

services.forEach(service => {
  startService(service.id);
});

// Cleanup on exit
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
