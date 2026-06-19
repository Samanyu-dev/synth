/* ═══════════════════════════════════════════════════════
   SYNTH MVP — EXECUTION TRACER
   Full interactive trace visualizer
   ═══════════════════════════════════════════════════════ */

// ─── 1. CONSTANTS ──────────────────────────────────────
const COLORS = {
    input:      { bg: '#0c1929', border: '#3b82f6', font: '#93bbfc', glow: 'rgba(59,130,246,0.5)' },
    validation: { bg: '#1a1506', border: '#eab308', font: '#fde68a', glow: 'rgba(234,179,8,0.5)' },
    processing: { bg: '#110c24', border: '#818cf8', font: '#c7d2fe', glow: 'rgba(129,140,248,0.5)' },
    ai:         { bg: '#1c0a33', border: '#a855f7', font: '#d8b4fe', glow: 'rgba(168,85,247,0.5)' },
    output:     { bg: '#052e16', border: '#22c55e', font: '#86efac', glow: 'rgba(34,197,94,0.5)' },
    error:      { bg: '#1f0a0a', border: '#ef4444', font: '#fca5a5', glow: 'rgba(239,68,68,0.5)' },
    data:       { bg: '#0f1219', border: '#334155', font: '#94a3b8', glow: 'none' },
    dimmed:     { bg: '#0a0b10', border: '#1e2030', font: '#3a3f52', glow: 'none' }
};

const EXEC_STEPS_ANALYZE = [
    { id: 1, label: 'API Gateway\n━━━━━━━━━━\nPOST /analyze',                cat: 'input',      latency: 12,  desc: 'Incoming HTTP request received by FastAPI server.' },
    { id: 2, label: 'Rate Limiter\n━━━━━━━━━━\nSlowAPI 10/min',               cat: 'validation',  latency: 3,   desc: 'SlowAPI checks IP against rate limit constraints.' },
    { id: 3, label: 'Pydantic\n━━━━━━━━━━\nSchema + Sanitize',               cat: 'validation',  latency: 8,   desc: 'Strict Pydantic validation & regex injection defense.' },
    { id: 4, label: 'Data Ingestion\n━━━━━━━━━━\nCSV → Pandas → Models',      cat: 'processing',  latency: 45,  desc: 'Parses raw CSV files into strongly-typed Pydantic models.' },
    { id: 5, label: 'Heuristics\n━━━━━━━━━━\nTRIMP • Splits • Drift',        cat: 'processing',  latency: 22,  desc: 'Deterministic metric calculation: load, recovery proxy, HR drift.' },
    { id: 6, label: 'Machine Learning\n━━━━━━━━━━\nXGBoost Injury Model',     cat: 'processing',  latency: 15,  desc: 'Evaluates heuristics against historical data to predict injury probability.' },
    { id: 7, label: 'AI Synthesis\n━━━━━━━━━━\nGemini 2.5 Flash',             cat: 'ai',          latency: 320, desc: 'Structured prompt sent to Google AI for insight generation.' },
    { id: 8, label: 'Schema Enforcer\n━━━━━━━━━━\nJSON validate/fallback',    cat: 'validation',  latency: 5,   desc: 'Validates AI response or triggers Graceful Degradation fallback.' },
    { id: 9, label: '200 OK\n━━━━━━━━━━\nPayload ready',                      cat: 'output',      latency: 2,   desc: 'Final JSON response returned to the client.' }
];

const EXEC_STEPS_STRAVA = [
    { id: 1, label: 'API Gateway\n━━━━━━━━━━\nPOST /sync/strava',             cat: 'input',      latency: 10,  desc: 'Incoming sync request.' },
    { id: 2, label: 'OAuth2 Verification\n━━━━━━━━━━\nStrava Tokens',          cat: 'validation', latency: 15,  desc: 'Validates or refreshes the Strava Access Token.' },
    { id: 3, label: 'Strava API\n━━━━━━━━━━\nGET /activities',                 cat: 'data',       latency: 410, desc: 'Pulls the athletes real workout data from Strava.' },
    { id: 4, label: 'Pydantic Mapping\n━━━━━━━━━━\nStrava → ActivityRecord',   cat: 'processing', latency: 25,  desc: 'Normalizes Strava JSON payload into strict internal Pydantic schemas.' },
    { id: 5, label: 'Google Sheets Write\n━━━━━━━━━━\ngspread Sync',           cat: 'output',     latency: 850, desc: 'Connects via Service Account to write the new activities to the spreadsheet.' },
    { id: 6, label: '200 OK\n━━━━━━━━━━\nSynced Successfully',                 cat: 'output',      latency: 2,   desc: 'Returns the mapped activities and sync status.' }
];

