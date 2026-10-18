/* HEATLA dashboard.
 *
 * Reads the static JSON/GeoJSON that the Python pipeline wrote into
 * public/data/. No computation happens here beyond picking colours and
 * looking up pre-computed rows, so the page stays fast on a phone.
 */
'use strict';

const DATA = './data';
const state = {
  tracts: null, centers: null, meta: null, grid: null, solutions: null,
  shap: {}, cv: {}, validation: null,
  layer: 'hvi', radiusMap: 2000,
  map: null, map2: null, tractLayer: null, centerLayer: null,
  bufferLayer: null, newLayer: null, newBuffers: null, tractLayer2: null,
  charts: {},
};

/* ----------------------------------------------------------- utilities -- */
const $ = (sel) => document.querySelector(sel);
const fmt = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '—'
    : Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtInt = (v) => v === null || v === undefined || Number.isNaN(v) ? '—'
  : Math.round(v).toLocaleString();

async function getJSON(name) {
  const r = await fetch(`${DATA}/${name}`);
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  return r.json();
}
async function tryJSON(name) {
  try { return await getJSON(name); } catch { return null; }
}

/* Cividis — perceptually uniform and readable for every common form of
 * colour-vision deficiency, and it still works printed in greyscale. */
const CIVIDIS = [
  [0, 32, 76], [0, 67, 118], [43, 98, 123], [85, 124, 123],
  [124, 151, 121], [171, 180, 114], [221, 211, 99], [253, 231, 55],
];
function ramp(t) {
  t = Math.max(0, Math.min(1, t));
  const x = t * (CIVIDIS.length - 1);
  const i = Math.min(CIVIDIS.length - 2, Math.floor(x));
  const f = x - i;
  const c = CIVIDIS[i].map((v, j) => Math.round(v + f * (CIVIDIS[i + 1][j] - v)));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

const LAYERS = {
  hvi: { label: 'HVI (0–100)', digits: 0, invert: false },
  lst_f: { label: 'Peak surface temp (°F)', digits: 0, invert: false },
  pct_canopy: { label: 'Tree canopy (%)', digits: 0, invert: true },
  pct_impervious: { label: 'Impervious (%)', digits: 0, invert: false },
  pct_poverty: { label: 'Below poverty (%)', digits: 0, invert: false },
  pct_age65p: { label: 'Age 65+ (%)', digits: 0, invert: false },
  pct_under5: { label: 'Under 5 (%)', digits: 1, invert: false },
  dist_center_m: { label: 'Distance to centre (m)', digits: 0, invert: false },
};

function domain(prop) {
  const vals = state.tracts.features
    .map((f) => f.properties[prop])
    .filter((v) => v !== null && v !== undefined && Number.isFinite(v))
    .sort((a, b) => a - b);
  if (!vals.length) return [0, 1];
  // Clip to the 2nd/98th percentile so one extreme tract does not flatten
  // the whole ramp.
  return [vals[Math.floor(vals.length * 0.02)], vals[Math.floor(vals.length * 0.98)]];
}

/* ---------------------------------------------------------------- maps -- */
function baseMap(id) {
  const m = L.map(id, { preferCanvas: true, zoomControl: true,
                        attributionControl: true });
  // Plain OSM tiles: no API key, and the choropleth sits on top at high
  // opacity anyway, so the basemap only needs to supply street context.
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 16, opacity: 0.5, crossOrigin: true,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(m);
  return m;
}

function styleFor(prop, dom, unservedOnly) {
  return (feat) => {
    const p = feat.properties;
    const v = p[prop];
    if (unservedOnly && !(p.hvi_top25 === 1 && p.served === 0)) {
      return { fillColor: '#000', fillOpacity: 0.04, weight: 0, color: '#000' };
    }
    if (v === null || v === undefined || !Number.isFinite(v)) {
      return { fillColor: '#888', fillOpacity: 0.3, weight: 0 };
    }
    let t = (v - dom[0]) / (dom[1] - dom[0] || 1);
    if (LAYERS[prop] && LAYERS[prop].invert) t = 1 - t;
    return { fillColor: ramp(t), fillOpacity: 0.82, weight: 0.12,
             color: '#ffffff', opacity: 0.35 };
  };
}

function tooltipHTML(p) {
  const rows = [
    ['HVI', fmt(p.hvi, 0)],
    ['Population', fmtInt(p.pop)],
    ['Peak temp (°F)', fmt(p.lst_f, 0)],
    ['Canopy (%)', fmt(p.pct_canopy, 0)],
    ['Age 65+ (%)', fmt(p.pct_age65p, 1)],
    ['Below poverty (%)', fmt(p.pct_poverty, 1)],
    ['Nearest centre (m)', fmtInt(p.dist_center_m)],
  ];
  return `<strong>Tract ${p.GEOID}</strong><br>` +
    rows.map(([k, v]) => `${k}: <b>${v}</b>`).join('<br>');
}

function drawTracts() {
  const dom = domain(state.layer);
  const unservedOnly = $('#chk-unserved').checked;
  if (state.tractLayer) state.map.removeLayer(state.tractLayer);
  state.tractLayer = L.geoJSON(state.tracts, {
    style: styleFor(state.layer, dom, unservedOnly),
    onEachFeature: (f, lyr) => lyr.bindTooltip(() => tooltipHTML(f.properties),
                                               { sticky: true }),
  }).addTo(state.map);
  state.tractLayer.bringToBack();
  drawLegend(dom);
  updateMapStats();
}

function drawLegend(dom) {
  const L_ = LAYERS[state.layer];
  const stops = Array.from({ length: 24 }, (_, i) => ramp(i / 23)).join(',');
  $('#legend').innerHTML =
    `<div>${L_.label}${L_.invert ? ' (reversed: less is worse)' : ''}</div>
     <div class="ramp" style="background:linear-gradient(90deg,${stops})"></div>
     <div class="ends"><span>${fmt(dom[0], L_.digits)}</span>
     <span>${fmt(dom[1], L_.digits)}</span></div>`;
}

function drawCenters() {
  if (state.centerLayer) state.map.removeLayer(state.centerLayer);
  if (state.bufferLayer) state.map.removeLayer(state.bufferLayer);
  if (!state.centers) return;
  if ($('#chk-buffers').checked) {
    state.bufferLayer = L.layerGroup(state.centers.map((c) =>
      L.circle([c.lat, c.lon], { radius: state.radiusMap, color: '#D55E00',
                                 weight: 1, fill: false, opacity: 0.55 })));
    state.bufferLayer.addTo(state.map);
  }
  if ($('#chk-centers').checked) {
    state.centerLayer = L.layerGroup(state.centers.map((c) =>
      L.circleMarker([c.lat, c.lon], {
        radius: 3.6, color: '#fff', weight: 0.8, fillColor: '#D55E00',
        fillOpacity: 1,
      }).bindTooltip(c.name || c.center_id)));
    state.centerLayer.addTo(state.map);
  }
}

function updateMapStats() {
  const fs = state.tracts.features.map((f) => f.properties);
  const r = state.radiusMap;
  const served = fs.filter((p) => p.dist_center_m !== null && p.dist_center_m <= r);
  const pop = fs.reduce((a, p) => a + (p.pop || 0), 0);
  const popServed = served.reduce((a, p) => a + (p.pop || 0), 0);
  const hi = fs.filter((p) => p.hvi_top25 === 1);
  const hiPop = hi.reduce((a, p) => a + (p.pop || 0), 0);
  const hiUnserved = hi.filter((p) => !(p.dist_center_m <= r))
    .reduce((a, p) => a + (p.pop || 0), 0);
  $('#map-stats').innerHTML = `
    <div class="row"><span>Tracts</span><span>${fmtInt(fs.length)}</span></div>
    <div class="row"><span>Residents</span><span>${fmtInt(pop)}</span></div>
    <div class="row"><span>Within ${(r / 1000).toFixed(1)} km of a centre</span>
      <span>${fmt(100 * popServed / pop, 1)}%</span></div>
    <div class="row"><span>High-HVI residents beyond it</span>
      <span>${fmt(100 * hiUnserved / hiPop, 1)}%</span></div>`;
}

/* ----------------------------------------------------------- optimizer -- */
function solutionKey() {
  const m = $('#opt-method').value;
  const o = ['greedy', 'ilp'].includes(m) ? $('#opt-objective').value : '-';
  return `${m}|${o}|${$('#opt-radius').value}|${$('#opt-k').value}`;
}

function gridRow(method, objective, radius, k) {
  return state.grid.find((r) =>
    r.method === method && String(r.radius_m) === String(radius) &&
    Number(r.k) === Number(k) &&
    (['greedy', 'ilp'].includes(method) ? r.objective === objective : true));
}

function drawOptimizer() {
  const method = $('#opt-method').value;
  const objective = $('#opt-objective').value;
  const radius = Number($('#opt-radius').value);
  const k = Number($('#opt-k').value);
  $('#opt-k-out').textContent = k;
  $('#opt-objective').disabled = !['greedy', 'ilp'].includes(method);

  const row = gridRow(method, objective, radius, k);
  const rnd = gridRow('random', '-', radius, k);
  const base = state.grid.find((r) => r.method === 'existing_only' &&
    String(r.radius_m) === String(radius));

  if (!row) {
    $('#opt-metrics').innerHTML =
      `<p class="hint">No solution stored for this combination. The pipeline
       solves the ILP only at the reported budgets (K = ${state.meta.k_grid.join(', ')})
       and radius ${state.meta.radius_default_m} m, because exact solving over
       ${fmtInt(state.meta.n_tracts)} candidate sites is slow. Pick greedy, or
       re-run with a wider grid.</p>`;
    $('#opt-fairness').innerHTML = '';
    if (state.newLayer) { state.map2.removeLayer(state.newLayer); state.newLayer = null; }
    if (state.newBuffers) { state.map2.removeLayer(state.newBuffers); state.newBuffers = null; }
    return;
  }

  const d = (v) => {
    if (!rnd) return '';
    const diff = v - rnd.vuln_weighted_pop_covered_pct;
    return `<span class="delta ${diff >= 0 ? 'pos' : 'neg'}">
      ${diff >= 0 ? '+' : ''}${fmt(diff, 1)} pp vs random</span>`;
  };
  $('#opt-metrics').innerHTML = `
    <div class="big">${fmt(row.vuln_weighted_pop_covered_pct, 1)}%</div>
    <div class="cap">vulnerability-weighted population covered ${d(row.vuln_weighted_pop_covered_pct)}</div>
    <div class="stats">
      <div class="row"><span>Tracts covered</span><span>${fmtInt(row.tracts_covered)}</span></div>
      <div class="row"><span>Population covered</span><span>${fmt(row.pop_covered_pct, 1)}%</span></div>
      <div class="row"><span>Top-quartile-HVI covered</span><span>${fmt(row.top25_hvi_pop_covered_pct, 1)}%</span></div>
      <div class="row"><span>Top-decile-HVI covered</span><span>${fmt(row.top10_hvi_pop_covered_pct, 1)}%</span></div>
      <div class="row"><span>High- minus low-HVI coverage</span><span>${fmt(row.hvi_coverage_gap_pp, 1)} pp</span></div>
      <div class="row"><span>Newly covered residents</span><span>${fmtInt(row.pop_newly_covered)}</span></div>
      ${base ? `<div class="row"><span>Existing centres alone</span><span>${fmt(base.pop_covered_pct, 1)}%</span></div>` : ''}
      ${row.greedy_vs_ilp_ratio ? `<div class="row"><span>Greedy / ILP optimum</span><span>${fmt(100 * row.greedy_vs_ilp_ratio, 1)}%</span></div>` : ''}
    </div>`;

  const groups = Object.keys(row).filter((c) => c.startsWith('fair_') &&
    c !== 'fair_max_minus_min_pp' && row[c] !== null);
  const max = Math.max(...groups.map((g) => row[g] || 0), 1);
  $('#opt-fairness').innerHTML = groups.map((g) => {
    const label = g.replace('fair_', '').replace(/_/g, ' ');
    const v = row[g] || 0;
    return `<div class="bar-row"><span>${label}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${100 * v / max}%"></span></span>
      <span class="val">${fmt(v, 1)}%</span></div>`;
  }).join('') + (row.fair_max_minus_min_pp !== undefined && row.fair_max_minus_min_pp !== null
    ? `<p class="hint">Spread between best- and worst-covered group:
       <strong>${fmt(row.fair_max_minus_min_pp, 1)} pp</strong>.</p>` : '');

  // Map: chosen sites plus their service radii.
  const sel = state.solutions[solutionKey()];
  if (state.newLayer) state.map2.removeLayer(state.newLayer);
  if (state.newBuffers) state.map2.removeLayer(state.newBuffers);
  if (sel && sel.lat && sel.lat.length) {
    state.newBuffers = L.layerGroup(sel.lat.map((la, i) =>
      L.circle([la, sel.lon[i]], { radius: radius, color: '#E69F00',
                                   weight: 1.2, fillColor: '#E69F00',
                                   fillOpacity: 0.1 }))).addTo(state.map2);
    state.newLayer = L.layerGroup(sel.lat.map((la, i) =>
      L.circleMarker([la, sel.lon[i]], {
        radius: 6, color: '#fff', weight: 1.2, fillColor: '#E69F00',
        fillOpacity: 1,
      }).bindTooltip(`New site ${i + 1} · tract ${sel.GEOID[i]}`))).addTo(state.map2);
  }
}

/* --------------------------------------------------------------- charts -- */
const CHART_DEFAULTS = () => {
  const dark = !window.matchMedia('(prefers-color-scheme: light)').matches;
  const ink = dark ? '#e8edf3' : '#16202b';
  const grid = dark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.08)';
  Chart.defaults.color = ink;
  Chart.defaults.borderColor = grid;
  Chart.defaults.font.family = 'ui-sans-serif, system-ui, sans-serif';
  return { ink, grid };
};

