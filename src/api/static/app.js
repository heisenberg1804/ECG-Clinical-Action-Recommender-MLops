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
const CLASSES = [
  ["NORM", "Normal ECG"],
  ["MI", "Myocardial infarction"],
  ["STTC", "ST/T change"],
  ["CD", "Conduction disturbance"],
  ["HYP", "Hypertrophy"],
];
const NAME = Object.fromEntries(CLASSES);

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

// Model attention for this lead, shaded behind the trace: one bar per heatmap sample
function drawAttention(u, heat, heatFs, t0) {
  if (!heat) return;
  const { ctx } = u, { top, height } = u.bbox, dt = 1 / heatFs;
  ctx.save();
  ctx.fillStyle = css("--accent");
  heat.forEach((v, i) => {
    if (v < 0.15) return;  // Keep low-attention regions clean
    const x0 = u.valToPos(t0 + i * dt, "x", true), x1 = u.valToPos(t0 + (i + 1) * dt, "x", true);
    ctx.globalAlpha = 0.45 * v;
    ctx.fillRect(x0, top, x1 - x0 + 0.5, height);
  });
  ctx.restore();
}

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

function Trace({ times, values, t0, t1, width, label, heat, heatFs }) {
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
      hooks: { drawClear: [drawPaper, (u) => drawAttention(u, heat, heatFs, t0)] },
    }, [times, values], el.current);
    return () => plot.destroy();
  }, [times, values, t0, t1, width, heat]);
  return html`<div class="lead"><span class="name">${label}</span><div ref=${el}></div></div>`;
}

function EcgSheet({ ecg, attention }) {
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
  const hfs = attention?.sampling_rate;
  const heat = (name, c) => {
    if (!attention) return null;
    const row = attention.heatmap[ecg.leads.indexOf(name)];
    return c === null ? row : row.slice(Math.round(c * WINDOW_S * hfs), Math.round((c + 1) * WINDOW_S * hfs));
  };

  return html`
    <div class="sheet" ref=${box}>
      ${LAYOUT.map((row) => html`
        <div class="grid4">
          ${row.map((name, c) => html`
            <${Trace} label=${name} width=${col}
              times=${slice(times, c)} values=${slice(lead(name), c)}
              t0=${c * WINDOW_S} t1=${(c + 1) * WINDOW_S}
              heat=${heat(name, c)} heatFs=${hfs} />`)}
        </div>`)}
      <div class="rhythm">
        <${Trace} label="II (rhythm)" width=${col * 4} times=${times} values=${lead("II")}
          t0=${0} t1=${n / fs} heat=${heat("II", null)} heatFs=${hfs} />
      </div>
      <div class="scale-note">
        25 mm/s · 10 mm/mV · small square 0.04 s × 0.1 mV
        ${attention && html` · <span class="attn-key"></span> model attention for ${NAME[attention.diagnosis]}`}
      </div>
    </div>`;
}

function ReadPanel({ answer, setAnswer, onReveal, busy }) {
  const toggle = (c) => setAnswer(answer.includes(c) ? answer.filter((x) => x !== c) : [...answer, c]);
  return html`
    <section class="panel">
      <h2>Your read</h2>
      <p class="muted">Select every category you see, then reveal the expert label and the model.</p>
      <div class="chips">
        ${CLASSES.map(([c, name]) => html`
          <button class=${"chip" + (answer.includes(c) ? " on" : "")} aria-pressed=${answer.includes(c)}
            onClick=${() => toggle(c)}><b>${c}</b> ${name}</button>`)}
      </div>
      <button class="primary" disabled=${!answer.length || busy} onClick=${onReveal}>Reveal</button>
    </section>`;
}

function ProbBar({ c, p, threshold, agree }) {
  return html`
    <div class="prob">
      <span class="cls" title=${NAME[c]}>${c}</span>
      <span class="bar"><span class="fill" style=${`width:${p * 100}%`}></span>
        <span class="thr" style=${`left:${threshold * 100}%`} title=${`threshold ${threshold}`}></span></span>
      <span class="pct">${Math.round(p * 100)}%</span>
      <span class=${agree ? "ok" : "bad"}>${agree ? "✓" : "✗"}</span>
    </div>`;
}

