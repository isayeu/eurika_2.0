/* Eurika UI — vanilla JS, no build (ROADMAP 3.5.2, 3.5.3). */

const API = (path, params = {}) => {
  const qs = new URLSearchParams(params).toString();
  const url = '/api' + path + (qs ? '?' + qs : '');
  return fetch(url).then(r => {
    if (!r.ok) return r.json().catch(() => ({ error: r.statusText || 'Request failed', status: r.status }));
    return r.json();
  });
};

const APIPost = (path, body) => {
  return fetch('/api' + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(r => r.json());
};

const DEFAULT_EXEC_TIMEOUT_SEC = 180;

function getExecTimeoutPayload() {
  const unlimitedCb = document.getElementById('exec-timeout-unlimited-cb');
  if (unlimitedCb && unlimitedCb.checked) return null;
  const timeoutInput = document.getElementById('exec-timeout-input');
  const raw = timeoutInput ? parseInt(String(timeoutInput.value || '').trim(), 10) : NaN;
  if (Number.isFinite(raw) && raw >= 1 && raw <= 3600) return raw;
  return DEFAULT_EXEC_TIMEOUT_SEC;
}

function syncExecTimeoutUi() {
  const unlimitedCb = document.getElementById('exec-timeout-unlimited-cb');
  const timeoutInput = document.getElementById('exec-timeout-input');
  if (!timeoutInput) return;
  timeoutInput.disabled = !!(unlimitedCb && unlimitedCb.checked);
}

function bar(value, maxVal, cls) {
  const pct = maxVal > 0 ? Math.round((value / maxVal) * 100) : 0;
  return '<div class="bar-wrap"><div class="bar-track"><div class="bar-fill ' + (cls || '') + '" style="width:' + pct + '%"></div></div><span>' + value + '/' + maxVal + '</span></div>';
}

function trendBadge(v) {
  if (!v || v === 'insufficient_data') return '<span class="trend-badge trend-stable">—</span>';
  if (v === 'increasing') return '<span class="trend-badge trend-up">↑</span>';
  if (v === 'decreasing') return '<span class="trend-badge trend-down">↓</span>';
  return '<span class="trend-badge trend-stable">→</span>';
}

function renderDashboard(summary, history, opsMetrics) {
  const el = document.getElementById('dashboard-content');
  if (summary.error) {
    el.innerHTML = '<span class="error">' + escapeHtml(summary.error) + '</span>';
    return;
  }
  const sys = summary.system || {};
  const central = (summary.central_modules || []).slice(0, 5);
  const risks = (summary.risks || []).slice(0, 5);
  const maturity = summary.maturity || '—';
  const trends = history.trends || {};
  const points = history.points || [];
  const latestPoint = points.length ? points[points.length - 1] : null;
  const riskScore = latestPoint && latestPoint.risk_score != null ? latestPoint.risk_score : null;

  let html = '';
  if (riskScore != null) {
    const barCls = riskScore <= 30 ? 'risk-low' : riskScore <= 60 ? 'risk-med' : 'risk-high';
    html += '<div class="card"><h2>Risk score</h2>' + bar(riskScore, 100, barCls) + '<div class="metric muted">Higher = more structural risk. From latest history point.</div></div>';
  }
  html += '<div class="card"><h2>System metrics</h2><div class="dashboard-grid">';
  html += '<div class="dashboard-stat"><div class="val">' + (sys.modules || '—') + '</div><div class="lbl">Modules</div></div>';
  html += '<div class="dashboard-stat"><div class="val">' + (sys.dependencies || '—') + '</div><div class="lbl">Dependencies</div></div>';
  html += '<div class="dashboard-stat"><div class="val">' + (sys.cycles || '—') + '</div><div class="lbl">Cycles</div></div>';
  html += '<div class="dashboard-stat"><div class="val"><span class="maturity ' + String(maturity).replace(/[\s-]/g, '-') + '">' + escapeHtml(maturity) + '</span></div><div class="lbl">Maturity</div></div>';
  html += '</div></div>';

  if (opsMetrics && !opsMetrics.error && opsMetrics.runs_count) {
    const ar = (opsMetrics.apply_rate * 100).toFixed(1);
    const rr = (opsMetrics.rollback_rate * 100).toFixed(1);
    const med = opsMetrics.median_verify_time_ms;
    const medStr = med != null ? med + ' ms' : '—';
    html += '<div class="card"><h2>Operational metrics</h2><div class="dashboard-grid">';
    html += '<div class="dashboard-stat"><div class="val">' + ar + '%</div><div class="lbl">Apply rate (last ' + opsMetrics.runs_count + ' runs)</div></div>';
    html += '<div class="dashboard-stat"><div class="val">' + rr + '%</div><div class="lbl">Rollback rate</div></div>';
    html += '<div class="dashboard-stat"><div class="val">' + medStr + '</div><div class="lbl">Median verify time</div></div>';
    html += '</div></div>';
  }
  if (Object.keys(trends).length) {
    html += '<div class="card"><h2>Trends</h2>';
    html += '<div class="metric">Complexity ' + trendBadge(trends.complexity) + ' ' + escapeHtml(trends.complexity || '') + '</div>';
    html += '<div class="metric">Smells ' + trendBadge(trends.smells) + ' ' + escapeHtml(trends.smells || '') + '</div>';
    html += '<div class="metric">Centralization ' + trendBadge(trends.centralization) + ' ' + escapeHtml(trends.centralization || '') + '</div>';
    html += '</div>';
  }

  if (central.length) {
    html += '<div class="card"><h2>Central modules (top 5)</h2><ul>';
    central.forEach(c => { html += '<li>' + escapeHtml(c.name) + ' <span class="muted">fi:' + c.fan_in + ' fo:' + c.fan_out + '</span></li>'; });
    html += '</ul></div>';
  }

  if (risks.length) {
    html += '<div class="card"><h2>Top risks</h2><ul>';
    risks.forEach(r => { html += '<li class="risk-item">' + escapeHtml(r) + '</li>'; });
    html += '</ul></div>';
  }

  if (!html) html = '<div class="muted">No data. Run <code>eurika scan .</code> and <code>eurika cycle .</code></div>';
  el.innerHTML = html;
}

function renderSummary(data) {
  const el = document.getElementById('summary-content');
  if (data.error) {
    el.innerHTML = '<span class="error">' + escapeHtml(data.error) + '</span>';
    return;
  }
  const sys = data.system || {};
  const central = data.central_modules || [];
  const risks = data.risks || [];
  const maturity = data.maturity || '—';

  let html = '<div class="card"><h2>System</h2>';
  html += '<div class="metric"><strong>Modules:</strong> ' + sys.modules + '</div>';
  html += '<div class="metric"><strong>Dependencies:</strong> ' + sys.dependencies + '</div>';
  html += '<div class="metric"><strong>Cycles:</strong> ' + sys.cycles + '</div>';
  html += '<div class="metric"><strong>Maturity:</strong> <span class="maturity ' + maturity.replace(/[\s-]/g, '-') + '">' + escapeHtml(maturity) + '</span></div>';
  html += '</div>';

  if (central.length) {
    html += '<div class="card"><h2>Central modules</h2><ul>';
    central.forEach(c => {
      html += '<li>' + escapeHtml(c.name) + ' — fan-in ' + c.fan_in + ', fan-out ' + c.fan_out + '</li>';
    });
    html += '</ul></div>';
  }

  if (risks.length) {
    html += '<div class="card"><h2>Risks</h2><ul>';
    risks.forEach(r => {
      html += '<li class="risk-item">' + escapeHtml(r) + '</li>';
    });
    html += '</ul></div>';
  }

  el.innerHTML = html;
}

function renderHistory(data) {
  const el = document.getElementById('history-content');
  const trends = data.trends || {};
  const regressions = data.regressions || [];
  const report = data.evolution_report || '';
  const points = data.points || [];

  let html = '';
  if (Object.keys(trends).length) {
    html += '<div class="card"><h2>Trends</h2>';
    html += '<div class="metric"><strong>Complexity:</strong> ' + escapeHtml(trends.complexity || '—') + '</div>';
    html += '<div class="metric"><strong>Smells:</strong> ' + escapeHtml(trends.smells || '—') + '</div>';
    html += '<div class="metric"><strong>Centralization:</strong> ' + escapeHtml(trends.centralization || '—') + '</div>';
    html += '</div>';
  }
  if (regressions.length) {
    html += '<div class="card"><h2>Regressions</h2><ul>';
    regressions.forEach(r => {
      html += '<li class="risk-item">' + escapeHtml(r) + '</li>';
    });
    html += '</ul></div>';
  }
  if (points.length) {
    html += '<div class="card"><h2>Recent points</h2><ul>';
    points.slice(-5).reverse().forEach(p => {
      const ts = p.timestamp ? new Date(p.timestamp * 1000).toISOString().slice(0, 19) : '—';
      html += '<li>' + escapeHtml(ts) + ' — modules ' + p.modules + ', deps ' + p.dependencies + ', smells ' + (p.total_smells || 0) + (p.risk_score != null ? ', risk ' + p.risk_score : '') + '</li>';
    });
    html += '</ul></div>';
  }
  if (report) {
    html += '<div class="card"><h2>Evolution report</h2><pre class="evolution">' + escapeHtml(report) + '</pre></div>';
  }
  if (!html) html = '<div class="muted">No history yet. Run <code>eurika scan .</code> and <code>eurika cycle .</code> to build history.</div>';
  el.innerHTML = html;
}

function escapeHtml(s) {
  if (typeof s !== 'string') return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

let graphNetwork = null;
let graphLoaded = false;

function initTabs() {
  document.querySelectorAll('.tabs button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const tab = btn.dataset.tab;
      document.getElementById('panel-' + tab).classList.add('active');
      if (tab === 'graph' && !graphLoaded) loadGraph();
      if (tab === 'approve') loadApprove();
    });
  });
}

