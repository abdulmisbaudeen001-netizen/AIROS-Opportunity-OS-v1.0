/**
 * AIROS Opportunity OS — Mission Control
 * Handles mission execution, real-time SSE log streaming, and history.
 */

import api from './api.js';
import { toast } from './app.js';

let _missionRunning = false;
let _eventSource = null;

const COMMANDS = [
  { cmd: '/mission',  label: '/mission',    desc: 'Full session: search + apply + email' },
  { cmd: '/search',   label: '/search',     desc: 'Search for opportunities only' },
  { cmd: '/apply',    label: '/apply',      desc: 'Submit queued applications' },
  { cmd: '/email',    label: '/email',      desc: 'Check career email inbox' },
  { cmd: '/status',   label: '/status',     desc: 'View recent application status' },
  { cmd: '/profile',  label: '/profile',    desc: 'Refresh and view profile' },
];

export async function renderMission(container) {
  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">
        <h2>Mission Control</h2>
        <p>Run commands and monitor execution in real time.</p>
      </div>
    </div>

    <!-- Status bar -->
    <div class="mission-status-bar" id="mission-status-bar">
      <div id="mission-status-icon" style="font-size:1rem;">◉</div>
      <span id="mission-status-text" class="mission-idle">No active mission. Send a command to begin.</span>
      <span id="mission-timer" style="margin-left:auto;font-family:var(--font-mono);font-size:0.75rem;color:var(--text-3)"></span>
    </div>

    <div class="mission-grid">
      <!-- Left: Quick commands + custom -->
      <div>
        <div class="card mb-lg">
          <div class="card-header">
            <span class="card-title">Quick Commands</span>
          </div>
          <div class="mission-commands" id="cmd-grid"></div>
          <div class="divider"></div>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Custom command or natural language</label>
            <input type="text" id="custom-cmd" placeholder="Find AI research grants in Germany..." />
          </div>
          <button class="btn btn-primary btn-full" id="run-cmd-btn" style="margin-top:0.5rem">
            ⚡ Run Command
          </button>
        </div>

        <!-- Last mission summary -->
        <div class="card" id="last-mission-card">
          <div class="card-header">
            <span class="card-title">Last Mission</span>
          </div>
          <div id="last-mission-content">
            <div class="skeleton" style="height:20px;margin-bottom:8px"></div>
            <div class="skeleton" style="height:20px;width:60%"></div>
          </div>
        </div>
      </div>

      <!-- Right: Live log -->
      <div class="card" style="display:flex;flex-direction:column;height:100%">
        <div class="card-header">
          <span class="card-title">Execution Log</span>
          <button class="btn btn-ghost btn-sm" id="clear-log-btn">Clear</button>
        </div>
        <div class="mission-log" id="mission-log">
          <div class="log-line">
            <span class="log-time">--:--:--</span>
            <span class="log-module">system</span>
            <span class="log-msg">Waiting for command...</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Mission history -->
    <div class="card mt-lg">
      <div class="card-header">
        <span class="card-title">Mission History</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mission ID</th>
              <th>Command</th>
              <th>Status</th>
              <th>Started</th>
              <th>Duration</th>
              <th>Applied</th>
              <th>Errors</th>
            </tr>
          </thead>
          <tbody id="mission-history-body">
            <tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text-3)">Loading...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  // Build quick command buttons
  const grid = container.querySelector('#cmd-grid');
  COMMANDS.forEach(({ cmd, label, desc }) => {
    const btn = document.createElement('button');
    btn.className = 'cmd-btn';
    btn.title = desc;
    btn.textContent = label;
    btn.addEventListener('click', () => {
      container.querySelector('#custom-cmd').value = cmd;
    });
    grid.appendChild(btn);
  });

  // Run button
  container.querySelector('#run-cmd-btn').addEventListener('click', () => {
    const cmd = container.querySelector('#custom-cmd').value.trim();
    if (!cmd) return;
    runCommand(cmd, container);
  });

  // Custom input — run on Enter
  container.querySelector('#custom-cmd').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const cmd = e.target.value.trim();
      if (cmd) runCommand(cmd, container);
    }
  });

  // Clear log
  container.querySelector('#clear-log-btn').addEventListener('click', () => {
    container.querySelector('#mission-log').innerHTML = '';
  });

  // Load data
  await loadLastMission(container);
  await loadMissionHistory(container);
}

async function runCommand(command, container) {
  if (_missionRunning) {
    toast('A mission is already running. Please wait.', 'warn');
    return;
  }

  _missionRunning = true;
  const btn = container.querySelector('#run-cmd-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Running...';

  setStatus(container, 'running', `Running: ${command}`);
  appendLog(container, 'system', `Starting: ${command}`, 'success');

  // Start timer
  const startTime = Date.now();
  const timerEl = container.querySelector('#mission-timer');
  const timer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const m = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const s = (elapsed % 60).toString().padStart(2, '0');
    timerEl.textContent = `${m}:${s}`;
  }, 1000);

  try {
    await api.mission.run(command);

    // Connect SSE for real-time logs
    streamLogs(container, () => {
      clearInterval(timer);
      _missionRunning = false;
      btn.disabled = false;
      btn.innerHTML = '⚡ Run Command';
      setStatus(container, 'done', 'Mission complete.');
      appendLog(container, 'system', 'Mission finished.', 'success');
      loadLastMission(container);
      loadMissionHistory(container);
    });

  } catch (err) {
    clearInterval(timer);
    _missionRunning = false;
    btn.disabled = false;
    btn.innerHTML = '⚡ Run Command';
    setStatus(container, 'error', `Error: ${err.message}`);
    appendLog(container, 'system', `Error: ${err.message}`, 'error');
    toast(err.message, 'error');
  }
}

