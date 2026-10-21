// TA dashboard: live counters, help queue (Super's summaries), class heatmap (+ attempt timeline drawer),
// step insights and the end-of-class report from Nemotron Ultra.
import { $, api, defaultConnection, el, fmtSeconds, icon, initTopbar, store, timeAgo, toast } from "./ui.js";
import { connectEvents } from "./ws.js";

initTopbar();
defaultConnection();

let labId = null;
let steps = [];
let refreshTimer = null;
const soundBox = $("#set-sound");
soundBox.checked = store.get("polarity.sound", "1") === "1";
soundBox.addEventListener("change", () => store.set("polarity.sound", soundBox.checked ? "1" : "0"));

const TRIGGER = {
  fix_count: "3+ FIX verdicts on this step", uncertain_streak: "3 CAN'T TELL in a row", power_test: "Power test failed twice",
  safety: "Safety concern", call_ta: "Student pressed Call TA",
};
const STATE_TEXT = {
  not_started: "Not started", in_progress: "In progress", passed_first: "Passed first try", passed_after: "Passed after fixes",
  struggling: "Struggling (2+ fixes)", stuck: "Stuck (3+ fixes or waiting for help)",
};

function chime() {
  if (!soundBox.checked) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const now = ctx.currentTime;
    for (const [i, f] of [660, 880].entries()) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = f;
      gain.gain.setValueAtTime(0.0001, now + i * 0.16);
      gain.gain.exponentialRampToValueAtTime(0.08, now + i * 0.16 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.16 + 0.22);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + i * 0.16);
      osc.stop(now + i * 0.16 + 0.25);
    }
    setTimeout(() => ctx.close(), 800);
  } catch (e) { /* audio blocked until the first click */ }
}

// ── data loading ──────────────────────────────────────────────────────────────────────────────
async function loadAll() {
  const q = labId ? `?lab_id=${encodeURIComponent(labId)}` : "";
  const [ov, hm, hq] = await Promise.all([api(`/api/ta/overview${q}`), api(`/api/ta/heatmap${q}`), api("/api/ta/help")]);
  if (ov.status === 401) { location.reload(); return; }
  if (ov.ok) renderOverview(ov.data);
  if (hm.ok) renderHeatmap(hm.data);
  if (hq.ok) renderHelp(hq.data.items);
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(loadAll, 700);
}

// ── overview + insights ───────────────────────────────────────────────────────────────────────
function renderOverview(o) {
  labId = o.lab.id;
  steps = o.lab.steps;
  $("#tb-sub").textContent = o.lab.title;
  $("#t-active").textContent = String(o.active_benches);
  $("#t-done").replaceChildren(document.createTextNode(String(o.completed)), el("small", { text: ` of ${o.sessions}` }));
  $("#t-help").textContent = String(o.waiting_for_help);
  $("#t-median").textContent = o.median_step_seconds === null ? "–" : fmtSeconds(o.median_step_seconds);
  $("#sim-banner").hidden = !o.simulated;
  $("#seed-btn").hidden = o.sessions > 0;
  $("#clear-sim-btn").hidden = !o.simulated;
  const labs = o.labs_with_data || [];
  const pickWrap = $("#lab-pick-wrap");
  pickWrap.hidden = labs.length < 2;
  if (labs.length >= 2) {
    const pick = $("#lab-pick");
    pick.replaceChildren(...labs.map((id) => el("option", { value: id, text: id, selected: id === labId })));
  }
  const box = $("#insights");
  if (!o.sessions) {
    box.replaceChildren(el("p", { class: "muted", text: "Insights appear once students start checking steps." }));
    return;
  }
  box.replaceChildren(...o.insights.map((s, i) => {
    const pct = s.first_try_pass_pct;
    return el("article", { class: "card insight" },
      el("h3", {}, el("span", { text: `${i + 1}. ${s.title}` }), el("span", { class: "muted", text: pct === null ? "no checks yet" : `${pct}% first try` })),
      el("div", { class: "bar", role: "img", "aria-label": `First-try pass rate ${pct === null ? "not available" : pct + "%"}` }, el("i", { style: `width:${pct || 0}%` })),
      el("div", { class: "kv" }, el("span", { text: "Median attempts to pass" }), el("strong", { text: s.median_attempts === null ? "–" : String(s.median_attempts) })),
      el("div", { class: "kv" }, el("span", { text: "Can't-tell rate" }), el("strong", { text: s.uncertain_rate_pct === null ? "–" : `${s.uncertain_rate_pct}%` })),
      s.top_errors.length ? el("ul", { class: "errs", "aria-label": "Most common mistakes" }, ...s.top_errors.map((e) =>
        el("li", {}, el("span", { text: e.label }), el("span", { class: "count", text: `×${e.count}` })))) : null);
  }));
}