function initTerminal() {
  const input = document.getElementById('terminal-input');
  const runBtn = document.getElementById('terminal-run-btn');
  const output = document.getElementById('terminal-output');
  const timeoutInput = document.getElementById('exec-timeout-input');
  const timeoutUnlimitedCb = document.getElementById('exec-timeout-unlimited-cb');
  if (!input || !runBtn || !output) return;
  if (timeoutInput) {
    timeoutInput.addEventListener('change', () => {
      const n = parseInt(String(timeoutInput.value || '').trim(), 10);
      if (!Number.isFinite(n) || n < 1) timeoutInput.value = '1';
      else if (n > 3600) timeoutInput.value = '3600';
    });
  }
  if (timeoutUnlimitedCb) timeoutUnlimitedCb.addEventListener('change', syncExecTimeoutUi);
  syncExecTimeoutUi();
  runBtn.addEventListener('click', async () => {
    const cmd = input.value.trim() || 'eurika scan .';
    const timeout = getExecTimeoutPayload();
    output.textContent = 'Running…';
    runBtn.disabled = true;
    try {
      const res = await APIPost('/exec', { command: cmd, timeout: timeout });
      runBtn.disabled = false;
      if (res.error) {
        output.textContent = (res.stderr || res.error || '') + (res.stdout || '');
      } else {
        const out = (res.stdout || '') + (res.stderr ? '\n' + res.stderr : '');
        output.textContent = out || '(no output)';
      }
    } catch (e) {
      runBtn.disabled = false;
      output.textContent = 'Request failed: ' + (e.message || 'unknown');
    }
  });
}

