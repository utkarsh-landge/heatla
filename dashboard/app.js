/* HEATLA dashboard.
 *
 * Reads the static JSON and GeoJSON the Python pipeline wrote into
 * public/data/. Nothing is computed here beyond picking colours and looking
 * up pre-computed rows, so the page stays quick on a phone.
 */
'use strict';

const DATA = './data';

const state = {
  tracts: null, centers: [], meta: null, grid: [], solutions: {},
  shap: {}, cv: {}, validation: [], headline: [],
  layer: 'hvi', radiusMap: 2000,
  map: null, map2: null, map2Fitted: false,
  tractLayer: null, tractLayer2: null, centerLayer: null, bufferLayer: null,
  newLayer: null, newBuffers: null, charts: {},
};

/* ----------------------------------------------------------- utilities -- */
const $ = (s) => document.querySelector(s);
const fmt = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(Number(v)) ? '—'
    : Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtInt = (v) =>
  v === null || v === undefined || Number.isNaN(Number(v)) ? '—' : Math.round(v).toLocaleString();
const millions = (v) => `${(v / 1e6).toFixed(2)} million`;

async function getJSON(name) {
  const r = await fetch(`${DATA}/${name}`);
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  return r.json();
}
const tryJSON = async (n) => { try { return await getJSON(n); } catch { return null; } };

/* Cividis: perceptually uniform, legible with any common colour-vision
 * deficiency, and still readable printed in greyscale. */
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
const RAMP_CSS = Array.from({ length: 24 }, (_, i) => ramp(i / 23)).join(',');

const LAYERS = {
  hvi: { label: 'Heat vulnerability index', unit: '', digits: 0, invert: false, ends: ['less vulnerable', 'more vulnerable'] },
  lst_f: { label: 'Peak summer surface temperature', unit: '°F', digits: 0, invert: false, ends: ['cooler', 'hotter'] },
  pct_canopy: { label: 'Tree canopy', unit: '%', digits: 0, invert: true, ends: ['more canopy', 'less canopy'] },
  pct_impervious: { label: 'Impervious surface', unit: '%', digits: 0, invert: false, ends: ['less paved', 'more paved'] },
  pct_poverty: { label: 'Below the poverty line', unit: '%', digits: 0, invert: false, ends: ['lower', 'higher'] },
  pct_age65p: { label: 'Residents aged 65 and over', unit: '%', digits: 0, invert: false, ends: ['fewer', 'more'] },
  pct_under5: { label: 'Residents under 5', unit: '%', digits: 1, invert: false, ends: ['fewer', 'more'] },
  dist_center_m: { label: 'Distance to the nearest centre', unit: ' m', digits: 0, invert: false, ends: ['closer', 'further'] },
};

function domain(prop) {
  const v = state.tracts.features
    .map((f) => f.properties[prop])
    .filter((x) => Number.isFinite(x))
    .sort((a, b) => a - b);
  if (!v.length) return [0, 1];
  // Clipped to the 2nd and 98th percentile: one extreme tract should not
  // flatten the ramp for everywhere else.
  return [v[Math.floor(v.length * 0.02)], v[Math.floor(v.length * 0.98)]];
}

/* ---------------------------------------------------------------- maps -- */
function baseMap(id) {
  // Zoom sits on the right so it never collides with the control overlay.
  const m = L.map(id, { preferCanvas: true, zoomControl: false, attributionControl: true });
  L.control.zoom({ position: 'topright' }).addTo(m);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 16, opacity: 0.42, crossOrigin: true,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(m);
  return m;
}

function styleFor(prop, dom, unservedOnly) {
  return (feat) => {
    const p = feat.properties;
    if (unservedOnly && !(p.hvi_top25 === 1 && p.served === 0)) {
      return { fillColor: '#000', fillOpacity: 0.05, weight: 0 };
    }
    const v = p[prop];
    if (!Number.isFinite(v)) return { fillColor: '#6b7a86', fillOpacity: 0.25, weight: 0 };
    let t = (v - dom[0]) / (dom[1] - dom[0] || 1);
    if (LAYERS[prop]?.invert) t = 1 - t;
    return { fillColor: ramp(t), fillOpacity: 0.84, weight: 0.1, color: '#000', opacity: 0.2 };
  };
}