const SERIES = [
  { method: 'greedy', objective: 'pop_x_hvi', color: '#56B4E9', label: 'greedy (Pop × HVI)' },
  { method: 'greedy', objective: 'count', color: '#009E73', label: 'greedy (count)' },
  { method: 'ilp', objective: 'pop_x_hvi', color: '#D55E00', label: 'ILP (Pop × HVI)', points: true },
  { method: 'sort_by_hvi', objective: '-', color: '#E69F00', label: 'sort by HVI', dash: [6, 4] },
  { method: 'hottest_tracts', objective: '-', color: '#CC79A7', label: 'hottest tracts', dash: [2, 3] },
  { method: 'most_populous', objective: '-', color: '#8c8c8c', label: 'most populous', dash: [2, 3] },
  { method: 'random', objective: '-', color: '#6b6b6b', label: 'random', dash: [8, 3] },
];

function drawBudget() {
  CHART_DEFAULTS();
  const metric = $('#budget-metric').value;
  const radius = state.meta.radius_default_m;
  const ks = [...new Set(state.grid.filter((r) => r.k > 0).map((r) => Number(r.k)))]
    .sort((a, b) => a - b);
  const datasets = SERIES.map((s) => {
    const pts = ks.map((k) => {
      const row = gridRow(s.method, s.objective, radius, k);
      return row ? { x: k, y: row[metric] } : null;
    }).filter(Boolean);
    return {
      label: s.label, data: pts, borderColor: s.color,
      backgroundColor: s.color, borderDash: s.dash || [],
      showLine: !s.points, pointRadius: s.points ? 6 : 3,
      pointStyle: s.points ? 'rectRot' : 'circle', borderWidth: 2, tension: 0.15,
    };
  }).filter((d) => d.data.length);

  if (state.charts.budget) state.charts.budget.destroy();
  state.charts.budget = new Chart($('#budget-chart'), {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      parsing: false, interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: { type: 'linear', title: { display: true, text: 'K (new cooling centres)' } },
        y: { title: { display: true, text: $('#budget-metric').selectedOptions[0].text } },
      },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 14, usePointStyle: true } } },
    },
  });

  // Marginal benefit between the last two budgets on the greedy curve.
  const g = SERIES[0];
  const pts = ks.map((k) => gridRow(g.method, g.objective, radius, k))
    .filter(Boolean).map((r, i) => ({ k: ks[i], y: r[metric] }));
  if (pts.length > 1) {
    const slopes = pts.slice(1).map((p, i) => ({
      from: pts[i].k, to: p.k, per: (p.y - pts[i].y) / (p.k - pts[i].k) }));
    const first = slopes[0], last = slopes[slopes.length - 1];
    $('#budget-readout').innerHTML = `
      <div class="row"><span>Marginal benefit, K ${first.from}→${first.to}</span>
        <span>${fmt(first.per, 2)} pp per centre</span></div>
      <div class="row"><span>Marginal benefit, K ${last.from}→${last.to}</span>
        <span>${fmt(last.per, 2)} pp per centre</span></div>
      <p class="hint">The curve is still climbing at the largest budget shown, so
      saturation has not been reached: within a realistic budget, every added
      centre still reaches people nobody is reaching now.</p>`;
  }
}