function initAskArchitect() {
  const btn = document.getElementById('ask-btn');
  const result = document.getElementById('ask-result');
  if (!btn || !result) return;
  btn.addEventListener('click', async () => {
    result.textContent = 'Loading…';
    btn.disabled = true;
    try {
      const res = await APIPost('/ask_architect', {});
      btn.disabled = false;
      if (res.error) {
        result.textContent = 'Error: ' + res.error;
      } else {
        result.textContent = res.text || '(empty)';
      }
    } catch (e) {
      btn.disabled = false;
      result.textContent = 'Request failed: ' + (e.message || 'unknown');
    }
  });
}

let chatHistory = [];

function appendChatMessage(role, content) {
  const el = document.getElementById('chat-messages');
  if (!el) return;
  const div = document.createElement('div');
  div.className = 'chat-msg chat-msg-' + role;
  div.style.marginBottom = '0.75rem';
  div.style.padding = '0.35rem 0';
  div.style.borderBottom = role === 'user' ? '1px solid var(--border)' : 'none';
  const label = document.createElement('strong');
  label.textContent = role === 'user' ? 'You: ' : 'Eurika: ';
  label.style.color = role === 'user' ? 'var(--accent)' : 'var(--ok)';
  div.appendChild(label);
  div.appendChild(document.createTextNode(content));
  if (el.textContent === 'No messages yet.') el.textContent = '';
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

function initChat() {
  const input = document.getElementById('chat-input');
  const btn = document.getElementById('chat-send-btn');
  const messagesEl = document.getElementById('chat-messages');
  if (!input || !btn || !messagesEl) return;
  const send = async () => {
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    appendChatMessage('user', msg);
    const historyToSend = chatHistory.slice(-10);
    chatHistory.push({ role: 'user', content: msg });
    const placeholder = document.createElement('div');
    placeholder.className = 'chat-msg chat-msg-assistant';
    placeholder.style.color = 'var(--muted)';
    placeholder.textContent = 'Thinking…';
    messagesEl.appendChild(placeholder);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    btn.disabled = true;
    try {
      const res = await APIPost('/chat', { message: msg, history: historyToSend });
      placeholder.remove();
      const text = res.text || '';
      const err = res.error || '';
      if (err) {
        appendChatMessage('assistant', '[Error] ' + err);
        chatHistory.push({ role: 'assistant', content: '[Error] ' + err });
      } else {
        appendChatMessage('assistant', text || '(empty)');
        chatHistory.push({ role: 'assistant', content: text });
      }
    } catch (e) {
      placeholder.remove();
      appendChatMessage('assistant', '[Request failed] ' + (e.message || 'unknown'));
      chatHistory.push({ role: 'assistant', content: '[Request failed] ' + (e.message || 'unknown') });
    }
    btn.disabled = false;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };
  btn.addEventListener('click', send);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
}

function runCommand(cmd, btn, btnText) {
  const output = document.getElementById('terminal-output');
  if (!btn || !output) return;
  const timeout = getExecTimeoutPayload();
  const timeoutLabel = timeout == null ? 'unlimited' : (timeout + 's');
  btn.disabled = true;
  const orig = btn.textContent;
  if (btnText) btn.textContent = 'Running…';
  document.querySelector('.tabs button[data-tab="terminal"]')?.click();
  const startedAt = Date.now();
  const frames = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'];
  let frame = 0;
  output.textContent = 'Running ' + cmd + ' …\n';
  const timer = setInterval(() => {
    const sec = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    output.textContent =
      'Running ' + cmd + ' …\n' +
      'timeout: ' + timeoutLabel + '\n' +
      frames[frame % frames.length] + ' elapsed: ' + sec + 's';
    frame += 1;
  }, 250);
  return APIPost('/exec', { command: cmd, timeout: timeout })
    .then(res => {
      clearInterval(timer);
      btn.disabled = false;
      if (btnText) btn.textContent = orig;
      const out = (res.stdout || '') + (res.stderr ? '\n' + res.stderr : '');
      const sec = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
      output.textContent = '[done in ' + sec + 's]\n' + (out || '(no output)');
      if (res.error && res.stdout) output.textContent = (res.stdout || '') + (res.stderr ? '\n' + res.stderr : '');
      load();
    })
    .catch(e => {
      clearInterval(timer);
      btn.disabled = false;
      if (btnText) btn.textContent = orig;
      const sec = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
      output.textContent = '[failed in ' + sec + 's]\nRequest failed: ' + (e.message || 'unknown');
    });
}

function initRunCycle() {
  const scanBtn = document.getElementById('run-scan-btn');
  const doctorBtn = document.getElementById('run-doctor-btn');
  const fixBtn = document.getElementById('run-fix-btn');
  const reportBtn = document.getElementById('run-report-btn');
  const cycleBtn = document.getElementById('run-cycle-btn');
  const dryRunCb = document.getElementById('fix-dry-run-cb');
  const approvalCb = document.getElementById('fix-approval-cb');
  const doctorLlmCb = document.getElementById('doctor-llm-cb');

  if (scanBtn) scanBtn.addEventListener('click', () => runCommand('eurika scan .', scanBtn, true));
  if (doctorBtn) doctorBtn.addEventListener('click', () => {
    const useLlm = doctorLlmCb && doctorLlmCb.checked;
    const cmd = useLlm ? 'eurika doctor .' : 'eurika doctor . --no-llm';
    runCommand(cmd, doctorBtn, true);
  });
  if (fixBtn) fixBtn.addEventListener('click', () => {
    const dry = dryRunCb && dryRunCb.checked;
    const team = approvalCb && approvalCb.checked;
    let cmd = 'eurika fix .';
    if (team) cmd += ' --team-mode';
    else if (dry) cmd += ' --dry-run';
    runCommand(cmd, fixBtn, true);
    if (team) setTimeout(() => { document.querySelector('.tabs button[data-tab="approve"]')?.click(); loadApprove(); }, 2000);
  });
  if (reportBtn) reportBtn.addEventListener('click', () => runCommand('eurika report-snapshot .', reportBtn, true));
  if (cycleBtn) cycleBtn.addEventListener('click', () => runCommand('eurika cycle . --dry-run', cycleBtn, true));
}

async function loadGraph() {
  const container = document.getElementById('graph-container');
  const hint = document.getElementById('graph-hint');
  if (!container || !hint) return;
  try {
    const data = await API('/graph');
    if (data.error) {
      let msg = escapeHtml(data.error);
      if (msg === 'not found' || data.status === 404) {
        msg = 'API /api/graph not found. Restart <code>eurika serve</code> to load the latest version.';
      }
      hint.innerHTML = '<span class="error">' + msg + '</span>';
      return;
    }
    graphLoaded = true;
    hint.innerHTML = 'Module dependency graph. Drag to pan, scroll to zoom. Double-click node → Explain.';
    const nodes = new vis.DataSet((data.nodes || []).map(n => ({
      id: n.id,
      label: n.label,
      title: n.title,
      font: { color: '#e2e6ed', size: 11 },
      color: { background: '#2a3140', border: '#5b9bd5' },
    })));
    const edges = new vis.DataSet((data.edges || []).map(e => ({ from: e.from, to: e.to })));
    const netData = { nodes, edges };
    const options = {
      physics: { enabled: true, solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -80, centralGravity: 0.01, springLength: 150, springConstant: 0.08 } },
      nodes: { shape: 'dot', size: 8 },
      edges: { arrows: 'to', color: { color: '#5b9bd5', highlight: '#e2e6ed' } },
      interaction: { hover: true, tooltipDelay: 200 },
    };
    graphNetwork = new vis.Network(container, netData, options);
    graphNetwork.on('doubleClick', function(params) {
      if (params.nodes.length && typeof vis !== 'undefined') {
        const id = params.nodes[0];
        const node = nodes.get(id);
        if (node && node.id) {
          const explainIn = document.getElementById('explain-module');
          if (explainIn) { explainIn.value = node.id; }
          document.querySelector('.tabs button[data-tab="explain"]')?.click();
        }
      }
    });
  } catch (e) {
    hint.innerHTML = '<span class="error">Request failed: ' + escapeHtml(e.message) + '</span>';
  }
}