function tooltipHTML(p) {
  const rows = [
    ['Vulnerability index', fmt(p.hvi, 0)],
    ['Residents', fmtInt(p.pop)],
    ['Peak surface temp', `${fmt(p.lst_f, 0)} °F`],
    ['Tree canopy', `${fmt(p.pct_canopy, 0)}%`],
    ['Aged 65+', `${fmt(p.pct_age65p, 1)}%`],
    ['Below poverty', `${fmt(p.pct_poverty, 1)}%`],
    ['Nearest centre', `${fmtInt(p.dist_center_m)} m`],
  ];
  return `<span class="tt-head">Tract ${p.GEOID}</span>` +
    rows.map(([k, v]) => `${k} <b>${v}</b>`).join('<br>');
}

function drawTracts() {
  const dom = domain(state.layer);
  const unservedOnly = $('#chk-unserved').checked;
  if (state.tractLayer) state.map.removeLayer(state.tractLayer);
  state.tractLayer = L.geoJSON(state.tracts, {
    style: styleFor(state.layer, dom, unservedOnly),
    onEachFeature: (f, lyr) => lyr.bindTooltip(() => tooltipHTML(f.properties), { sticky: true }),
  }).addTo(state.map);
  state.tractLayer.bringToBack();
  drawLegend(dom);
  updateMapStats();
}

function drawLegend(dom) {
  const L_ = LAYERS[state.layer];
  const lo = `${fmt(dom[0], L_.digits)}${L_.unit}`;
  const hi = `${fmt(dom[1], L_.digits)}${L_.unit}`;
  $('#legend').innerHTML =
    `<div class="legend-name">${L_.label}</div>
     <div class="ramp" style="background:linear-gradient(90deg,${RAMP_CSS})"></div>
     <div class="ends"><span>${L_.invert ? hi : lo}</span><span>${L_.invert ? lo : hi}</span></div>`;
  $('#scale-mid').textContent = L_.label.toLowerCase();
  $('.scale-cap .lo').textContent = L_.ends[0];
  $('.scale-cap .hi').textContent = L_.ends[1];
}

function drawCenters() {
  if (state.centerLayer) state.map.removeLayer(state.centerLayer);
  if (state.bufferLayer) state.map.removeLayer(state.bufferLayer);
  if (!state.centers.length) return;
  if ($('#chk-buffers').checked) {
    state.bufferLayer = L.layerGroup(state.centers.map((c) =>
      L.circle([c.lat, c.lon], {
        radius: state.radiusMap, color: '#FFC94A', weight: 0.9,
        fill: false, opacity: 0.5,
      }))).addTo(state.map);
  }
  if ($('#chk-centers').checked) {
    state.centerLayer = L.layerGroup(state.centers.map((c) =>
      L.circleMarker([c.lat, c.lon], {
        radius: 3.4, color: '#0C1319', weight: 1, fillColor: '#FFC94A', fillOpacity: 1,
      }).bindTooltip(`<span class="tt-head">Existing centre</span>${c.name || c.center_id}`)))
      .addTo(state.map);
  }
}

function cell(value, label, extra = '', lead = false) {
  return `<div class="cell"><div class="v${lead ? ' lead' : ''}">${value}</div>
          <div class="k">${label}</div>${extra}</div>`;
}

function updateMapStats() {
  const fs = state.tracts.features.map((f) => f.properties);
  const r = state.radiusMap;
  const sum = (arr, f) => arr.reduce((a, p) => a + (f(p) || 0), 0);
  const served = (p) => Number.isFinite(p.dist_center_m) && p.dist_center_m <= r;
  const pop = sum(fs, (p) => p.pop);
  const popServed = sum(fs.filter(served), (p) => p.pop);
  const hi = fs.filter((p) => p.hvi_top25 === 1);
  const hiPop = sum(hi, (p) => p.pop);
  const hiUnserved = sum(hi.filter((p) => !served(p)), (p) => p.pop);
  const elderUnserved = sum(fs.filter((p) => !served(p)), (p) => (p.pct_age65p / 100) * p.pop);
  const elderAll = sum(fs, (p) => (p.pct_age65p / 100) * p.pop);

  $('#map-stats').innerHTML =
    cell(fmtInt(fs.length), 'census tracts in the county') +
    cell(fmtInt(pop), 'residents') +
    cell(`${fmt(100 * popServed / pop, 1)}%`, `live within ${(r / 1000).toFixed(1)} km of a centre`) +
    cell(`${fmt(100 * hiUnserved / hiPop, 1)}%`,
         'of the most vulnerable quarter have none in reach', '', true) +
    cell(fmtInt(hiUnserved), 'people in that gap') +
    cell(`${fmt(100 * elderUnserved / elderAll, 1)}%`, 'of residents aged 65+ have none in reach');

  // The opening statement restates whatever the reader is currently looking at.
  $('#hero-num').textContent = millions(hiUnserved);
  $('#hero-rest').textContent =
    ` people live in the most heat-vulnerable quarter of Los Angeles County with no cooling centre within ${(r / 1000).toFixed(1)} km.`;
}