const EXEC_STEPS_SHEETS = [
    { id: 1, label: 'API Gateway\n━━━━━━━━━━\nPOST /sync/sheets',             cat: 'input',      latency: 12,  desc: 'Incoming sync request.' },
    { id: 2, label: 'Service Account\n━━━━━━━━━━\nGoogle Auth',                cat: 'validation', latency: 45,  desc: 'Authenticates with Google Cloud via service account JSON.' },
    { id: 3, label: 'Google Sheets API\n━━━━━━━━━━\nRead Worksheets',          cat: 'data',       latency: 600, desc: 'Fetches all raw training and wellness tabs from the live spreadsheet.' },
    { id: 4, label: 'Heuristics Engine\n━━━━━━━━━━\nNormalization & Math',     cat: 'processing', latency: 35,  desc: 'Calculates acute load, heart rate drift, and recovery proxy scores.' },
    { id: 5, label: 'AI Synthesis\n━━━━━━━━━━\nClaude Tool-Calling',           cat: 'ai',         latency: 1200,desc: 'Sends normalized data to Claude 3.5 Sonnet to generate structured JSON insights.' },
    { id: 6, label: 'Google Sheets API\n━━━━━━━━━━\nWrite Insights Tab',       cat: 'output',     latency: 850, desc: 'Writes the AI-generated insights, risks, and recommendations back to the sheet.' },
    { id: 7, label: '200 OK\n━━━━━━━━━━\nTwo-Way Sync Complete',               cat: 'output',     latency: 2,   desc: 'Sync loop finished.' }
];

function getSteps(mode) {
    if (mode === 'sync_strava') return EXEC_STEPS_STRAVA;
    if (mode === 'sync_sheets') return EXEC_STEPS_SHEETS;
    return EXEC_STEPS_ANALYZE;
}

const ALERT_EXPLANATIONS = {
    'ACUTE_LOAD_SPIKE': 'Training load increased >30% compared to the previous period. This is a significant jump that raises injury risk.',
    'ACUTE_LOAD_DROP': 'Training load dropped >30% compared to baseline. Could indicate a taper, illness, or loss of motivation.',
    'NO_REST_7_DAYS': 'The athlete has trained 7+ consecutive days without a rest day. Recovery capacity is compromised.',
    'ELEVATED_HR_DRIFT': 'Heart rate is trending >5% above baseline for similar efforts. Early sign of accumulated fatigue.',
    'POOR_RECOVERY_PROXY': 'Recovery score is below 0.4/1.0. Combination of consecutive training days, HR drift, and load changes.',
    'HIGH_INDIVIDUAL_ABSENCE_RATE': 'An athlete has missed 3+ scheduled test sessions. May indicate injury, disengagement, or scheduling conflicts.',
    'TEAM_WIDE_FATIGUE_POSSIBLE': 'More than 20% of the team is showing declining performance trends. Suggests systemic overtraining.',
    'PERFORMANCE_DECLINE': 'Split times are trending slower across recent tests compared to earlier season benchmarks.',
    'CHRONIC_ABSENCE': 'Athlete has been absent from 3+ test sessions. Pattern suggests ongoing issue requiring attention.',
    'ERRATIC_PACING': 'Standard deviation of interval splits exceeds 5 seconds. Athlete struggles to maintain consistent pace.',
    'HIGH_PREDICTIVE_INJURY_RISK': 'XGBoost model predicts >70% chance of injury in the next 14 days based on compounding fatigue markers.',
    'RP3_WASH_OUT_DETECTED': 'Biomechanical force curve analysis detects a sharp power drop-off at the finish of the stroke (washing out). Indicates poor core connection or technique breakdown under fatigue.'
};