function renderDiff(data) {
  const el = document.getElementById('diff-content');
  if (data.error) {
    el.innerHTML = '<span class="error">' + escapeHtml(data.error) + '</span>';
    return;
  }
  const structures = data.structures || {};
  const maturity = data.maturity || {};
  const actions = data.recommended_actions || [];
  const bottlenecks = data.bottleneck_modules || [];
  const centrality = data.centrality_shifts || [];

  let html = '';
  if (maturity.old || maturity.new) {
    html += '<div class="card"><h2>Maturity</h2><div class="metric">' + escapeHtml(maturity.old || '—') + ' → ' + escapeHtml(maturity.new || '—') + '</div></div>';
  }
  if (structures.modules_added && structures.modules_added.length) {
    html += '<div class="card"><h2>Modules added</h2><ul>' + structures.modules_added.map(m => '<li class="ok">' + escapeHtml(m) + '</li>').join('') + '</ul></div>';
  }
  if (structures.modules_removed && structures.modules_removed.length) {
    html += '<div class="card"><h2>Modules removed</h2><ul>' + structures.modules_removed.map(m => '<li>' + escapeHtml(m) + '</li>').join('') + '</ul></div>';
  }
  if (centrality.length) {
    html += '<div class="card"><h2>Centrality shifts</h2><ul>';
    centrality.slice(0, 10).forEach(c => {
      const name = c.module || c.name || '?';
      const fi = c.fan_in;
      const fo = c.fan_out;
      const fiStr = Array.isArray(fi) ? fi[0] + '→' + fi[1] : '';
      const foStr = Array.isArray(fo) ? fo[0] + '→' + fo[1] : '';
      html += '<li>' + escapeHtml(name) + (fiStr ? ' fan-in ' + fiStr : '') + (foStr ? ' fan-out ' + foStr : '') + '</li>';
    });
    html += '</ul></div>';
  }
  if (bottlenecks.length) {
    html += '<div class="card"><h2>Bottleneck modules</h2><ul>';
    bottlenecks.forEach(b => { html += '<li class="risk-item">' + escapeHtml(b) + '</li>'; });
    html += '</ul></div>';
  }
  if (actions.length) {
    html += '<div class="card"><h2>Recommended actions</h2><ul>';
    actions.forEach(a => { html += '<li>' + escapeHtml(typeof a === 'string' ? a : (a.action || a.text || JSON.stringify(a))) + '</li>'; });
    html += '</ul></div>';
  }
  if (!html) html = '<div class="muted">No significant changes, or structures/smells data empty.</div>';
  el.innerHTML = html;
}