// ── help queue ────────────────────────────────────────────────────────────────────────────────
let knownHelp = new Set();
function renderHelp(items) {
  const box = $("#helpq");
  $("#hq-count").textContent = items.length ? `${items.length} waiting` : "";
  const fresh = items.filter((h) => !knownHelp.has(h.id));
  if (knownHelp.size && fresh.length) chime();
  knownHelp = new Set(items.map((h) => h.id));
  if (!items.length) {
    box.replaceChildren(el("div", { class: "empty" }, icon("pass"), el("strong", { text: "Nobody is waiting" }), el("span", { text: "New help requests appear here with an AI summary." })));
    return;
  }
  items.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  box.replaceChildren(...items.map((h) => {
    const sum = h.summary || null;
    const urgency = (sum && sum.urgency) || (h.trigger === "safety" || h.trigger === "power_test" ? "high" : "medium");
    const summary = sum ? el("p", { class: "summary", text: sum.summary_for_ta }) :
      el("div", { class: "stack", style: "gap:6px" }, el("div", { class: "skeleton sk-line", style: "width:90%" }), el("span", { class: "muted", style: "font-size:13px", text: "Summarising with Nemotron Super…" }));
    return el("article", { class: `card hcard u-${urgency}`, dataset: { id: h.id } },
      el("div", { class: "hcard__top" },
        el("span", { class: "hcard__who", text: h.alias }), h.bench_id ? el("span", { text: `· Bench ${h.bench_id}` }) : null,
        el("span", { text: `· ${h.step_title}` }), el("div", { class: "spacer" }), el("span", { class: "wait", dataset: { since: h.created_at }, text: timeAgo(h.created_at) })),
      el("div", { class: "row wrap", style: "gap:8px" },
        el("span", { class: `urg u-${urgency}` }, urgency === "high" ? icon("fix") : icon("bell"), el("span", { text: urgency })),
        el("span", { class: "muted", style: "font-size:13px", text: TRIGGER[h.trigger] || h.trigger }),
        h.is_simulated ? el("span", { class: "sim-tag", text: "simulated" }) : null),
      el("div", { class: "hcard__body" },
        el("div", { class: "stack", style: "gap:6px" }, summary,
          sum && sum.likely_root_cause ? el("p", { class: "action" }, el("strong", { text: "Likely cause: " }), sum.likely_root_cause) : null,
          sum && sum.suggested_ta_action ? el("p", { class: "action" }, el("strong", { text: "Suggested: " }), sum.suggested_ta_action) : null),
        h.thumb ? el("img", { src: h.thumb, alt: `Latest board photo from ${h.alias}`, loading: "lazy" }) : el("span")),
      el("div", { class: "row" },
        el("button", { class: "btn btn--ghost", type: "button", on: { click: () => openTimeline(h.session_id, h.alias, h.step_id) } }, icon("clock"), "Timeline"),
        el("div", { class: "spacer" }),
        el("button", { class: "btn btn--primary", type: "button", on: { click: () => resolveHelp(h.id) } }, icon("pass"), "Resolve")));
  }));
}

async function resolveHelp(id) {
  const { ok } = await api(`/api/ta/help/${id}/resolve`, { method: "POST" });
  if (ok) { toast("Marked as resolved.", "ok"); loadAll(); } else toast("Could not resolve that request.", "error");
}

setInterval(() => { for (const n of document.querySelectorAll(".wait[data-since]")) n.textContent = timeAgo(n.dataset.since); }, 15000);

// ── heatmap ───────────────────────────────────────────────────────────────────────────────────
const tooltip = $("#tooltip");
function showTip(target, title, lines) {
  tooltip.replaceChildren(el("strong", { text: title }), ...lines.map((l) => el("div", { text: l })));
  tooltip.hidden = false;
  const r = target.getBoundingClientRect();
  const tr = tooltip.getBoundingClientRect();
  let left = r.left + r.width / 2 - tr.width / 2;
  left = Math.max(8, Math.min(window.innerWidth - tr.width - 8, left));
  const top = r.top - tr.height - 8 < 8 ? r.bottom + 8 : r.top - tr.height - 8;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}