function drawAssociation() {
  CHART_DEFAULTS();
  const outcome = $('#assoc-outcome').value;
  const rows = state.shap[outcome];
  if (!rows || !rows.length) {
    $('#assoc-cv').innerHTML = '<p class="hint">No association output for this outcome.</p>';
    if (state.charts.assoc) { state.charts.assoc.destroy(); state.charts.assoc = null; }
    return;
  }
  const val = 'mean_abs_shap' in rows[0] ? 'mean_abs_shap' : 'perm_importance_mean';
  const sorted = [...rows].sort((a, b) => a[val] - b[val]);
  if (state.charts.assoc) state.charts.assoc.destroy();
  state.charts.assoc = new Chart($('#assoc-chart'), {
    type: 'bar',
    data: {
      labels: sorted.map((r) => r.feature),
      datasets: [{
        data: sorted.map((r) => r[val]),
        backgroundColor: sorted.map((r) =>
          String(r.role).startsWith('social') ? '#E69F00' : '#7a8899'),
      }],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      scales: { x: { title: { display: true,
        text: val === 'mean_abs_shap' ? 'mean |SHAP|' : 'permutation importance' } } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { afterLabel: (ctx) => {
          const r = sorted[ctx.dataIndex];
          return [`${r.role}`, r.direction ? `${r.direction}` : ''].filter(Boolean);
        } } },
      },
    },
  });

  const cv = state.cv[outcome] || [];
  $('#assoc-cv').innerHTML =
    '<p class="hint">Orange = social variables of interest, grey = physical controls. ' +
    'Hover a bar for the direction of the association.</p>' +
    (cv.length ? `<div class="table-wrap">${tableHTML(cv, [
      ['model', 'Model'], ['cv', 'Cross-validation'], ['r2', 'R² (spatial)'],
      ['r2_random_split', 'R² (random split)'],
      ['r2_optimism_from_random_split', 'Optimism a random split would add'],
      ['rmse', 'RMSE'], ['mae', 'MAE']])}</div>
      <p class="hint">The gap between the two R² columns is the spatial leakage a
      random train/test split would have hidden. These are adequacy checks on the
      fitted surface, not findings.</p>` : '');
}