/* ----------------------------------------------------------- the siting -- */
const solutionKey = () => {
  const m = $('#opt-method').value;
  const o = ['greedy', 'ilp'].includes(m) ? $('#opt-objective').value : '-';
  return `${m}|${o}|${$('#opt-radius').value}|${$('#opt-k').value}`;
};

const gridRow = (method, objective, radius, k) => state.grid.find((r) =>
  r.method === method && String(r.radius_m) === String(radius) && Number(r.k) === Number(k) &&
  (['greedy', 'ilp'].includes(method) ? r.objective === objective : true));

function drawOptimizer() {
  const method = $('#opt-method').value;
  const objective = $('#opt-objective').value;
  const radius = Number($('#opt-radius').value);
  const k = Number($('#opt-k').value);
  $('#opt-k-out').textContent = k;
  $('#opt-objective').disabled = !['greedy', 'ilp'].includes(method);

  const row = gridRow(method, objective, radius, k);
  const rnd = gridRow('random', '-', radius, k);
  const base = state.grid.find((r) => r.method === 'existing_only' && String(r.radius_m) === String(radius));

  if (!row) {
    $('#opt-metrics').innerHTML =
      `<div class="cell"><div class="k">The exact optimum is solved only at the
       reported budgets (${state.meta.k_grid.join(', ')} centres) and a
       ${state.meta.radius_default_m} m radius, because solving exactly over
       ${fmtInt(state.meta.n_tracts)} candidate sites is slow. Switch to greedy,
       or widen the grid in <code>config.yaml</code> and re-run.</div></div>`;
    $('#opt-fairness').innerHTML = '';
    [state.newLayer, state.newBuffers].forEach((l) => l && state.map2.removeLayer(l));
    state.newLayer = state.newBuffers = null;
    return;
  }

  const delta = rnd ? row.vuln_weighted_pop_covered_pct - rnd.vuln_weighted_pop_covered_pct : null;
  const deltaHTML = delta === null ? '' :
    `<div class="d ${delta >= 0 ? 'pos' : 'neg'}">${delta >= 0 ? '+' : ''}${fmt(delta, 1)} points against placing them at random</div>`;

  $('#opt-metrics').innerHTML =
    cell(`${fmt(row.top25_hvi_pop_covered_pct, 1)}%`,
         'of the most vulnerable quarter end up within reach', '', true) +
    cell(`${fmt(row.vuln_weighted_pop_covered_pct, 1)}%`,
         'of people weighted by vulnerability', deltaHTML) +
    cell(fmtInt(row.pop_newly_covered), 'residents reached who are not reached today') +
    cell(`${fmt(row.pop_covered_pct, 1)}%`,
         `of all residents, against ${base ? fmt(base.pop_covered_pct, 1) : '—'}% today`) +
    cell(`${fmt(row.hvi_coverage_gap_pp, 1)} pts`,
         'more of the vulnerable quarter covered than the least vulnerable') +
    (row.greedy_vs_ilp_ratio
      ? cell(`${fmt(100 * row.greedy_vs_ilp_ratio, 1)}%`, 'of the exact optimum, reached by greedy')
      : cell(fmtInt(row.tracts_covered), 'tracts within reach in total'));

  // Fairness: each group against the figure for all residents.
  const all = row.pop_covered_pct;
  const groups = Object.keys(row)
    .filter((c) => c.startsWith('fair_') && c !== 'fair_max_minus_min_pp' && Number.isFinite(row[c]));
  const NAMES = {
    fair_age_65_plus: 'Aged 65+', fair_under_5: 'Under 5', fair_under_18: 'Under 18',
    fair_below_poverty: 'Below poverty', fair_hispanic: 'Hispanic or Latino',
    fair_black: 'Black', fair_asian: 'Asian', fair_white_nh: 'White, non-Hispanic',
    fair_all_residents: 'All residents',
  };
  const max = Math.max(...groups.map((g) => row[g]), all) * 1.12;
  $('#opt-fairness').innerHTML = groups.map((g) => {
    const v = row[g];
    const behind = g !== 'fair_all_residents' && v < all - 0.15;
    return `<div class="bar${behind ? ' behind' : ''}">
      <span class="lab">${NAMES[g] || g.replace('fair_', '').replace(/_/g, ' ')}</span>
      <span class="track">
        <span class="fill" style="width:${100 * v / max}%"></span>
        <span class="ref" style="left:${100 * all / max}%" title="all residents"></span>
      </span>
      <span class="val">${fmt(v, 1)}%</span></div>`;
  }).join('') +
    (Number.isFinite(row.fair_max_minus_min_pp)
      ? `<p class="note" style="margin-top:14px">Best-covered group to worst-covered:
         <strong>${fmt(row.fair_max_minus_min_pp, 1)} points</strong> apart.</p>` : '');

  const sel = state.solutions[solutionKey()];
  [state.newLayer, state.newBuffers].forEach((l) => l && state.map2.removeLayer(l));
  state.newLayer = state.newBuffers = null;
  if (sel?.lat?.length) {
    state.newBuffers = L.layerGroup(sel.lat.map((la, i) =>
      L.circle([la, sel.lon[i]], {
        radius, color: '#FFC94A', weight: 1.1, fillColor: '#FFC94A', fillOpacity: 0.09,
      }))).addTo(state.map2);
    state.newLayer = L.layerGroup(sel.lat.map((la, i) =>
      L.circleMarker([la, sel.lon[i]], {
        radius: 5.5, color: '#0C1319', weight: 1.4, fillColor: '#FFC94A', fillOpacity: 1,
      }).bindTooltip(`<span class="tt-head">Proposed site ${i + 1}</span>tract ${sel.GEOID[i]}`)))
      .addTo(state.map2);
  }
}