let approveOps = [];
let approveData = null;

async function loadApprove() {
  const content = document.getElementById('approve-content');
  const hint = document.getElementById('approve-hint');
  if (!content || !hint) return;
  content.innerHTML = '<span class="loading">Loading…</span>';
  try {
    const data = await API('/pending_plan');
    if (data.error) {
      content.innerHTML = '<span class="error">' + escapeHtml(data.error) + '</span><br><span class="muted">' + escapeHtml(data.hint || '') + '</span>';
      hint.innerHTML = 'Run <code>eurika fix . --team-mode</code> first. Then approve/reject and Save.';
      return;
    }
    approveData = data;
    approveOps = (data.operations || []).map(o => ({ ...o, team_decision: o.team_decision || 'pending', approved_by: o.approved_by || null }));
    renderApprove(approveOps);
    const approved = approveOps.filter(o => (o.team_decision || '').toLowerCase() === 'approve').length;
    hint.innerHTML = approved + ' approved. Click Save to persist. Then run <code>eurika fix . --apply-approved</code>.';
  } catch (e) {
    content.innerHTML = '<span class="error">Request failed: ' + escapeHtml(e.message) + '</span>';
  }
}

/**
 * Parse unified diff into synchronized rows: { leftRows, rightRows }.
 * Each row: { lineNum, text, isDel/isAdd }. Both arrays same length for alignment.
 */