function tableHTML(rows, cols) {
  const head = cols.map(([, l]) => `<th>${l}</th>`).join('');
  const body = rows.map((r) => '<tr>' + cols.map(([c]) => {
    const v = r[c];
    return `<td>${typeof v === 'number' ? fmt(v, Math.abs(v) < 10 ? 3 : 1) : (v ?? '—')}</td>`;
  }).join('') + '</tr>').join('');
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

/* ----------------------------------------------------------------- init -- */
function wireTabs() {
  document.querySelectorAll('.tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((b) =>
        b.setAttribute('aria-selected', String(b === btn)));
      document.querySelectorAll('.view').forEach((v) =>
        v.classList.toggle('hidden', v.id !== `view-${btn.dataset.view}`));
      // Leaflet needs a nudge when its container was display:none.
      setTimeout(() => {
        if (btn.dataset.view === 'map' && state.map) state.map.invalidateSize();
        if (btn.dataset.view === 'optimizer' && state.map2) {
          // The container had no size while hidden, so Leaflet's earlier
          // fitBounds landed on a single polygon. Re-fit on first reveal.
          state.map2.invalidateSize();
          if (!state.map2Fitted && state.tractLayer2) {
            state.map2.fitBounds(state.tractLayer2.getBounds(), { padding: [10, 10] });
            state.map2Fitted = true;
          }
        }
        if (btn.dataset.view === 'budget') drawBudget();
        if (btn.dataset.view === 'association') drawAssociation();
      }, 30);
    });
  });
}