// ─── 2. DOM REFS ───────────────────────────────────────
const $ = (s) => document.getElementById(s);
const megaGraph       = $('megaGraph');
const modeSelect      = $('modeSelect');
const triathlonInputs = $('triathlonInputs');
const rowingInputs    = $('rowingInputs');
const stravaInputs    = $('stravaInputs');
const sheetsInputs    = $('sheetsInputs');
const executeBtn      = $('executeBtn');
const btnLoader       = $('btnLoader');
const metricsBar      = $('metricsBar');
const viewToggle      = $('viewToggle');
const timelineView    = $('timelineView');
const timelineList    = $('timelineList');
const inspector       = $('inspector');
const inspectorTitle  = $('inspectorTitle');
const inspectorStatus = $('inspectorStatus');
const inspectorBody   = $('inspectorBody');
const inspectorClose  = $('inspectorClose');
const minimapEl       = $('minimap');
const minimapCanvas   = $('minimapCanvas');
const cmdPalette      = $('cmdPalette');
const cmdInput        = $('cmdInput');
const cmdList         = $('cmdList');
const explainTooltip  = $('explainTooltip');
const explainBody     = $('explainBody');

// ─── 3. STATE ──────────────────────────────────────────
let network       = null;
let nodes         = new vis.DataSet([]);
let edges         = new vis.DataSet([]);
let idCounter     = 1;
let responseData  = null;
let traceTimeline = [];
let totalLatency  = 0;
let currentView   = 'graph';

// ─── 4. UTILS ──────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function nodeColor(cat, state = 'normal') {
    if (state === 'dimmed') return { background: COLORS.dimmed.bg, border: COLORS.dimmed.border };
    if (state === 'active') return { background: COLORS[cat].border, border: '#fff' };
    return { background: COLORS[cat].bg, border: COLORS[cat].border };
}

function nodeFont(cat, state = 'normal') {
    if (state === 'dimmed') return { color: COLORS.dimmed.font, face: 'JetBrains Mono', size: 13, multi: 'md' };
    if (state === 'active') return { color: '#fff', face: 'JetBrains Mono', size: 14, multi: 'md' };
    return { color: COLORS[cat].font, face: 'JetBrains Mono', size: 13, multi: 'md' };
}

function countWarnings(data) {
    let c = 0;
    function walk(obj) {
        if (!obj || typeof obj !== 'object') return;
        for (const [k, v] of Object.entries(obj)) {
            if (k === 'alerts' || k === 'risks' || k === 'active_alerts') {
                if (Array.isArray(v)) c += v.length;
            }
            if (typeof v === 'object') walk(v);
        }
    }
    walk(data);
    return c;
}

// ─── 5. MODE SELECT ───────────────────────────────────
modeSelect.addEventListener('change', (e) => {
    triathlonInputs.style.display = e.target.value === 'triathlon' ? 'flex' : 'none';
    rowingInputs.style.display    = e.target.value === 'rowing'    ? 'flex' : 'none';
    stravaInputs.style.display    = e.target.value === 'sync_strava' ? 'flex' : 'none';
    sheetsInputs.style.display    = e.target.value === 'sync_sheets' ? 'flex' : 'none';
});

// ─── 6. METRICS BAR ───────────────────────────────────
function updateMetrics(latency, warnings, nodeCount, degraded) {
    $('metricLatency').textContent = `${latency}ms`;
    $('metricTokens').textContent  = degraded ? '0' : '~2.1k';
    const wEl = $('metricWarnings');
    wEl.textContent = warnings;
    wEl.className = `metric-value ${warnings > 2 ? 'red' : warnings > 0 ? 'yellow' : 'green'}`;
    $('metricNodes').textContent = nodeCount;
    const sEl = $('metricStatus');
    sEl.textContent = degraded ? 'Degraded' : 'Healthy';
    sEl.className   = `metric-value ${degraded ? 'yellow' : 'green'}`;
    metricsBar.classList.remove('hidden');
}

// ─── 7. VIEW TOGGLE ───────────────────────────────────
document.querySelectorAll('.toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentView = btn.dataset.view;
        if (currentView === 'timeline') {
            timelineView.classList.remove('hidden');
            megaGraph.style.display = 'none';
        } else {
            timelineView.classList.add('hidden');
            megaGraph.style.display = 'block';
        }
    });
});