function parseUnifiedDiffToAlignedRows(oldLines, diffText) {
  const diff = (diffText || '').split('\n');
  const chunkRe = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))?/;
  const ix = (n) => Math.max(0, n - 1);
  const leftRows = [];
  const rightRows = [];
  let i = 0;
  while (i < diff.length && !chunkRe.test(diff[i])) i++;
  if (i >= diff.length) return null;
  let oldNum = 1;
  let newNum = 1;
  while (i < diff.length) {
    const m = diff[i].match(chunkRe);
    if (m) {
      const chunkOldStart = parseInt(m[1], 10);
      const chunkNewStart = parseInt(m[3], 10);
      for (; oldNum < chunkOldStart && oldNum <= oldLines.length; oldNum++, newNum++) {
        const txt = oldLines[ix(oldNum)] || '';
        leftRows.push({ lineNum: oldNum, text: txt, isDel: false });
        rightRows.push({ lineNum: newNum, text: txt, isAdd: false });
      }
      oldNum = chunkOldStart;
      newNum = chunkNewStart;
      i++;
      while (i < diff.length && !chunkRe.test(diff[i])) {
        const line = diff[i];
        const first = line.charAt(0);
        const content = line.slice(1);
        if (first === ' ') {
          leftRows.push({ lineNum: oldNum, text: content, isDel: false });
          rightRows.push({ lineNum: newNum, text: content, isAdd: false });
          oldNum++;
          newNum++;
        } else if (first === '-') {
          leftRows.push({ lineNum: oldNum, text: content, isDel: true });
          rightRows.push({ lineNum: null, text: '', isAdd: false });
          oldNum++;
        } else if (first === '+') {
          leftRows.push({ lineNum: null, text: '', isDel: false });
          rightRows.push({ lineNum: newNum, text: content, isAdd: true });
          newNum++;
        }
        i++;
      }
      continue;
    }
    i++;
  }
  for (; oldNum <= oldLines.length; oldNum++, newNum++) {
    const txt = oldLines[ix(oldNum)] || '';
    leftRows.push({ lineNum: oldNum, text: txt, isDel: false });
    rightRows.push({ lineNum: newNum, text: txt, isAdd: false });
  }
  const hasEdits = leftRows.some(r => r.isDel) || rightRows.some(r => r.isAdd);
  return hasEdits ? { leftRows, rightRows } : null;
}

function renderDiffPreview(leftRows, rightRows, leftLabel, rightLabel) {
  const fmt = (rows, isLeft) => rows.map((r) => {
    const num = (r.lineNum != null && r.lineNum > 0) ? String(r.lineNum) : '\u00A0';
    const cls = isLeft ? (r.isDel ? ' class="line-del"' : '') : (r.isAdd ? ' class="line-add"' : '');
    return '<span class="diff-line-num">' + escapeHtml(num) + '</span><span' + cls + '>' + escapeHtml(r.text || ' ') + '</span>';
  }).join('\n');
  const leftHtml = fmt(leftRows, true);
  const rightHtml = fmt(rightRows, false);
  return '<div class="diff-split" style="margin-top: 0.5rem;">' +
    '<div class="diff-panel left"><strong class="muted">' + escapeHtml(leftLabel) + '</strong><br>' + leftHtml + '</div>' +
    '<div class="diff-panel right"><strong class="muted">' + escapeHtml(rightLabel) + '</strong><br>' + rightHtml + '</div>' +
    '</div>';
}