function streamLogs(container, onComplete) {
  if (_eventSource) { _eventSource.close(); }

  _eventSource = api.mission.stream();

  _eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.done) {
        _eventSource.close();
        _eventSource = null;
        onComplete();
        return;
      }
      const msgType = data.message?.includes('Error') ? 'error' :
                      data.message?.includes('complete') ? 'success' : '';
      appendLog(container, data.module || 'system', data.message || '', msgType);
    } catch (_) {}
  };

  _eventSource.onerror = () => {
    _eventSource?.close();
    _eventSource = null;
    onComplete();
  };

  // Fallback timeout — close after 3 minutes
  setTimeout(() => {
    if (_eventSource) {
      _eventSource.close();
      _eventSource = null;
      onComplete();
    }
  }, 180000);
}

function appendLog(container, module, message, type = '') {
  const log = container.querySelector('#mission-log');
  if (!log) return;

  const now = new Date();
  const time = now.toTimeString().slice(0, 8);

  const line = document.createElement('div');
  line.className = 'log-line';
  line.innerHTML = `
    <span class="log-time">${time}</span>
    <span class="log-module">${module.slice(0, 12)}</span>
    <span class="log-msg ${type}">${escHtml(message)}</span>
  `;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

function setStatus(container, state, text) {
  const bar = container.querySelector('#mission-status-text');
  const icon = container.querySelector('#mission-status-icon');
  if (!bar) return;

  bar.className = `mission-${state}`;
  bar.textContent = text;

  const icons = { idle: '◉', running: '◉', done: '◉', error: '◉' };
  const colors = { idle: 'var(--text-3)', running: 'var(--primary)', done: 'var(--green)', error: 'var(--red)' };
  icon.textContent = icons[state] || '◉';
  icon.style.color = colors[state] || 'var(--text-3)';
}

async function loadLastMission(container) {
  const el = container.querySelector('#last-mission-content');
  if (!el) return;
  try {
    const data = await api.mission.recent();
    const missions = data.missions || [];
    if (!missions.length) {
      el.innerHTML = '<p style="font-size:0.82rem">No missions yet. Run /mission to start.</p>';
      return;
    }
    const m = missions[0];
    const summary = m.summary || {};
    const started = m.started_at ? new Date(m.started_at).toLocaleString() : '—';
    el.innerHTML = `
      <div class="flex items-center justify-between mb-md">
        <span class="mono" style="color:var(--text-3)">${m.id}</span>
        <span class="badge ${m.status === 'completed' ? 'badge-green' : 'badge-red'}">${m.status}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem">
        ${statLine('Applications', summary.applications_submitted || 0)}
        ${statLine('Opportunities', (summary.jobs_found||0) + (summary.scholarships_found||0) + (summary.grants_found||0))}
        ${statLine('Errors', summary.errors || 0)}
        ${statLine('Started', started)}
      </div>
    `;
  } catch (err) {
    el.innerHTML = `<p style="color:var(--red);font-size:0.8rem">${err.message}</p>`;
  }
}

async function loadMissionHistory(container) {
  const tbody = container.querySelector('#mission-history-body');
  if (!tbody) return;
  try {
    const data = await api.mission.recent();
    const missions = data.missions || [];
    if (!missions.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text-3)">No missions recorded yet.</td></tr>';
      return;
    }
    tbody.innerHTML = missions.map(m => {
      const summary = m.summary || {};
      const started = m.started_at ? new Date(m.started_at).toLocaleString() : '—';
      const ended = m.ended_at ? new Date(m.ended_at) : null;
      const started_d = m.started_at ? new Date(m.started_at) : null;
      let duration = '—';
      if (ended && started_d) {
        const secs = Math.floor((ended - started_d) / 1000);
        duration = `${Math.floor(secs/60)}m ${secs%60}s`;
      }
      const statusBadge = m.status === 'completed' ? 'badge-green' :
                          m.status === 'error'     ? 'badge-red'   : 'badge-gray';
      return `<tr>
        <td class="td-mono" style="font-size:0.7rem">${m.id}</td>
        <td class="td-mono">${escHtml(m.command || '—')}</td>
        <td><span class="badge ${statusBadge}">${m.status}</span></td>
        <td class="td-dim" style="font-size:0.78rem">${started}</td>
        <td class="td-mono">${duration}</td>
        <td class="td-mono">${summary.applications_submitted || 0}</td>
        <td class="td-mono" style="color:${(summary.errors||0) > 0 ? 'var(--red)' : 'var(--text-2)'}">${summary.errors || 0}</td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--red);padding:1rem">${err.message}</td></tr>`;
  }
}

function statLine(label, value) {
  return `<div>
    <div class="label">${label}</div>
    <div class="mono" style="color:var(--text)">${value}</div>
  </div>`;
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