// ─── 8. TIMELINE ───────────────────────────────────────
function populateTimeline() {
    timelineList.innerHTML = '';
    traceTimeline.forEach(item => {
        const dotClass = { input: 'blue', validation: 'yellow', processing: 'purple', ai: 'purple', output: 'green' }[item.cat] || 'blue';
        const el = document.createElement('div');
        el.className = 'tl-item';
        el.innerHTML = `
            <div class="tl-dot ${dotClass}"></div>
            <div class="tl-content">
                <div class="tl-time">${item.time}</div>
                <div class="tl-name">${item.name}</div>
                <div class="tl-desc">${item.desc}</div>
            </div>
            <div class="tl-latency">${item.latency}ms</div>
        `;
        timelineList.appendChild(el);
    });
}

// ─── 9. INSPECTOR ──────────────────────────────────────
function openInspector(nodeId) {
    const node = nodes.get(nodeId);
    if (!node) return;

    inspectorTitle.textContent = node._title || node.label.split('\n')[0];
    inspectorStatus.style.background = COLORS[node._cat || 'data']?.border || '#334155';

    let html = '';

    if (node._execStep) {
        const step = node._execStep;
        html += `
            <div class="insp-section">
                <div class="insp-section-title">Details</div>
                <div style="font-size:0.85rem;color:var(--text-2);margin-top:4px;line-height:1.5;">${step.desc}</div>
            </div>
            <div class="insp-section">
                <div class="insp-section-title">Performance</div>
                <div class="insp-kv"><span class="insp-key">Latency</span><span class="insp-val">${step.latency}ms</span></div>
                <div class="insp-kv"><span class="insp-key">Category</span><span class="insp-val ${step.cat === 'ai' ? 'purple' : step.cat === 'output' ? 'green' : 'blue'}">${step.cat.toUpperCase()}</span></div>
            </div>`;
        if (step.cat === 'ai') {
            html += `
            <div class="insp-section">
                <div class="insp-section-title">AI Reasoning</div>
                <div class="insp-kv"><span class="insp-key">Model</span><span class="insp-val purple">Gemini 2.5 Flash</span></div>
                <div class="insp-kv"><span class="insp-key">Tokens (est)</span><span class="insp-val">~2,142</span></div>
                <div class="insp-kv"><span class="insp-key">Cost (est)</span><span class="insp-val">$0.003</span></div>
                <div class="insp-kv"><span class="insp-key">Response</span><span class="insp-val">application/json</span></div>
            </div>
            <div class="insp-section">
                <div class="insp-section-title">Inputs</div>
                <ul class="insp-list">
                    <li>Heuristic Summary (TriathlonWeeklySummary or RowingTeamSummary)</li>
                    <li>Computed alert flags from deterministic engine</li>
                </ul>
            </div>
            <div class="insp-section">
                <div class="insp-section-title">Outputs</div>
                <ul class="insp-list">
                    <li class="insight-item">insights[] — factual observations</li>
                    <li class="alert-item">risks[] — potential consequences</li>
                    <li class="rec-item">recommendations[] — actionable steps</li>
                </ul>
            </div>`;
        }
    } else if (node._dataKey) {
        html += `
            <div class="insp-section">
                <div class="insp-section-title">Data Field</div>
                <div class="insp-kv"><span class="insp-key">Key</span><span class="insp-val">${node._dataKey}</span></div>
                <div class="insp-kv"><span class="insp-key">Value</span><span class="insp-val">${typeof node._dataValue === 'object' ? '(Object)' : node._dataValue}</span></div>
            </div>`;
        if (node._isAlert && ALERT_EXPLANATIONS[node._dataValue]) {
            html += `
            <div class="insp-section">
                <div class="insp-section-title">💡 Explain This</div>
                <div style="font-size:0.85rem;color:var(--text-2);line-height:1.6;">
                    <strong style="color:var(--red);">⚠ ${node._dataValue}</strong><br><br>
                    ${ALERT_EXPLANATIONS[node._dataValue]}
                </div>
            </div>`;
        } else if (node._dataKey === 'load_summary' && typeof node._dataValue === 'object') {
            const sum = node._dataValue;
            html += `<div class="insp-section"><div class="insp-section-title">Form Chart (CTL vs ATL)</div><canvas id="formChartCanvas"></canvas></div>`;
            html += `<div class="insp-section"><div class="insp-section-title">Sport Balance</div><canvas id="radarChartCanvas"></canvas></div>`;
            setTimeout(() => {
                const formCtx = document.getElementById('formChartCanvas');
                if (formCtx && sum.form_chart_data && sum.form_chart_data.length > 0) {
                    new Chart(formCtx, {
                        type: 'line',
                        data: {
                            labels: sum.form_chart_data.map(d => d.date),
                            datasets: [
                                { label: 'Fitness (CTL)', data: sum.form_chart_data.map(d => d.ctl), borderColor: '#3b82f6', tension: 0.4 },
                                { label: 'Fatigue (ATL)', data: sum.form_chart_data.map(d => d.atl), borderColor: '#ef4444', tension: 0.4 }
                            ]
                        },
                        options: { scales: { y: { beginAtZero: true } }, plugins: { legend: { labels: { color: '#94a3b8' } } } }
                    });
                }
                const radarCtx = document.getElementById('radarChartCanvas');
                if (radarCtx) {
                    new Chart(radarCtx, {
                        type: 'radar',
                        data: {
                            labels: ['Run Miles', 'Bike Miles', 'Swim Miles'],
                            datasets: [{
                                label: 'Volume',
                                data: [sum.run_miles || 0, sum.bike_miles || 0, sum.swim_miles || 0],
                                backgroundColor: 'rgba(168,85,247,0.2)',
                                borderColor: '#a855f7'
                            }]
                        },
                        options: { scales: { r: { angleLines: { color: '#334155' }, grid: { color: '#334155' }, pointLabels: { color: '#94a3b8' } } }, plugins: { legend: { display: false } } }
                    });
                }
            }, 100);
        } else if (node._dataKey === 'heatmap_data' && typeof node._dataValue === 'object') {
            const heat = node._dataValue;
            html += `<div class="insp-section"><div class="insp-section-title">Team Progression Heatmap</div><div id="heatmapContainer" style="overflow-x:auto;"></div></div>`;
            setTimeout(() => {
                const container = document.getElementById('heatmapContainer');
                if (!container) return;
                let tableHtml = '<table style="width:100%; border-collapse: collapse; font-size: 0.75rem; color:#94a3b8;">';
                tableHtml += '<tr><th style="text-align:left; padding:4px;">Athlete</th><th style="text-align:left; padding:4px;">Progression</th></tr>';
                for (const [athlete, records] of Object.entries(heat)) {
                    tableHtml += `<tr><td style="padding:4px; border-top:1px solid #334155; white-space:nowrap;">${athlete}</td><td style="padding:4px; border-top:1px solid #334155; display:flex; gap:4px; flex-wrap:wrap;">`;
                    if (records.length > 0) {
                        const baseline = records[0].split;
                        records.forEach(r => {
                            const diff = r.split - baseline;
                            let color = '#3b82f6'; // neutral (blue)
                            if (diff < -1) color = '#22c55e'; // faster -> green
                            else if (diff > 1) color = '#ef4444'; // slower -> red
                            tableHtml += `<div style="width:16px; height:16px; background-color:${color}; border-radius:2px;" title="${r.date}: ${r.split}s"></div>`;
                        });
                    }
                    tableHtml += '</td></tr>';
                }
                tableHtml += '</table>';
                container.innerHTML = tableHtml;
            }, 100);
        }
    }

    inspectorBody.innerHTML = html;
    inspector.classList.remove('hidden');
    inspector.classList.add('visible');
}