/* --------------------------------------------------------------- charts -- */
function chartTheme() {
  const css = getComputedStyle(document.documentElement);
  const ink = css.getPropertyValue('--ink').trim();
  const soft = css.getPropertyValue('--ink-faint').trim();
  const grid = css.getPropertyValue('--rule-soft').trim();
  Chart.defaults.color = soft;
  Chart.defaults.borderColor = grid;
  Chart.defaults.font.family = 'Archivo, ui-sans-serif, system-ui, sans-serif';
  Chart.defaults.font.size = 11.5;
  return { ink, soft, grid };
}

const SERIES = [
  { method: 'greedy', objective: 'pop_x_hvi', color: '#FFC94A', label: 'Greedy, weighted by vulnerability', width: 2.4 },
  { method: 'ilp', objective: 'pop_x_hvi', color: '#FDE737', label: 'Exact optimum', points: true },
  { method: 'greedy', objective: 'count', color: '#AFB472', label: 'Greedy, by tract count' },
  { method: 'sort_by_hvi', objective: '-', color: '#4B6378', label: 'Ranked by vulnerability', dash: [5, 4] },
  { method: 'hottest_tracts', objective: '-', color: '#16426F', label: 'Hottest tracts', dash: [2, 3] },
  { method: 'most_populous', objective: '-', color: '#2F4858', label: 'Most populous tracts', dash: [2, 3] },
  { method: 'random', objective: '-', color: '#7A8F9E', label: 'Placed at random', dash: [8, 4] },
];