async function showOpDiff(targetFile, diff) {
  const current = await API('/file', { path: targetFile });
  if (current.error) {
    return '(file not found: ' + escapeHtml(current.error) + ')';
  }
  const leftLines = (current.content || '').split('\n');
  const diffText = diff || '';
  const parsed = parseUnifiedDiffToAlignedRows(leftLines, diffText);
  if (parsed && parsed.leftRows.length > 0) {
    return renderDiffPreview(
      parsed.leftRows,
      parsed.rightRows,
      targetFile + ' (current)',
      targetFile + ' (new)'
    );
  }
  const isTodoStyle = /^#\s*TODO:|^#\s*Suggested|^#\s*Refactor/i.test(diffText.trim());
  if (isTodoStyle) {
    const leftRows = leftLines.map((t, i) => ({ lineNum: i + 1, text: t, isDel: false }));
    const rightRows = leftRows.map(r => ({ lineNum: r.lineNum, text: r.text, isAdd: false }));
    return '<div class="diff-split" style="margin-top: 0.5rem;">' +
      '<div class="diff-panel left"><strong class="muted">' + escapeHtml(targetFile) + ' (current)</strong><br>' +
      leftRows.map(r => '<span class="diff-line-num">' + r.lineNum + '</span><span>' + escapeHtml(r.text) + '</span>').join('\n') + '</div>' +
      '<div class="diff-panel right" style="background: var(--surface);"><strong class="muted">Preview</strong><br>' +
      '<div class="muted" style="white-space: normal; margin-bottom: 0.75rem;">No patch preview. This operation uses a textual plan (split_module, refactor suggestion).</div>' +
      '<pre style="white-space: pre-wrap; font-size: 11px; margin: 0; color: var(--muted);">' + escapeHtml(diffText.trim()) + '</pre></div></div>';
  }
  const leftRows = leftLines.map((t, i) => ({ lineNum: i + 1, text: t, isDel: false }));
  const diffLines = diffText.split('\n');
  let rightRows = diffLines.map((t, i) => ({
    lineNum: (t.startsWith('+') || t.startsWith('-') || t.startsWith(' ')) ? i + 1 : null,
    text: (t.startsWith('+') || t.startsWith('-') || t.startsWith(' ')) ? t.slice(1) : t,
    isAdd: t.startsWith('+'),
  }));
  const maxLen = Math.max(leftRows.length, rightRows.length);
  while (leftRows.length < maxLen) leftRows.push({ lineNum: null, text: '', isDel: false });
  while (rightRows.length < maxLen) rightRows.push({ lineNum: null, text: '', isAdd: false });
  return renderDiffPreview(
    leftRows,
    rightRows,
    targetFile + ' (current)',
    targetFile + ' (diff)'
  );
}

function renderApprove(ops) {
  const content = document.getElementById('approve-content');
  if (!content) return;
  if (!ops.length) {
    content.innerHTML = '<div class="muted">No operations.</div>';
    return;
  }
  let html = '<div class="card"><h2>Operations</h2>';
  ops.forEach((op, i) => {
    const file = op.target_file || op.file || '?';
    const kind = op.refactor_kind || op.kind || '';
    const diff = op.diff || '';
    const dec = (op.team_decision || 'pending').toLowerCase();
    const ap = dec === 'approve' ? ' active' : '';
    const rej = dec === 'reject' ? ' active' : '';
    html += '<div class="op-row" data-idx="' + i + '">';
    html += '<div class="op-desc">' + escapeHtml(file) + (kind ? ' <span class="muted">' + escapeHtml(kind) + '</span>' : '') + '</div>';
    html += '<div class="op-actions">';
    html += '<button class="view-diff-btn" data-idx="' + i + '" style="padding: 0.25rem 0.5rem; font-size: 11px; cursor: pointer; background: var(--surface); border: 1px solid var(--border); color: var(--accent); font-family: inherit;">View</button>';
    html += '<button class="approve' + (dec === 'approve' ? ap : '') + '" data-action="approve">Approve</button>';
    html += '<button class="reject' + (dec === 'reject' ? rej : '') + '" data-action="reject">Reject</button>';
    html += '</div></div>';
    html += '<div id="op-diff-' + i + '" class="op-diff-placeholder" style="display: none;"></div>';
  });
  html += '<div style="margin-top: 1rem; display: flex; gap: 0.5rem; align-items: center;">' +
    '<button id="approve-save-btn" style="padding: 0.5rem 1rem; background: var(--accent); border: none; color: var(--bg); cursor: pointer; font-family: inherit;">Save decisions</button>' +
    '<button id="approve-apply-btn" class="run-cmd-btn" style="padding: 0.5rem 1rem;">Apply approved</button></div>';
  html += '</div>';
  content.innerHTML = html;
  content.querySelectorAll('.op-actions button').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      if (e.target.classList.contains('view-diff-btn')) {
        const idx = parseInt(e.target.dataset.idx, 10);
        const op = approveOps[idx] || {};
        const file = op.target_file || op.file || '';
        const diff = op.diff || '';
        const placeholder = document.getElementById('op-diff-' + idx);
        if (!placeholder) return;
        if (placeholder.style.display === 'block') {
          placeholder.style.display = 'none';
          placeholder.innerHTML = '';
          return;
        }
        placeholder.innerHTML = '<span class="loading">Loading…</span>';
        placeholder.style.display = 'block';
        try {
          const html = await showOpDiff(file, diff);
          placeholder.innerHTML = html;
          const split = placeholder.querySelector('.diff-split');
          if (split) {
            const panels = split.querySelectorAll('.diff-panel');
            if (panels.length === 2) {
              const syncScroll = (from, to) => { to.scrollTop = from.scrollTop; to.scrollLeft = from.scrollLeft; };
              panels[0].addEventListener('scroll', () => syncScroll(panels[0], panels[1]));
              panels[1].addEventListener('scroll', () => syncScroll(panels[1], panels[0]));
            }
          }
        } catch (err) {
          placeholder.innerHTML = '<span class="error">' + escapeHtml(err.message || 'failed') + '</span>';
        }
        return;
      }
      const row = e.target.closest('.op-row');
      const idx = parseInt(row.dataset.idx, 10);
      const action = e.target.dataset.action;
      if (!action) return;
      approveOps[idx] = { ...approveOps[idx], team_decision: action, approved_by: action === 'approve' ? 'ui' : null };
      renderApprove(approveOps);
    });
  });
  document.getElementById('approve-save-btn')?.addEventListener('click', saveApprove);
  const applyBtn = document.getElementById('approve-apply-btn');
  if (applyBtn) applyBtn.addEventListener('click', () => {
    runCommand('eurika fix . --apply-approved', applyBtn, true);
    setTimeout(loadApprove, 3000);
  });
}