function closeInspector() {
    inspector.classList.remove('visible');
    inspector.classList.add('hidden');
}
inspectorClose.addEventListener('click', closeInspector);

// ─── 10. MINIMAP ───────────────────────────────────────
function updateMinimap() {
    if (!network) return;
    const ctx = minimapCanvas.getContext('2d');
    ctx.clearRect(0, 0, 180, 120);
    const positions = network.getPositions();
    const ids = Object.keys(positions);
    if (ids.length === 0) return;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    ids.forEach(id => {
        const p = positions[id];
        if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x;
        if (p.y < minY) minY = p.y; if (p.y > maxY) maxY = p.y;
    });
    const pad = 50;
    const w = (maxX - minX) + pad * 2 || 1;
    const h = (maxY - minY) + pad * 2 || 1;
    const scale = Math.min(180 / w, 120 / h);

    ids.forEach(id => {
        const p = positions[id];
        const node = nodes.get(parseInt(id));
        const color = COLORS[node?._cat || 'data']?.border || '#334155';
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc((p.x - minX + pad) * scale, (p.y - minY + pad) * scale, 3, 0, Math.PI * 2);
        ctx.fill();
    });
}

// ─── 11. COMMAND PALETTE ───────────────────────────────
const COMMANDS = [
    { icon: '▶', text: 'Analyze Triathlon', hint: 'POST', action: () => { modeSelect.value = 'triathlon'; modeSelect.dispatchEvent(new Event('change')); executeBtn.click(); } },
    { icon: '▶', text: 'Analyze Rowing', hint: 'POST', action: () => { modeSelect.value = 'rowing'; modeSelect.dispatchEvent(new Event('change')); executeBtn.click(); } },
    { icon: '📊', text: 'Toggle Timeline', hint: 'view', action: () => { document.querySelector('.toggle-btn[data-view="timeline"]').click(); } },
    { icon: '🗺️', text: 'Fit Graph to View', hint: 'zoom', action: () => { if (network) network.fit({ animation: { duration: 800 } }); } }
];