function hideTip() { tooltip.hidden = true; }

function glyph(cell) {
  switch (cell.state) {
    case "passed_first": return [icon("pass")];
    case "passed_after": return [icon("pass"), el("span", { text: String(cell.attempts) })];
    case "struggling": return [el("span", { text: `!${cell.fixes}` })];
    case "stuck": return cell.help ? [icon("bell"), el("span", { text: String(cell.fixes || "") })] : [el("span", { text: `!!${cell.fixes}` })];
    case "in_progress": return [el("span", { text: "•" })];
    default: return [];
  }
}

function renderHeatmap(h) {
  const table = $("#heatmap");
  $("#hm-empty").hidden = h.rows.length > 0;
  table.hidden = h.rows.length === 0;
  $("#hm-legend").hidden = h.rows.length === 0;
  if (!h.rows.length) return;
  const head = el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Student · bench" }),
    ...h.steps.map((s, i) => el("th", { scope: "col" }, `Step ${i + 1}`, el("span", { text: s.title })))));
  const body = el("tbody", {}, ...h.rows.map((row) => el("tr", {},
    el("th", { scope: "row", title: row.alias }, row.alias, row.bench_id ? el("small", { text: row.bench_id }) : null,
      row.is_simulated ? el("small", { class: "sim-tag", text: " sim" }) : null),
    ...row.cells.map((cell, i) => {
      const lines = [STATE_TEXT[cell.state], `${cell.attempts} check${cell.attempts === 1 ? "" : "s"} · ${cell.fixes} fix · ${cell.uncertain} can't tell`];
      if (cell.help) lines.push("Waiting for help");
      const label = `${row.alias}, step ${i + 1} ${h.steps[i].title}: ${lines.join(", ")}`;
      const btn = el("button", { class: `hm-cell s-${cell.state}${cell.cant_tell ? " cant-tell" : ""}`, type: "button", "aria-label": label,
        on: {
          click: () => openTimeline(row.session_id, row.alias, cell.step_id),
          pointerenter: (e) => showTip(e.currentTarget, `${row.alias} · ${h.steps[i].title}`, lines),
          pointerleave: hideTip, focus: (e) => showTip(e.currentTarget, `${row.alias} · ${h.steps[i].title}`, lines), blur: hideTip,
        } }, el("span", { class: "g" }, ...glyph(cell)));
      return el("td", {}, btn);
    }))));
  table.replaceChildren(head, body);
}

// ── drawer: attempt timeline ──────────────────────────────────────────────────────────────────
function closeOverlay() { document.querySelectorAll(".scrim, .drawer, .modal").forEach((n) => n.remove()); }
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeOverlay(); });

async function openTimeline(sessionId, alias, stepId) {
  closeOverlay();
  const { ok, data } = await api(`/api/ta/session/${sessionId}/timeline`);
  if (!ok) { toast("Could not load the timeline.", "error"); return; }
  const items = data.items.filter((a) => !stepId || a.step_id === stepId);
  const list = items.length ? el("ol", { class: "timeline" }, ...items.map((a) => el("li", {},
    a.thumb ? el("img", { src: a.thumb, alt: `Board photo for ${a.step_title}`, loading: "lazy" }) : el("div", { class: "skeleton", style: "width:112px;height:84px" }),
    el("div", { class: "stack", style: "gap:4px" },
      el("div", { class: "row", style: "gap:8px" }, el("strong", { text: a.kind === "ask" ? "Question" : a.kind === "ta_skip" ? "Skipped by TA" : (a.status || "").toUpperCase() }),
        el("span", { class: "muted", style: "font-size:13px", text: `${a.step_title} · ${new Date(a.created_at).toLocaleTimeString()}` })),
      a.question ? el("p", { class: "obs" }, `“${a.question}” → ${a.answer || ""}`) : null,
      ...a.observations.map((o) => el("p", { class: "obs", text: `${o.result}: ${(o.observation || "").replace(/^\[mock\]\s*/, "")}` })),
      a.detected_error_ids.length ? el("p", { class: "obs", text: `Detected: ${a.detected_error_ids.join(", ")}` }) : null,
      el("p", { class: "obs mono", text: [a.model_id && `model ${a.model_id}`, a.latency_ms !== null && a.latency_ms !== undefined && `${a.latency_ms} ms`, a.reason].filter(Boolean).join(" · ") }))))) :
    el("p", { class: "muted", text: "No attempts on this step yet." });
  const drawer = el("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": `Timeline for ${alias}` },
    el("div", { class: "drawer__head" }, icon("clock"), el("strong", { text: `${alias}${stepId ? " · " + ((steps.find((s) => s.id === stepId) || {}).title || stepId) : ""}` }),
      el("div", { class: "spacer" }), el("button", { class: "btn btn--ghost btn--icon", type: "button", "aria-label": "Close", on: { click: closeOverlay } }, icon("close"))),
    el("div", { class: "drawer__body" }, list));
  document.body.append(el("div", { class: "scrim", on: { click: closeOverlay } }), drawer);
  drawer.querySelector("button").focus();
}

