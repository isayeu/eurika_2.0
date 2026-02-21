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
    const dec = (op.team_decision || 'pending').toLowerCase();
    const ap = dec === 'approve' ? ' active' : '';
    const rej = dec === 'reject' ? ' active' : '';
    html += '<div class="op-row" data-idx="' + i + '">';
    html += '<div class="op-desc">' + escapeHtml(file) + (kind ? ' <span class="muted">' + escapeHtml(kind) + '</span>' : '') + '</div>';
    html += '<div class="op-actions">';
    html += '<button class="approve' + (dec === 'approve' ? ap : '') + '" data-action="approve">Approve</button>';
    html += '<button class="reject' + (dec === 'reject' ? rej : '') + '" data-action="reject">Reject</button>';
    html += '</div></div>';
  });
  html += '<div style="margin-top: 1rem;"><button id="approve-save-btn" style="padding: 0.5rem 1rem; background: var(--accent); border: none; color: var(--bg); cursor: pointer; font-family: inherit;">Save decisions</button></div>';
  html += '</div>';
  content.innerHTML = html;
  content.querySelectorAll('.op-actions button').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const row = e.target.closest('.op-row');
      const idx = parseInt(row.dataset.idx, 10);
      const action = e.target.dataset.action;
      approveOps[idx] = { ...approveOps[idx], team_decision: action, approved_by: action === 'approve' ? 'ui' : null };
      renderApprove(approveOps);
    });
  });
  document.getElementById('approve-save-btn')?.addEventListener('click', saveApprove);
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
load();