function renderCommands(filter = '') {
    cmdList.innerHTML = '';
    COMMANDS.filter(c => c.text.toLowerCase().includes(filter.toLowerCase())).forEach((cmd, i) => {
        const el = document.createElement('div');
        el.className = `cmd-item ${i === 0 ? 'focused' : ''}`;
        el.innerHTML = `<span class="cmd-item-icon">${cmd.icon}</span><span class="cmd-item-text">${cmd.text}</span><span class="cmd-item-hint">${cmd.hint}</span>`;
        el.addEventListener('click', () => { closePalette(); cmd.action(); });
        cmdList.appendChild(el);
    });
}

function openPalette() { cmdPalette.classList.remove('hidden'); cmdInput.value = ''; renderCommands(); setTimeout(() => cmdInput.focus(), 50); }
function closePalette() { cmdPalette.classList.add('hidden'); }

document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); openPalette(); }
    if (e.key === 'Escape') { closePalette(); closeInspector(); }
});
cmdInput.addEventListener('input', () => renderCommands(cmdInput.value));
cmdInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const first = cmdList.querySelector('.cmd-item'); if (first) first.click(); } });
document.querySelector('.cmd-backdrop')?.addEventListener('click', closePalette);

// ─── 12. GRAPH ─────────────────────────────────────────
function initNetwork() {
    nodes.clear();
    edges.clear();
    idCounter = 1;

    const options = {
        layout: {
            hierarchical: {
                direction: 'LR',
                sortMethod: 'directed',
                levelSeparation: 260,
                nodeSpacing: 60,
                treeSpacing: 100,
                blockShifting: true,
                edgeMinimization: true,
                parentCentralization: true
            }
        },
        nodes: {
            shape: 'box',
            margin: { top: 14, bottom: 14, left: 18, right: 18 },
            borderWidth: 1.5,
            shadow: false,
            chosen: false
        },
        edges: {
            width: 1.5,
            smooth: { type: 'cubicBezier', forceDirection: 'horizontal', roundness: 0.5 },
            arrows: { to: { enabled: true, scaleFactor: 0.6 } },
            chosen: false
        },
        physics: false,
        interaction: { hover: true, dragNodes: false, dragView: true, zoomView: true, zoomSpeed: 0.6 }
    };

    if (network) network.destroy();
    network = new vis.Network(megaGraph, { nodes, edges }, options);

    network.on('click', (params) => {
        if (params.nodes.length > 0) openInspector(params.nodes[0]);
        else closeInspector();
    });

    network.on('afterDrawing', () => updateMinimap());
}

