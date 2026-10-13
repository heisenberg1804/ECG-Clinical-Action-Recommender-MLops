// ECG Reading Practice: learner UI (D-53, D-55).
// Preact + htm and uPlot are vendored; there is no build step.
import { html, render, useEffect, useRef, useState } from "./vendor/htm-preact-standalone-3.1.1.js";
import uPlot from "./vendor/uPlot-1.6.31.esm.js";

// Standard 12-lead printout: each column is the next 2.5 s of the recording
const LAYOUT = [
  ["I", "aVR", "V1", "V4"],
  ["II", "aVL", "V2", "V5"],
  ["III", "aVF", "V3", "V6"],
];
const WINDOW_S = 2.5;
const MV_RANGE = [-1.5, 1.5];        // 3 mV tall rows
const MM_PER_S = 25, MM_PER_MV = 10;  // Standard paper speed and gain

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

async function api(path, options) {
  const r = await fetch(path, options);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${r.status} ${r.statusText}`);
  return body;
}

const store = {  // Per-viewer convenience only; the page works without it
  get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ignore */ } },
};

// ECG paper: 1 mm minor squares (0.04 s, 0.1 mV) and 5 mm major squares (0.2 s, 0.5 mV)
function drawPaper(u) {
  const { ctx } = u, { left, top, width, height } = u.bbox;
  const [t0, t1] = [u.scales.x.min, u.scales.x.max];
  ctx.save();
  ctx.fillStyle = css("--paper");
  ctx.fillRect(left, top, width, height);
  const line = (x0, y0, x1, y1) => { ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); };
  for (const [step_s, step_mv, color, w] of [[0.04, 0.1, "--grid-minor", 1], [0.2, 0.5, "--grid-major", 1.2]]) {
    ctx.strokeStyle = css(color);
    ctx.lineWidth = w * devicePixelRatio;
    for (let t = Math.ceil(t0 / step_s) * step_s; t <= t1 + 1e-9; t += step_s) {
      const x = u.valToPos(t, "x", true);
      line(x, top, x, top + height);
    }
    for (let v = MV_RANGE[0]; v <= MV_RANGE[1] + 1e-9; v += step_mv) {
      const y = u.valToPos(v, "y", true);
      line(left, y, left + width, y);
    }
  }
  ctx.restore();
}

function Trace({ times, values, t0, t1, width, label }) {
  const el = useRef(null);
  useEffect(() => {
    if (!width) return;
    const pxPerMm = width / ((t1 - t0) * MM_PER_S);
    const height = Math.round((MV_RANGE[1] - MV_RANGE[0]) * MM_PER_MV * pxPerMm);
    const plot = new uPlot({
      width, height,
      legend: { show: false }, cursor: { show: false },
      scales: { x: { time: false, range: [t0, t1] }, y: { range: MV_RANGE } },
      axes: [{ show: false }, { show: false }],
      series: [{}, { stroke: css("--trace"), width: 1.3, points: { show: false } }],
      hooks: { drawClear: [drawPaper] },
    }, [times, values], el.current);
    return () => plot.destroy();
  }, [times, values, t0, t1, width]);
  return html`<div class="lead"><span class="name">${label}</span><div ref=${el}></div></div>`;
}

function EcgSheet({ ecg }) {
  const box = useRef(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const fs = ecg.sampling_rate, n = ecg.signal_mv[0].length;
  const times = Array.from({ length: n }, (_, i) => i / fs);
  const lead = (name) => ecg.signal_mv[ecg.leads.indexOf(name)];
  const col = Math.floor(Math.max(width, 720) / 4);  // Matches the sheet's min-width (CSS)
  const slice = (arr, c) => arr.slice(Math.round(c * WINDOW_S * fs), Math.round((c + 1) * WINDOW_S * fs));

  return html`
    <div class="sheet" ref=${box}>
      ${LAYOUT.map((row) => html`
        <div class="grid4">
          ${row.map((name, c) => html`
            <${Trace} label=${name} width=${col}
              times=${slice(times, c)} values=${slice(lead(name), c)}
              t0=${c * WINDOW_S} t1=${(c + 1) * WINDOW_S} />`)}
        </div>`)}
      <div class="rhythm">
        <${Trace} label="II (rhythm)" width=${col * 4} times=${times} values=${lead("II")}
          t0=${0} t1=${n / fs} />
      </div>
      <div class="scale-note">25 mm/s · 10 mm/mV · small square 0.04 s × 0.1 mV</div>
    </div>`;
}

function App() {
  const [cases, setCases] = useState(null);
  const [idx, setIdx] = useState(store.get("ecg.caseIndex", 0));
  const [ecg, setEcg] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => { api("/cases").then(setCases).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    if (!cases) return;
    const i = Math.min(idx, cases.cases.length - 1);
    store.set("ecg.caseIndex", i);
    setEcg(null);
    api(`/cases/${cases.cases[i].case_id}`).then(setEcg).catch((e) => setError(e.message));
  }, [cases, idx]);

  if (error) return html`<${Shell}><div class="error">${error}</div><//>`;
  if (!cases) return html`<${Shell}><p class="muted">Loading cases…</p><//>`;
  const c = cases.cases[Math.min(idx, cases.cases.length - 1)];
  return html`
    <${Shell}>
      <div class="casebar">
        <span class="title">Case ${idx + 1} of ${cases.n_cases}</span>
        <span class="meta">${c.age ? `${c.age} y` : "age unknown"}, ${c.sex === "M" ? "male" : "female"}</span>
        <span class="spacer"></span>
        <button disabled=${idx === 0} onClick=${() => setIdx(idx - 1)}>← Previous</button>
        <button disabled=${idx >= cases.n_cases - 1} onClick=${() => setIdx(idx + 1)}>Next →</button>
      </div>
      ${ecg ? html`<${EcgSheet} ecg=${ecg} />` : html`<p class="muted">Loading ECG…</p>`}
    <//>`;
}

function Shell({ children }) {
  return html`
    <header class="top">
      <h1>ECG Reading Practice</h1>
      <span class="tag">Real 12-lead ECGs (PTB-XL) with an AI second opinion</span>
    </header>
    <main>${children}</main>
    <footer class="disclaimer">
      Educational use only. Not a medical device and not for patient care. Cases come from the
      PTB-XL test set, which the model never saw during training.
    </footer>`;
}

const root = document.getElementById("app");
root.replaceChildren();  // Drop the static "Loading…" placeholder: render() appends otherwise
render(html`<${App} />`, root);