async function saveApprove() {
  const content = document.getElementById('approve-content');
  const hint = document.getElementById('approve-hint');
  if (!content || !hint) return;
  const btn = document.getElementById('approve-save-btn');
  if (btn) btn.disabled = true;
  try {
    const res = await APIPost('/approve', { operations: approveOps });
    if (res.error) {
      hint.innerHTML = '<span class="error">' + escapeHtml(res.error) + '</span>';
    } else {
      const n = res.approved || 0;
      hint.innerHTML = '<span class="ok">Saved. ' + n + ' approved.</span> Run <code>eurika fix . --apply-approved</code>.';
    }
  } catch (e) {
    hint.innerHTML = '<span class="error">Save failed: ' + escapeHtml(e.message) + '</span>';
  }
  if (btn) btn.disabled = false;
}

function initDiff() {
  const oldIn = document.getElementById('diff-old');
  const newIn = document.getElementById('diff-new');
  const result = document.getElementById('diff-content');
  document.getElementById('diff-btn').addEventListener('click', async () => {
    const oldPath = oldIn.value.trim() || 'self_map.json';
    const newPath = newIn.value.trim() || 'self_map.json';
    result.innerHTML = '<span class="loading">Loading…</span>';
    try {
      const data = await API('/diff', { old: oldPath, new: newPath });
      renderDiff(data);
    } catch (e) {
      result.innerHTML = '<span class="error">Request failed: ' + escapeHtml(e.message) + '</span>';
    }
  });
}

function initExplain() {
  const input = document.getElementById('explain-module');
  const result = document.getElementById('explain-result');
  document.getElementById('explain-btn').addEventListener('click', async () => {
    const mod = input.value.trim();
    if (!mod) {
      result.textContent = 'Enter a module path.';
      return;
    }
    result.textContent = 'Loading…';
    try {
      const data = await API('/explain', { module: mod, window: 5 });
      if (data.error) {
        result.textContent = 'Error: ' + data.error;
      } else {
        result.textContent = data.text || '(empty)';
      }
    } catch (e) {
      result.textContent = 'Request failed: ' + e.message;
    }
  });
}

async function load() {
  try {
    const [summary, history, opsMetrics] = await Promise.all([
      API('/summary'),
      API('/history', { window: 5 }),
      API('/operational_metrics', { window: 10 }).catch(() => ({ error: true })),
    ]);
    renderDashboard(summary, history, opsMetrics);
    renderSummary(summary);
    renderHistory(history);
  } catch (e) {
    const err = '<span class="error">Failed to load: ' + escapeHtml(e.message) + '</span>';
    document.getElementById('dashboard-content').innerHTML = err;
    document.getElementById('summary-content').innerHTML = err;
    document.getElementById('history-content').innerHTML = err;
  }
}

initTabs();
initDiff();
initExplain();
initTerminal();
initAskArchitect();
initChat();
initRunCycle();
load();