function ResultPanel({ result, thresholds, focus, setFocus }) {
  const exact = result.student_answer.slice().sort().join() === result.labels.slice().sort().join();
  const m = result.model;
  const flags = Object.entries(result.quality_flags);
  return html`
    <section class="panel">
      <h2>${exact ? "Exact match" : "Compare your read"}</h2>
      <div class="cols">
        <div>
          <h3>Cardiologist</h3>
          <ul class="labels">
            ${result.labels.map((c) => html`
              <li><b>${c}</b> ${NAME[c]} <span class="muted">· confidence ${result.label_likelihoods[c] ?? "n/a"}%</span></li>`)}
          </ul>
          <h3>You</h3>
          <ul class="labels">
            ${CLASSES.map(([c]) => c).filter((c) => result.student_answer.includes(c) || result.labels.includes(c)).map((c) => html`
              <li><span class=${"mark " + (result.agreement[c].student ? "ok" : "bad")}>${result.agreement[c].student ? "✓" : "✗"}</span>
                <b>${c}</b> ${result.student_answer.includes(c) ? "selected" : "missed"}</li>`)}
          </ul>
          ${result.report && html`<h3>Original report <span class="muted">(German, as written)</span></h3>
            <p class="report">${result.report.replace(/\s+/g, " ").trim().toLowerCase()}</p>`}
          ${flags.length > 0 && html`<h3>Recording notes</h3>
            <p class="muted">${flags.map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ")}</p>`}
        </div>
        <div>
          <h3>Model <span class="muted">(✓ = agrees with the cardiologist)</span></h3>
          ${CLASSES.map(([c]) => html`<${ProbBar} c=${c} p=${m.probabilities[c]}
            threshold=${thresholds[c]} agree=${result.agreement[c].model} />`)}
          <p class="muted small">Marker on each bar = the model's decision threshold for that class.</p>
          <h3>Where the model looked</h3>
          <div class="chips">
            ${CLASSES.map(([c]) => html`<button class=${"chip small" + (focus === c ? " on" : "")}
              onClick=${() => setFocus(c)}>${c}</button>`)}
          </div>
          ${focus && html`<p class="small">${m.explanations[focus].description}</p>`}
        </div>
      </div>
    </section>`;
}

const pct = (x) => (x * 100).toFixed(1);
const GROUPS = [["sex_male", "Male"], ["sex_female", "Female"], ["age_lt40", "Age < 40"],
                ["age_40to65", "Age 40–65"], ["age_gt65", "Age > 65"]];

function ModelCard({ card }) {
  const e = card.evaluation;
  const short = (v) => (v ? String(v).slice(0, 12) : "n/a");
  return html`
    <details class="panel card">
      <summary><h2>About the model</h2>
        <span class="muted">${card.model_version} · test macro AUC ${e.test_macro_auc.toFixed(3)}</span></summary>
      <p class="muted small">${card.architecture}. Evaluated on ${e.split}.</p>
      <div class="cols">
        <div>
          <h3>Per class (test fold)</h3>
          <table class="metrics">
            <thead><tr><th></th><th>AUC</th><th>Sensitivity</th><th>Specificity</th><th>Threshold</th><th>ECE</th></tr></thead>
            <tbody>${CLASSES.map(([c, name]) => html`
              <tr><th title=${name}>${c}</th>
                <td>${e.test_per_class_auc[c].toFixed(3)}</td>
                <td>${pct(e.test_at_threshold[c].sensitivity)}%</td>
                <td>${pct(e.test_at_threshold[c].specificity)}%</td>
                <td>${card.thresholds[c].toFixed(2)}</td>
                <td>${e.test_ece[c].toFixed(3)}</td></tr>`)}</tbody>
          </table>
          <p class="muted small">AUC ranks positives above negatives (1.0 is perfect). Sensitivity and
            specificity are at the shown thresholds. ECE is calibration error: lower means the
            percentages mean what they say.</p>
        </div>
        <div>
          <h3>By patient group (macro AUC)</h3>
          <table class="metrics">
            <tbody>${GROUPS.filter(([k]) => k in e.test_subgroup_auc).map(([k, label]) => html`
              <tr><th>${label}</th><td>${e.test_subgroup_auc[k].toFixed(3)}</td></tr>`)}</tbody>
          </table>
          <h3>Limitations</h3>
          <ul class="small">${card.limitations.map((l) => html`<li>${l}</li>`)}</ul>
          <h3>Lineage</h3>
          <p class="small mono">${`git ${short(card.lineage.git_commit)} · data ${short(card.lineage.data_dvc_md5)} · MLflow run ${short(card.lineage.mlflow_run_id)}`}</p>
          ${card.case_bank && html`<p class="muted small">${`${card.case_bank.n_cases} practice cases from ${card.case_bank.source}, built ${card.case_bank.built_at.slice(0, 10)}.`}</p>`}
        </div>
      </div>
    </details>`;
}

function App() {
  const [cases, setCases] = useState(null);
  const [idx, setIdx] = useState(store.get("ecg.caseIndex", 0));
  const [ecg, setEcg] = useState(null);
  const [error, setError] = useState(null);
  const [answer, setAnswer] = useState([]);
  const [result, setResult] = useState(null);
  const [focus, setFocus] = useState(null);
  const [attention, setAttention] = useState(null);
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState(null);
  const [score, setScore] = useState(store.get("ecg.score", {}));  // case_id -> exact match?

  useEffect(() => { api("/model/card").then(setCard).catch(() => {}); }, []);

  useEffect(() => { api("/cases").then(setCases).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    if (!cases) return;
    const i = Math.min(idx, cases.cases.length - 1);
    store.set("ecg.caseIndex", i);
    setEcg(null); setResult(null); setFocus(null); setAttention(null);
    const id = cases.cases[i].case_id;
    setAnswer(store.get(`ecg.answer.${id}`, []));
    api(`/cases/${id}`).then(setEcg).catch((e) => setError(e.message));
  }, [cases, idx]);

  useEffect(() => {
    if (!result || !focus) { setAttention(null); return; }
    api(`/cases/${result.case_id}/explanation/${focus}`).then(setAttention).catch(() => setAttention(null));
  }, [result, focus]);

  const reveal = async () => {
    setBusy(true);
    try {
      const r = await api(`/cases/${ecg.case_id}/reveal`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer }),
      });
      setResult(r);
      setFocus(r.model.predicted[0] || r.primary_label);  // Start where the model was most sure
      store.set(`ecg.answer.${ecg.case_id}`, answer);
      if (!(ecg.case_id in score)) {  // Score each case once: the first committed read counts
        const exact = r.student_answer.slice().sort().join() === r.labels.slice().sort().join();
        const next = { ...score, [ecg.case_id]: exact };
        setScore(next); store.set("ecg.score", next);
      }
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  if (error) return html`<${Shell}><div class="error">${error}</div><//>`;
  if (!cases) return html`<${Shell}><p class="muted">Loading cases…</p><//>`;
  const c = cases.cases[Math.min(idx, cases.cases.length - 1)];
  return html`
    <${Shell}>
      <div class="casebar">
        <span class="title">Case ${idx + 1} of ${cases.n_cases}</span>
        <span class="meta">${c.age ? `${c.age} y` : "age unknown"}, ${c.sex === "M" ? "male" : "female"}</span>
        <span class="spacer"></span>
        <span class="meta">Score ${Object.values(score).filter(Boolean).length} / ${Object.keys(score).length}</span>
        <button disabled=${idx === 0} onClick=${() => setIdx(idx - 1)}>← Previous</button>
        <button disabled=${idx >= cases.n_cases - 1} onClick=${() => setIdx(idx + 1)}>Next →</button>
      </div>
      ${ecg ? html`<${EcgSheet} ecg=${ecg} attention=${attention} />` : html`<p class="muted">Loading ECG…</p>`}
      ${ecg && !result && html`<${ReadPanel} answer=${answer} setAnswer=${setAnswer} onReveal=${reveal} busy=${busy} />`}
      ${result && card && html`<${ResultPanel} result=${result} thresholds=${card.thresholds}
        focus=${focus} setFocus=${setFocus} />`}
      ${card && html`<${ModelCard} card=${card} />`}
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