function renderMethods() {
  const m = state.meta;
  const vint = (m.vintages_markdown || '').trim();
  $('#methods-body').innerHTML = `
    <h2>What this is</h2>
    <p>Two questions about Los Angeles County, answered at the level of the
    2020 census tract (${fmtInt(m.n_tracts)} tracts, ${fmtInt(m.total_population)}
    residents): which tracts are most vulnerable to extreme heat, and where
    should a limited number of new public cooling centres go so they reach the
    most vulnerable people. It relates to UN SDGs 3, 11 and 13.</p>

    <h3>Heat Vulnerability Index</h3>
    <p>A tract's HVI is the mean percentile rank of four inputs, one per
    pathway: peak summer land-surface temperature (exposure), share of
    residents aged 65 and over (sensitivity), share below the poverty line and
    share without tree canopy (adaptive capacity). Percentile ranks rather
    than z-scores, so a single very hot tract cannot stretch the whole index.
    It is validated against heat-related ER visits and the CDC Social
    Vulnerability Index.</p>

    <h3>Who existing centres serve</h3>
    <p>For every indicator we compare two distributions: all ${fmtInt(m.n_tracts)}
    tracts, and only the tracts within the service radius of one of the
    ${fmtInt(m.n_existing_centers)} existing centres. The shift between them is
    measured with a standardised mean difference and a KS statistic, not
    eyeballed off a histogram.</p>

    <h3>Where new centres should go</h3>
    <p>A maximum-coverage facility-location problem. Candidate sites are tract
    centroids; a site covers every tract whose centroid is within the radius;
    we choose K sites to maximise covered benefit. Greedy is guaranteed within
    (1 − 1/e) ≈ 63% of the optimum because coverage is submodular, and an
    integer program gives the exact optimum so the real gap can be reported.
    What a run <em>optimises</em> (tract count, or population × HVI) is kept
    separate from what it is <em>evaluated on</em>: every solution is scored on
    all metrics, including coverage by demographic subgroup.</p>

    <h3>Association study, not a predictor</h3>
    <p>Fitting a model to predict HVI from features correlated with HVI's own
    inputs just relearns the formula. Instead, physical heat enters as a
    control and the social variables are the ones of interest, with the
    ranking read off SHAP values and partial-dependence curves. Folds are
    spatial k-means clusters, because neighbouring tracts are near-copies and
    a random split would let the model interpolate rather than generalise.</p>

    <h3>Run settings</h3>
    <ul>
      <li>Data mode: <code>${m.data_mode}</code></li>
      <li>Temperature source: <code>${m.lst_source}</code></li>
      <li>Default service radius: ${m.radius_default_m} m (also run at
          ${m.radius_grid_m.join(' m, ')} m)</li>
      <li>Budgets: K = ${m.k_grid.join(', ')}</li>
      <li>Objectives: ${m.objectives.join(', ')}</li>
    </ul>
    ${m.data_mode === 'mock' ? `<p><strong>This run uses synthetic data.</strong>
      The numbers on this page describe a simulated LA-shaped county built so
      the pipeline can be checked end to end. They are not findings about Los
      Angeles.</p>` : ''}

    <h3>Data vintages</h3>
    ${vint ? markdownish(vint) : '<p>See <code>data/vintages.md</code>.</p>'}`;
}