// ── report ────────────────────────────────────────────────────────────────────────────────────
function showReport(r) {
  closeOverlay();
  const content = el("div", { class: "report" });
  content.innerHTML = r.html; // server-rendered Markdown with raw HTML disabled (see engine/report.py)
  const modal = el("section", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": "Class report" },
    el("div", { class: "modal__head" }, icon("report"), el("strong", { text: "End-of-class report" }), el("div", { class: "spacer" }),
      el("a", { class: "btn", href: `/api/ta/report/${r.id}.md`, download: `class-report-${r.id.slice(0, 8)}.md` }, icon("download"), "Download .md"),
      el("button", { class: "btn", type: "button", on: { click: async () => { await navigator.clipboard.writeText(r.markdown); toast("Report copied.", "ok"); } } }, icon("copy"), "Copy"),
      el("button", { class: "btn btn--ghost btn--icon", type: "button", "aria-label": "Close", on: { click: closeOverlay } }, icon("close"))),
    el("div", { class: "modal__body" }, content),
    el("div", { class: "meta" }, el("span", { text: `model ${r.model_id || "–"}` }),
      r.fallback_from ? el("span", { class: "tag", text: `fallback from ${r.fallback_from}` }) : null,
      el("span", { text: `${r.tokens || 0} tokens` }), el("span", { text: r.cost_usd === null || r.cost_usd === undefined ? "cost n/a" : `$${r.cost_usd.toFixed(4)}` }),
      el("span", { text: `${((r.latency_ms || 0) / 1000).toFixed(1)} s` })));
  document.body.append(el("div", { class: "scrim", on: { click: closeOverlay } }), modal);
}

$("#report-btn").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  const label = btn.querySelector("span");
  const old = label ? label.textContent : "";
  if (label) label.textContent = "Nemotron Ultra is writing…";
  const { ok, data } = await api("/api/ta/report", { method: "POST", json: { lab_id: labId } });
  btn.disabled = false;
  if (label) label.textContent = old;
  if (ok) showReport(data);
  else toast((data && data.message) || "Could not generate the report.", "error");
});

$("#seed-btn").addEventListener("click", async () => {
  const { ok, data } = await api("/api/demo/seed", { method: "POST", json: { students: 28 } });
  if (ok) { toast(`Seeded ${data.sessions} simulated students.`, "ok"); loadAll(); } else toast((data && data.message) || "Could not seed.", "error");
});
$("#clear-sim-btn").addEventListener("click", async () => {
  const { ok } = await api("/api/demo/seed", { method: "DELETE" });
  if (ok) { toast("Simulated data removed.", "ok"); loadAll(); }
});
$("#lab-pick").addEventListener("change", (e) => { labId = e.target.value; loadAll(); });

connectEvents({
  help_created: () => { scheduleRefresh(); },
  help_updated: () => scheduleRefresh(),
  help_resolved: () => scheduleRefresh(),
  check_result: () => scheduleRefresh(),
  step_advanced: () => scheduleRefresh(),
  session_started: () => scheduleRefresh(),
  session_completed: () => scheduleRefresh(),
  hub_update: () => scheduleRefresh(),
}, (status) => { if (status === "open") loadAll(); });

loadAll();
setInterval(loadAll, 30000);