function drawBudget() {
  const t = chartTheme();
  const metric = $('#budget-metric').value;
  const radius = state.meta.radius_default_m;
  const ks = [...new Set(state.grid.filter((r) => r.k > 0).map((r) => Number(r.k)))].sort((a, b) => a - b);

  const datasets = SERIES.map((s) => {
    const data = ks.map((k) => {
      const row = gridRow(s.method, s.objective, radius, k);
      return row ? { x: k, y: row[metric] } : null;
    }).filter(Boolean);
    return {
      label: s.label, data, borderColor: s.color, backgroundColor: s.color,
      borderDash: s.dash || [], showLine: !s.points,
      pointRadius: s.points ? 5 : 2.5, pointHoverRadius: s.points ? 7 : 5,
      pointStyle: s.points ? 'rectRot' : 'circle',
      borderWidth: s.width || 1.6, tension: 0.2,
    };
  }).filter((d) => d.data.length);

  state.charts.budget?.destroy();
  state.charts.budget = new Chart($('#budget-chart'), {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false, parsing: false,
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: { type: 'linear', title: { display: true, text: 'new cooling centres', color: t.soft },
             grid: { color: t.grid }, border: { color: t.grid } },
        y: { title: { display: true, text: $('#budget-metric').selectedOptions[0].text, color: t.soft },
             grid: { color: t.grid }, border: { color: t.grid } },
      },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 14 } },
        tooltip: { callbacks: { title: (i) => `${i[0].parsed.x} new centres`,
                                label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y, 1)}%` } },
      },
    },
  });

  const pts = ks.map((k) => {
    const r = gridRow('greedy', 'pop_x_hvi', radius, k);
    return r ? { k, y: r[metric] } : null;
  }).filter(Boolean);
  if (pts.length > 1) {
    const slope = (a, b) => (b.y - a.y) / (b.k - a.k);
    const first = slope(pts[0], pts[1]);
    const last = slope(pts[pts.length - 2], pts[pts.length - 1]);
    $('#budget-readout').innerHTML =
      cell(`${fmt(first, 2)} pts`, `added per centre between ${pts[0].k} and ${pts[1].k}`, '', true) +
      cell(`${fmt(last, 2)} pts`, `still added per centre between ${pts[pts.length - 2].k} and ${pts[pts.length - 1].k}`) +
      cell(`${fmt(100 * last / first, 0)}%`, 'of the early return, so the curve has barely bent') +
      cell(fmtInt(state.meta.n_existing_centers), 'centres the county operates today');
  }
}

function drawAssociation() {
  const t = chartTheme();
  const outcome = $('#assoc-outcome').value;
  const rows = state.shap[outcome] || [];
  if (!rows.length) {
    $('#assoc-cv').innerHTML = '<p class="note">No association output for this outcome.</p>';
    state.charts.assoc?.destroy();
    state.charts.assoc = null;
    return;
  }
  const NICE = {
    pct_age65p: 'Aged 65 and over', pct_under5: 'Under 5', pct_under18: 'Under 18',
    pct_poverty: 'Below poverty', median_income: 'Median income',
    pct_hispanic: 'Hispanic or Latino', pct_black: 'Black', pct_asian: 'Asian',
    pct_white_nh: 'White, non-Hispanic', svi: 'Social vulnerability index',
    lst_f: 'Surface temperature', pct_impervious: 'Impervious surface',
    pct_canopy: 'Tree canopy', pop_density_km2: 'Population density',
    land_area_sqkm: 'Tract land area', ces_pollution_pctl: 'Pollution burden',
  };
  const val = 'mean_abs_shap' in rows[0] ? 'mean_abs_shap' : 'perm_importance_mean';
  const sorted = [...rows].sort((a, b) => a[val] - b[val]);
  const isSocial = (r) => String(r.role).startsWith('social');

  state.charts.assoc?.destroy();
  state.charts.assoc = new Chart($('#assoc-chart'), {
    type: 'bar',
    data: {
      labels: sorted.map((r) => NICE[r.feature] || r.feature),
      datasets: [{
        data: sorted.map((r) => r[val]),
        backgroundColor: sorted.map((r) => (isSocial(r) ? '#FFC94A' : '#3A5567')),
        borderRadius: 2, barPercentage: 0.78,
      }],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: 'strength of association', color: t.soft },
             grid: { color: t.grid }, border: { color: t.grid } },
        y: { grid: { display: false }, border: { color: t.grid }, ticks: { color: t.ink } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => fmt(c.parsed.x, 2),
            afterLabel: (c) => {
              const r = sorted[c.dataIndex];
              return [isSocial(r) ? 'social variable' : 'physical control',
                      r.direction || ''].filter(Boolean);
            },
          },
        },
      },
    },
  });

  const cv = state.cv[outcome] || [];
  const NICE_MODEL = { ridge_splines: 'Ridge with splines', random_forest: 'Random forest', xgboost: 'Gradient boosting' };
  $('#assoc-cv').innerHTML =
    `<p class="note">Gold bars are the social variables being read; slate bars are
     the physical controls. Hover a bar for the direction of the relationship.</p>` +
    (cv.length ? `<h3>Is the fitted surface steady enough to read?</h3>
      <div class="table-wrap">${tableHTML(
        cv.map((r) => ({ ...r, model: NICE_MODEL[r.model] || r.model })), [
        ['model', 'Model'], ['r2', 'R², spatial folds'],
        ['r2_random_split', 'R², random split'],
        ['r2_optimism_from_random_split', 'Inflation a random split would add'],
        ['rmse', 'RMSE'], ['mae', 'MAE']])}</div>
      <p class="note" style="margin-top:12px">The gap between the two R² columns is
      spatial leakage a random split would have hidden: neighbouring tracts are
      near-copies, so a model that memorises a neighbourhood scores well without
      generalising. These figures only check that the surface is steady enough to
      interpret. They are not the result.</p>` : '');
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
  document.querySelectorAll('.rail-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.rail-tab').forEach((b) =>
        b.setAttribute('aria-selected', String(b === btn)));
      document.querySelectorAll('.view').forEach((v) =>
        v.classList.toggle('hidden', v.id !== `view-${btn.dataset.view}`));
      setTimeout(() => {
        const v = btn.dataset.view;
        if (v === 'map') state.map?.invalidateSize();
        if (v === 'optimizer' && state.map2) {
          // The container had no size while hidden, so Leaflet's first
          // fitBounds landed on a single polygon. Re-fit on first reveal.
          state.map2.invalidateSize();
          if (!state.map2Fitted && state.tractLayer2) {
            state.map2.fitBounds(state.tractLayer2.getBounds(), { padding: [12, 12] });
            state.map2Fitted = true;
          }
        }
        if (v === 'budget') drawBudget();
        if (v === 'association') drawAssociation();
      }, 30);
    });
  });
}

function renderMethods() {
  const m = state.meta;
  $('#methods-body').innerHTML = `
    <h2>How this was put together</h2>
    <p>Two questions about Los Angeles County, answered for each of its
    ${fmtInt(m.n_tracts)} census tracts and ${fmtInt(m.total_population)} residents:
    which places are most exposed to extreme heat, and where a limited number of
    new public cooling centres would reach the most vulnerable people.</p>

    <h3>The vulnerability index</h3>
    <p>A tract's score is the average of its percentile rank on four measures,
    one for each way heat causes harm: peak summer surface temperature for
    exposure, the share of residents aged 65 and over for sensitivity, and the
    poverty rate and the share without tree canopy for the ability to cope.
    Percentile ranks rather than standardised scores, because the four measures
    have incompatible units and one extremely hot tract would otherwise stretch
    the whole index.</p>

    <h3>Who the existing centres serve</h3>
    <p>For each measure, two distributions are held side by side: all
    ${fmtInt(m.n_tracts)} tracts, and only those within reach of one of the
    ${fmtInt(m.n_existing_centers)} centres operating today. The difference
    between them is measured with a standardised mean difference and a
    Kolmogorov–Smirnov statistic rather than read off a histogram.</p>

    <h3>Where new centres should go</h3>
    <p>A maximum-coverage siting problem. Candidate sites are tract centres; a
    site covers every tract whose centre falls within the service radius; K
    sites are chosen to maximise the benefit covered. Greedy selection is
    guaranteed to land within about 63% of the best possible answer because
    coverage is submodular, and an integer program finds the exact optimum, so
    the real gap can be reported rather than the worst case. What a run
    maximises is deliberately kept apart from what it is judged on: every
    solution is scored on every measure, including coverage group by group.</p>

    <h3>Reading relationships, not predicting them</h3>
    <p>Training a model to predict the index from variables correlated with its
    own inputs would only relearn the formula. Instead the physical character of
    a place is held as a control and the social variables are the ones being
    read, with the ranking taken from SHAP values and accumulated local effects.
    Cross-validation holds out whole regions at a time, because neighbouring
    tracts are near-copies of each other.</p>

    <h3>This run</h3>
    <ul>
      <li>Data: <code>${m.data_mode}</code></li>
      <li>Temperature source: <code>${m.lst_source}</code></li>
      <li>Service radius: ${m.radius_default_m} m by default, also run at ${m.radius_grid_m.join(' m, ')} m</li>
      <li>Budgets: ${m.k_grid.join(', ')} new centres</li>
    </ul>
    ${m.data_mode === 'mock' ? `<p><strong>This run uses synthetic data.</strong>
      The figures here describe a simulated county built so the pipeline could be
      checked end to end before the last real inputs landed. They are not
      findings about Los Angeles. Everything regenerates against real data from
      one setting.</p>` : ''}

    <h3>Where the data comes from, and from when</h3>
    ${m.vintages_markdown ? markdownish(m.vintages_markdown) : '<p>See <code>data/vintages.md</code>.</p>'}`;
}

/* A deliberately small Markdown renderer. It only ever receives
 * data/vintages.md, which uses headings, tables, lists, bold and code. */
function markdownish(md) {
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>')
    .replace(/&lt;(https?:\/\/[^&]+)&gt;/g, '<a href="$1" rel="noopener noreferrer" target="_blank">$1</a>');
  const cells = (r) => r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
  const renderTable = (t) => {
    const [head, , ...rows] = t;
    return `<div class="table-scroll"><table><thead><tr>${cells(head).map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead>`
      + `<tbody>${rows.map((r) => `<tr>${cells(r).map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  };

  const out = [];
  let table = null, list = null, para = [];
  const flushPara = () => {
    if (para.length) { out.push(`<p>${inline(para.join(' '))}</p>`); para = []; }
  };
  const flushList = () => { if (list) { out.push(`<ul>${list.join('')}</ul>`); list = null; } };
  const flushTable = () => { if (table) { out.push(renderTable(table)); table = null; } };

  for (const raw of md.split('\n')) {
    const line = raw.trim();

    if (/^\|.*\|$/.test(line)) { flushPara(); flushList(); (table ||= []).push(line); continue; }
    flushTable();

    if (/^-\s+/.test(line)) {
      flushPara();
      (list ||= []).push(`<li>${inline(line.replace(/^-\s+/, ''))}</li>`);
      continue;
    }

    if (/^#{1,4}\s/.test(line)) {
      flushPara(); flushList();
      const depth = line.match(/^#+/)[0].length;
      // The file's own H1 duplicates the heading this section already has.
      if (depth > 1) {
        out.push(`<h${Math.min(depth + 1, 4)}>${inline(line.replace(/^#+\s/, ''))}</h${Math.min(depth + 1, 4)}>`);
      }
      continue;
    }

    // A blank line ends a paragraph; otherwise wrapped source lines are one.
    if (!line) { flushPara(); flushList(); continue; }
    para.push(line);
  }
  flushPara(); flushTable(); flushList();
  return out.join('\n');
}

async function init() {
  wireTabs();

  const [meta, tracts] = await Promise.all([getJSON('meta.json'), getJSON('tracts.geojson')]);
  state.meta = meta;
  state.tracts = tracts;
  state.centers = (await tryJSON('centers_existing.json')) || [];
  state.grid = (await tryJSON('partC_results_grid.json')) || [];
  state.solutions = (await tryJSON('partC_solutions.json')) || {};
  state.shap.hvi = (await tryJSON('partB_assoc_hvi_shap.json'))
    || (await tryJSON('partB_assoc_hvi_importance.json')) || [];
  state.shap.heat_er_rate_per100k = (await tryJSON('partB_assoc_heat_er_rate_per100k_shap.json')) || [];
  const assoc = (await tryJSON('partB_association.json')) || {};
  for (const k of Object.keys(assoc)) state.cv[k] = assoc[k].cv || [];
  state.validation = (await tryJSON('partB_hvi_validation.json')) || [];
  state.headline = (await tryJSON('partC_headline.json')) || [];

  $('#rail-mode').innerHTML = meta.data_mode === 'mock'
    ? `<span class="flag">Synthetic data.</span>Not findings about Los Angeles; see Method.`
    : `${fmtInt(meta.n_tracts)} tracts<br>${fmtInt(meta.n_existing_centers)} centres today`;
  $('#provenance').textContent = meta.data_mode === 'mock'
    ? 'Simulated county, built so the pipeline could be verified end to end. Switch the data source and every figure here regenerates.'
    : `Census tracts, Landsat thermal imagery, CalEnviroScreen and the county's own cooling-centre register.`;

  // --- exposure
  state.map = baseMap('map');
  drawTracts();
  drawCenters();
  state.map.fitBounds(state.tractLayer.getBounds(), { padding: [12, 12] });

  $('#layer-select').addEventListener('change', (e) => { state.layer = e.target.value; drawTracts(); });
  $('#chk-unserved').addEventListener('change', drawTracts);
  $('#chk-centers').addEventListener('change', drawCenters);
  $('#chk-buffers').addEventListener('change', drawCenters);
  $('#radius-map').addEventListener('input', (e) => {
    state.radiusMap = Number(e.target.value);
    $('#radius-map-out').textContent = `${(state.radiusMap / 1000).toFixed(1)} km`;
    drawCenters();
    updateMapStats();
  });

  // --- siting
  const radii = [...new Set(state.grid.map((r) => Number(r.radius_m)))].filter(Boolean).sort((a, b) => a - b);
  const RADIUS_NAME = { 1609: '1 mile, a short walk', 2000: '2 km', 3219: '2 miles' };
  $('#opt-radius').innerHTML = radii.map((r) =>
    `<option value="${r}" ${r === meta.radius_default_m ? 'selected' : ''}>${RADIUS_NAME[r] || `${r} m`}</option>`).join('');

  const ks = [...new Set(state.grid.filter((r) => r.k > 0).map((r) => Number(r.k)))].sort((a, b) => a - b);
  if (ks.length) {
    const el = $('#opt-k');
    el.min = ks[0];
    el.max = ks[ks.length - 1];
    el.step = ks.length > 1 ? ks[1] - ks[0] : 5;
    el.value = ks.includes(meta.k_default) ? meta.k_default : ks[0];
  }

  state.map2 = baseMap('map2');
  state.tractLayer2 = L.geoJSON(state.tracts, { style: styleFor('hvi', domain('hvi'), false) }).addTo(state.map2);
  if (state.centers.length) {
    L.layerGroup(state.centers.map((c) => L.circleMarker([c.lat, c.lon], {
      radius: 2.4, color: '#DEE8F0', weight: 0.7, fillColor: '#8DA2B3', fillOpacity: 0.9,
    }).bindTooltip(`<span class="tt-head">Existing centre</span>${c.name || c.center_id}`))).addTo(state.map2);
  }
  ['#opt-method', '#opt-objective', '#opt-radius', '#opt-k'].forEach((s) =>
    $(s).addEventListener('input', drawOptimizer));
  drawOptimizer();

  // --- budget
  $('#budget-metric').addEventListener('change', drawBudget);
  const METHOD_NAME = {
    existing_only: 'Centres today', greedy: 'Greedy', ilp: 'Exact optimum',
    sort_by_hvi: 'Ranked by vulnerability', sort_by_ces: 'Ranked by CalEnviroScreen',
    sort_by_svi: 'Ranked by social vulnerability', hottest_tracts: 'Hottest tracts',
    most_populous: 'Most populous tracts', random: 'Placed at random',
  };
  const OBJ_NAME = { pop_x_hvi: 'people × vulnerability', count: 'tracts covered', '-': '' };
  if (state.headline.length) {
    $('#headline-table').innerHTML = tableHTML(
      state.headline.map((r) => ({
        ...r,
        method: METHOD_NAME[r.method] || r.method,
        objective: OBJ_NAME[r.objective] ?? r.objective,
      })), [
      ['method', 'Method'], ['objective', 'Maximises'], ['k', 'Centres'],
      ['pop_covered_pct', 'All residents %'],
      ['vuln_weighted_pop_covered_pct', 'Weighted by vulnerability %'],
      ['top25_hvi_pop_covered_pct', 'Most vulnerable quarter %'],
      ['hvi_coverage_gap_pp', 'Gap, most vs least vulnerable'],
      ['vuln_weighted_pop_covered_pct_vs_random_pp', 'Against random'],
      ['fair_age_65_plus', 'Aged 65+ %'], ['fair_under_5', 'Under 5 %'],
      ['fair_below_poverty', 'Below poverty %']]);
  }

  // --- drivers
  $('#assoc-outcome').addEventListener('change', drawAssociation);
  if (state.validation.length) {
    $('#validation-table').innerHTML = tableHTML(state.validation, [
      ['comparison', 'Compared with'], ['spearman_rho', 'Rank correlation'],
      ['p_value', 'p'], ['n', 'Tracts'], ['top10_overlap', 'Agreement on the worst 10%']]) +
      `<p class="note" style="margin-top:12px">Emergency-visit rates are published by
      ZIP code and shared out to tracts by population, so every tract inside one ZIP
      carries the same value: that correlation is weakened and partly mechanical, and
      is corroboration rather than a test. Partial agreement with the federal social
      vulnerability index is the wanted result — identical rankings would mean this
      index adds nothing, and no agreement would mean its social inputs are
      misbehaving.</p>`;
  }

  renderMethods();
}

init().catch((err) => {
  $('#main').insertAdjacentHTML('afterbegin',
    `<div class="wide"><h2>The data did not load</h2>
     <p class="note">${err.message}. Run <code>make mock</code>, or
     <code>make real</code>, to rebuild <code>dashboard/public/data</code>.</p></div>`);
});