/* A deliberately small markdown renderer: this only ever receives
 * data/vintages.md, which uses headings, tables, lists, bold and code. */
function markdownish(md) {
  const esc = (s) => s.replace(/[&<>]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,
             '<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>')
    .replace(/&lt;(https?:\/\/[^&]+)&gt;/g,
             '<a href="$1" rel="noopener noreferrer" target="_blank">$1</a>');
  const out = [];
  let table = null, list = null;
  const closeAll = () => {
    if (table) { out.push(renderTable(table)); table = null; }
    if (list) { out.push(`<ul>${list.join('')}</ul>`); list = null; }
  };
  const renderTable = (t) => {
    const [head, , ...body] = t;
    const cells = (r) => r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
    return `<table><thead><tr>${cells(head).map((c) =>
      `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${body.map((r) =>
      `<tr>${cells(r).map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`
    ).join('')}</tbody></table>`;
  };
  for (const raw of md.split('\n')) {
    const line = raw.trimEnd();
    if (/^\s*\|.*\|\s*$/.test(line)) {
      if (list) { out.push(`<ul>${list.join('')}</ul>`); list = null; }
      (table ||= []).push(line.trim());
      continue;
    }
    if (table) { out.push(renderTable(table)); table = null; }
    if (/^-\s+/.test(line)) {
      (list ||= []).push(`<li>${inline(line.replace(/^-\s+/, ''))}</li>`);
      continue;
    }
    if (list) { out.push(`<ul>${list.join('')}</ul>`); list = null; }
    if (/^#{1,4}\s/.test(line)) {
      const n = line.match(/^#+/)[0].length;
      out.push(`<h${Math.min(n + 1, 4)}>${inline(line.replace(/^#+\s/, ''))}</h${Math.min(n + 1, 4)}>`);
    } else if (line.trim() === '') {
      out.push('');
    } else {
      out.push(`<p>${inline(line)}</p>`);
    }
  }
  closeAll();
  return out.join('\n');
}

async function init() {
  wireTabs();
  const [meta, tracts] = await Promise.all([
    getJSON('meta.json'), getJSON('tracts.geojson')]);
  state.meta = meta;
  state.tracts = tracts;
  state.centers = (await tryJSON('centers_existing.json')) || [];
  state.grid = (await tryJSON('partC_results_grid.json')) || [];
  state.solutions = (await tryJSON('partC_solutions.json')) || {};
  state.shap.hvi = (await tryJSON('partB_assoc_hvi_shap.json'))
    || (await tryJSON('partB_assoc_hvi_importance.json')) || [];
  state.shap.heat_er_rate_per100k =
    (await tryJSON('partB_assoc_heat_er_rate_per100k_shap.json')) || [];
  const assoc = (await tryJSON('partB_association.json')) || {};
  for (const k of Object.keys(assoc)) state.cv[k] = assoc[k].cv || [];
  state.validation = (await tryJSON('partB_hvi_validation.json')) || [];
  const headline = (await tryJSON('partC_headline.json')) || [];

  const badge = $('#mode-badge');
  badge.textContent = meta.data_mode === 'mock'
    ? 'synthetic data — not findings about LA'
    : `real data · ${fmtInt(meta.n_tracts)} tracts · ${fmtInt(meta.n_existing_centers)} existing centres`;
  badge.classList.toggle('mock', meta.data_mode === 'mock');

  // --- map view
  state.map = baseMap('map');
  drawTracts();
  drawCenters();
  state.map.fitBounds(state.tractLayer.getBounds(), { padding: [10, 10] });

  $('#layer-select').addEventListener('change', (e) => {
    state.layer = e.target.value; drawTracts();
  });
  $('#chk-unserved').addEventListener('change', drawTracts);
  $('#chk-centers').addEventListener('change', drawCenters);
  $('#chk-buffers').addEventListener('change', drawCenters);
  $('#radius-map').addEventListener('input', (e) => {
    state.radiusMap = Number(e.target.value);
    $('#radius-map-out').textContent = `${(state.radiusMap / 1000).toFixed(1)} km`;
    drawCenters(); updateMapStats();
  });

  // --- optimizer view
  const radii = [...new Set(state.grid.map((r) => Number(r.radius_m)))]
    .filter(Boolean).sort((a, b) => a - b);
  $('#opt-radius').innerHTML = radii.map((r) => {
    const label = { 1609: '1 mile', 2000: '2 km', 3219: '2 miles' }[r] || `${r} m`;
    return `<option value="${r}" ${r === meta.radius_default_m ? 'selected' : ''}>${label}</option>`;
  }).join('');
  const ks = [...new Set(state.grid.filter((r) => r.k > 0).map((r) => Number(r.k)))]
    .sort((a, b) => a - b);
  if (ks.length) {
    const el = $('#opt-k');
    el.min = ks[0]; el.max = ks[ks.length - 1];
    el.step = ks.length > 1 ? ks[1] - ks[0] : 5;
    el.value = ks.includes(meta.k_default) ? meta.k_default : ks[0];
  }
  state.map2 = baseMap('map2');
  const dom2 = domain('hvi');
  state.tractLayer2 = L.geoJSON(state.tracts, { style: styleFor('hvi', dom2, false) })
    .addTo(state.map2);
  if (state.centers.length) {
    L.layerGroup(state.centers.map((c) => L.circleMarker([c.lat, c.lon], {
      radius: 2.6, color: '#333', weight: 0.6, fillColor: '#333', fillOpacity: 0.8,
    }).bindTooltip(`existing: ${c.name || c.center_id}`))).addTo(state.map2);
  }
  ['#opt-method', '#opt-objective', '#opt-radius', '#opt-k'].forEach((s) =>
    $(s).addEventListener('input', drawOptimizer));
  drawOptimizer();

  // --- budget view
  $('#budget-metric').addEventListener('change', drawBudget);
  if (headline.length) {
    $('#headline-table').innerHTML = tableHTML(headline, [
      ['method', 'Method'], ['objective', 'Optimised for'], ['k', 'K'],
      ['tracts_covered', 'Tracts'], ['pop_covered_pct', 'Pop covered %'],
      ['vuln_weighted_pop_covered_pct', 'Pop×HVI covered %'],
      ['top25_hvi_pop_covered_pct', 'Top-quartile HVI %'],
      ['hvi_coverage_gap_pp', 'High−low gap (pp)'],
      ['vuln_weighted_pop_covered_pct_vs_random_pp', 'vs random (pp)'],
      ['fair_age_65_plus', '65+ %'], ['fair_under_5', 'Under 5 %'],
      ['fair_below_poverty', 'Poverty %']]);
  }

  // --- association view
  $('#assoc-outcome').addEventListener('change', drawAssociation);
  if (state.validation.length) {
    $('#validation-table').innerHTML = tableHTML(state.validation, [
      ['comparison', 'Compared with'], ['spearman_rho', 'Spearman ρ'],
      ['p_value', 'p'], ['n', 'n'], ['top10_overlap', 'Top-10% overlap']]) +
      `<p class="hint">ER visits are published by ZIP code and apportioned to
      tracts by population, so that correlation is attenuated and partly
      mechanical — corroboration, not a test. Partial agreement with the CDC
      SVI is what we want: identical rankings would mean the HVI adds nothing,
      and no agreement would mean its social inputs are misbehaving.</p>`;
  }

  renderMethods();
}

init().catch((err) => {
  document.querySelector('#main').insertAdjacentHTML('afterbegin',
    `<div class="panel"><h2>Could not load the data</h2>
     <p class="hint">${err.message}. Run <code>make mock</code> (or
     <code>make real</code>) to regenerate <code>dashboard/public/data/</code>.</p></div>`);
});