// ─── 13. FULLY EXPANDED DATA TREE ──────────────────────
function addDataTree(parentNodeId, obj, level) {
    if (!obj || typeof obj !== 'object') return;

    for (const [key, value] of Object.entries(obj)) {
        if (key === 'generated_at') continue;

        const nodeId = idCounter++;

        if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
            // Object: create a group label, then recurse
            const childCount = Object.keys(value).length;
            let borderColor = COLORS.data.border;
            if (key === 'insights' || key === 'load_summary' || key === 'performance_summary') borderColor = COLORS.processing.border;

            nodes.add({
                id: nodeId, label: `${key}`, level,
                color: { background: COLORS.data.bg, border: borderColor },
                font: { color: COLORS.data.font, face: 'JetBrains Mono', size: 13 },
                _title: key, _cat: 'data', _dataKey: key, _dataValue: value
            });
            edges.add({ from: parentNodeId, to: nodeId, color: { color: '#1e293b' }, arrows: 'to' });
            addDataTree(nodeId, value, level + 1);

        } else if (Array.isArray(value)) {
            let isAlertArr = (key === 'alerts' || key === 'risks' || key === 'active_alerts');
            let isInsightArr = (key === 'insights');
            let isRecArr = (key === 'recommendations');
            let borderColor = COLORS.data.border;
            let bgColor = COLORS.data.bg;
            let fontColor = COLORS.data.font;
            if (isAlertArr) { borderColor = COLORS.error.border; bgColor = COLORS.error.bg; fontColor = COLORS.error.font; }
            else if (isInsightArr) { borderColor = COLORS.output.border; bgColor = COLORS.output.bg; fontColor = COLORS.output.font; }
            else if (isRecArr) { borderColor = COLORS.input.border; bgColor = COLORS.input.bg; fontColor = COLORS.input.font; }

            // Parent array node
            nodes.add({
                id: nodeId, label: `${key}`, level,
                color: { background: bgColor, border: borderColor },
                font: { color: fontColor, face: 'JetBrains Mono', size: 13 },
                _title: key, _cat: isAlertArr ? 'error' : isInsightArr ? 'output' : isRecArr ? 'input' : 'data', _dataKey: key
            });
            edges.add({ from: parentNodeId, to: nodeId, color: { color: '#1e293b' }, arrows: 'to' });

            // Each array item as a child
            value.forEach((item, i) => {
                const childId = idCounter++;
                const strVal = String(item);
                const short = strVal.length > 40 ? strVal.substring(0, 40) + '…' : strVal;
                nodes.add({
                    id: childId, label: short, level: level + 1,
                    color: { background: bgColor, border: borderColor },
                    font: { color: fontColor, face: 'JetBrains Mono', size: 12 },
                    _title: `${key}[${i}]`, _cat: isAlertArr ? 'error' : isInsightArr ? 'output' : 'data',
                    _dataKey: `${key}[${i}]`, _dataValue: strVal, _isAlert: isAlertArr
                });
                edges.add({ from: nodeId, to: childId, color: { color: '#1e293b' }, arrows: 'to' });
            });

        } else {
            // Leaf
            const strVal = String(value);
            const short = strVal.length > 30 ? strVal.substring(0, 30) + '…' : strVal;
            nodes.add({
                id: nodeId, label: `${key}: ${short}`, level,
                color: { background: COLORS.data.bg, border: COLORS.data.border },
                font: { color: COLORS.data.font, face: 'JetBrains Mono', size: 12 },
                _title: key, _cat: 'data', _dataKey: key, _dataValue: strVal
            });
            edges.add({ from: parentNodeId, to: nodeId, color: { color: '#1e293b' }, arrows: 'to' });
        }
    }
}

// ─── 14. ANIMATED TRACE ────────────────────────────────
async function runTrace(mode, body) {
    initNetwork();
    closeInspector();
    traceTimeline = [];
    totalLatency = 0;
    
    const steps = getSteps(mode);

    // Add all exec nodes dimmed
    steps.forEach(step => {
        nodes.add({
            id: step.id, label: step.label, level: step.id,
            color: nodeColor(step.cat, 'dimmed'),
            font: nodeFont(step.cat, 'dimmed'),
            _title: step.label.split('\n')[0], _cat: step.cat, _execStep: step
        });
        
        if (mode === 'triathlon' || mode === 'rowing') {
            if (step.id === 5 || step.id === 7) {
                edges.add({ from: 4, to: step.id, color: { color: '#1e2030' }, arrows: 'to' });
            } else if (step.id === 6) {
                edges.add({ from: 5, to: 6, color: { color: '#1e2030' }, arrows: 'to' });
            } else if (step.id === 8) {
                edges.add({ from: 6, to: 8, color: { color: '#1e2030' }, arrows: 'to' });
                edges.add({ from: 7, to: 8, color: { color: '#1e2030' }, arrows: 'to' });
            } else if (step.id > 1 && step.id !== 5 && step.id !== 6 && step.id !== 7 && step.id !== 8) {
                edges.add({ from: step.id - 1, to: step.id, color: { color: '#1e2030' }, arrows: 'to' });
            }
        } else {
            // Linear flow for strava and sheets
            if (step.id > 1) {
                edges.add({ from: step.id - 1, to: step.id, color: { color: '#1e2030' }, arrows: 'to' });
            }
        }
    });
    idCounter = 20;

    await sleep(300);
    network.fit({ animation: { duration: 500 } });
    await sleep(600);

    // Fire fetch concurrently
    let fetchUrl = `/analyze/${mode}`;
    let fetchOpts = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    
    if (mode === 'sync_strava') {
        fetchUrl = `/sync/strava?access_token=${encodeURIComponent(body.access_token || '')}`;
        fetchOpts = { method: 'POST' };
    } else if (mode === 'sync_sheets') {
        fetchUrl = `/sync/sheets?domain=${encodeURIComponent(body.domain || 'triathlon')}`;
        fetchOpts = { method: 'POST' };
    }

    const fetchP = fetch(fetchUrl, fetchOpts).then(async r => { const d = await r.json(); if (!r.ok) throw d; return d; });

    // Animate through steps
    for (const step of steps) {
        await sleep(500);

        // Highlight current, normalize previous
        steps.forEach(s => {
            if (s.id === step.id) {
                nodes.update({ id: s.id, color: nodeColor(s.cat, 'active'), font: nodeFont(s.cat, 'active') });
            } else if (s.id < step.id) {
                nodes.update({ id: s.id, color: nodeColor(s.cat, 'normal'), font: nodeFont(s.cat, 'normal') });
            }
        });

        // Glow incoming edges
        edges.forEach(e => {
            if (e.to === step.id) edges.update({ id: e.id, color: { color: COLORS[step.cat].border }, width: 3 });
        });

        network.focus(step.id, { scale: 1.1, animation: { duration: 350, easingFunction: 'easeInOutQuad' } });

        const ts = new Date();
        totalLatency += step.latency;
        traceTimeline.push({ time: ts.toLocaleTimeString(), name: step.label.split('\n')[0], cat: step.cat, desc: step.desc, latency: step.latency });
    }

    // Wait for fetch
    try {
        responseData = await fetchP;
    } catch (err) {
        responseData = { error: err.detail || err.message || err };
    }

    // Normalize all
    await sleep(300);
    steps.forEach(s => {
        nodes.update({ id: s.id, color: nodeColor(s.cat, 'normal'), font: nodeFont(s.cat, 'normal') });
    });
    edges.forEach(e => edges.update({ id: e.id, width: 1.5 }));

    // Build fully expanded data tree
    addDataTree(9, responseData, 10);

    await sleep(200);
    network.fit({ animation: { duration: 1200, easingFunction: 'easeInOutQuad' } });

    const warnings = countWarnings(responseData);
    const degraded = responseData?.insights?.degraded ?? false;
    updateMetrics(totalLatency, warnings, nodes.length, degraded);
    viewToggle.classList.remove('hidden');
    minimapEl.classList.remove('hidden');
    populateTimeline();
}

// ─── 15. EXECUTE BUTTON ────────────────────────────────
executeBtn.addEventListener('click', async () => {
    const mode = modeSelect.value;
    const body = {};
    if (mode === 'triathlon') body.lookback_days = parseInt(document.getElementById('lookbackDays').value) || 7;
    else if (mode === 'rowing') body.athlete = document.getElementById('athleteName').value;
    else if (mode === 'sync_strava') body.access_token = document.getElementById('stravaAccessToken').value;
    else if (mode === 'sync_sheets') body.domain = document.getElementById('sheetsDomain').value;

    executeBtn.disabled = true;
    btnLoader.style.display = 'block';
    executeBtn.querySelector('.btn-text').style.opacity = '0.5';

    await runTrace(mode, body);

    executeBtn.disabled = false;
    btnLoader.style.display = 'none';
    executeBtn.querySelector('.btn-text').style.opacity = '1';
});

// ─── 16. INIT ──────────────────────────────────────────
initNetwork();
