// Debug panel: capabilities, routing, model calls, last verdict, live metrics + session-only threshold sliders,
// LED mask, demo scene picker, baseline, budget meter and the demo controls for budget/timeout states.
import { $, api, boot, cfg, defaultConnection, el, initTopbar, renderChips, toast } from "./ui.js";
import { connectEvents } from "./ws.js";

initTopbar();
defaultConnection();

const SLIDERS = [
  ["quality", "blur_var_min", "Focus: min Laplacian var", 0, 400, 1],
  ["quality", "brightness_min", "Light: min brightness", 0, 255, 1],
  ["quality", "brightness_max", "Light: max brightness", 0, 255, 1],
  ["quality", "glare_ratio_max", "Glare: max ratio", 0, 0.2, 0.001],
  ["quality", "motion_max", "Steady: max motion", 0, 40, 0.5],
  ["led", "v_delta_min", "LED: min brightness rise", 0, 150, 1],
  ["led", "s_min", "LED: min saturation", 0, 255, 1],
  ["led", "min_area_px", "LED: min blob area", 1, 400, 1],
  ["led", "strong_min", "LED: strong evidence", 0, 1, 0.01],
];
const METRIC = { blur_var_min: "blur_var", brightness_min: "brightness", brightness_max: "brightness", glare_ratio_max: "glare_ratio", motion_max: "motion" };
let unlocked = !!boot.is_ta;
let latestMetrics = {};
const originalBudget = { ...(cfg.budget || {}) };

function guard() {
  if (!unlocked) { $("#unlock-card").hidden = false; $("#unlock-pin").focus(); toast("Enter the TA PIN to use the controls.", "warn"); }
  return unlocked;
}

$("#unlock-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { ok } = await api("/api/ta/login", { method: "POST", json: { pin: $("#unlock-pin").value } });
  if (ok) { unlocked = true; $("#unlock-card").hidden = true; toast("Controls unlocked.", "ok"); } else toast("Wrong PIN.", "error");
});
$("#unlock-card").hidden = unlocked;

function buildSliders(thresholds) {
  const box = $("#sliders");
  box.replaceChildren(...SLIDERS.map(([section, key, label, min, max, step]) => {
    const value = thresholds[section][key];
    const out = el("span", { class: "mono nums", text: String(value) });
    const input = el("input", { type: "range", min, max, step, value, "aria-label": label, on: {
      input: (e) => { out.textContent = e.target.value; },
      change: async (e) => {
        if (!guard()) { e.target.value = value; out.textContent = String(value); return; }
        const r = await api("/api/debug/thresholds", { method: "POST", json: { section, key, value: Number(e.target.value) } });
        if (!r.ok) toast(r.data.message || "Could not change that threshold.", "error");
      },
    } });
    const live = METRIC[key] ? el("span", { class: "muted mono", dataset: { metric: METRIC[key] } }) : null;
    return el("div", { class: "slider" }, el("span", {}, label, live ? el("br") : null, live), input, out);
  }));
}

function renderState(s) {
  $("#routing tbody").replaceChildren(...s.routing.map((r) => el("tr", {},
    el("td", { class: "mono", text: r.role }), el("td", { class: "mono wrap-cell", text: r.model || "— (run verify)" }),
    el("td", { text: r.case || "–" }), el("td", { class: "wrap-cell", text: r.used_for }))));
  $("#routing-note").textContent = `JSON mode in use: ${s.json_mode_effective} · thinking control: ${s.capabilities.thinking_control} · tools: ${s.capabilities.tools_mode}`;
  const b = s.budget;
  const meter = (spent, limit, label) => {
    const pct = limit > 0 ? Math.min(100, (spent / limit) * 100) : 100;
    return el("div", { class: "stack", style: "gap:4px" }, el("div", { class: "kv" }, el("span", { text: label }), el("strong", { text: `$${spent.toFixed(4)} of $${Number(limit).toFixed(2)}` })),
      el("div", { class: "bar", role: "img", "aria-label": `${label} ${pct.toFixed(0)}% used` }, el("i", { style: `width:${pct}%` })));
  };
  $("#budget").replaceChildren(meter(b.session_usd, b.limit_session, "This session"), meter(b.day_usd, b.limit_day, "Today"),
    b.pricing_known ? el("span") : el("p", { class: "tone-fix", style: "font-size:14px", text: "Prices in config/pricing.yaml are empty: cost shows n/a and the guard cannot stop spending." }));
  $("#tokens").textContent = `${s.tokens.calls || 0} calls · ${s.tokens.prompt_tokens || 0} in / ${s.tokens.completion_tokens || 0} out tokens`;
  $("#calls tbody").replaceChildren(...s.calls.map((c) => el("tr", {},
    el("td", { class: "mono", text: new Date(c.created_at).toLocaleTimeString() }), el("td", { class: "mono", text: c.role }),
    el("td", { class: "mono", text: c.model_id }), el("td", { text: c.ok ? "yes" : "no", class: c.ok ? "tone-pass" : "tone-danger" }),
    el("td", { class: "num", text: `${c.latency_ms} ms` }), el("td", { class: "num", text: `${c.prompt_tokens}/${c.completion_tokens}` }),
    el("td", { class: "num", text: c.cost_usd === null ? "n/a" : `$${Number(c.cost_usd).toFixed(4)}` }), el("td", { class: "wrap-cell", text: c.error || "" }))));
  $("#last-verdict").textContent = s.last_verdict ? JSON.stringify(s.last_verdict, null, 2) : (s.last_answer ? JSON.stringify(s.last_answer, null, 2) : "No checks yet.");
  $("#caps").textContent = JSON.stringify(s.capabilities, null, 2);
  $("#caps-state").textContent = s.capabilities.verified ? "verified by Phase 0" : "not verified yet (run verify): conservative defaults";
  $("#baseline-state").textContent = s.baseline_pending ? `Waiting for a clear frame to store the ${s.baseline_pending} baseline…` :
    s.baselines.length ? `Baselines stored: ${s.baselines.join(", ")}` : "No LED baseline stored yet.";
}

async function poll() {
  const { ok, data } = await api("/api/debug/state");
  if (ok) {
    if (!$("#sliders").children.length) buildSliders(data.thresholds);
    renderState(data);
  }
}

function refreshMask() {
  const img = $("#ledmask");
  const probe = new Image();
  probe.onload = () => { img.src = probe.src; };
  probe.onerror = () => { img.alt = "Board not found: show all four markers to see the LED mask."; };
  probe.src = `/api/frame/ledmask.jpg?ts=${Date.now()}`;
}

async function setupScenes() {
  const { ok, data } = await api("/api/demo/scenes");
  if (!ok || !data.enabled) return;
  $("#scene-card").hidden = false;
  const groups = {};
  for (const s of data.scenes) (groups[s.step] = groups[s.step] || []).push(s.label);
  $("#scene-grid").replaceChildren(...Object.entries(groups).map(([step, labels]) => el("div", { class: "row wrap", style: "gap:6px" },
    el("strong", { class: "mono", style: "width:28px", text: step }),
    ...labels.map((label) => el("button", { class: "btn", style: "min-height:34px;font-size:13px", type: "button",
      on: { click: async () => { await api("/api/demo/scene", { method: "POST", json: { step, label } }); toast(`Scene ${step}/${label}`, "info", 1500); } } }, label)))));
}

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-ctl]");
  if (!btn) return;
  const ctl = btn.dataset.ctl;
  if (ctl === "baseline") {
    const { data } = await api("/api/baseline", { method: "POST" });
    toast(data.ok ? "Baseline stored." : data.message || "Could not store a baseline.", data.ok ? "ok" : "warn");
    return;
  }
  if (!guard()) return;
  const calls = {
    "budget-zero": ["/api/debug/budget", { session_usd: 0, day_usd: 0 }, "Budget limit simulated: the next check will be blocked."],
    "budget-reset": ["/api/debug/budget", { session_usd: originalBudget.session_usd, day_usd: originalBudget.day_usd }, "Budget restored."],
    slow: ["/api/debug/mock_latency", { ms: 35000 }, "Mock answers now take 35 s (shows the timeout state)."],
    fast: ["/api/debug/mock_latency", { ms: 600 }, "Mock speed back to normal."],
  }[ctl];
  if (!calls) return;
  const { ok, data } = await api(calls[0], { method: "POST", json: calls[1] });
  toast(ok ? calls[2] : (data.message || "Not available."), ok ? "ok" : "warn");
  poll();
});

connectEvents({
  quality: (q) => {
    renderChips($("#qchips"), q.chips);
    latestMetrics = q.metrics || {};
    for (const n of document.querySelectorAll("[data-metric]")) {
      const v = latestMetrics[n.dataset.metric];
      n.textContent = v === undefined || v === null ? "" : `now ${typeof v === "number" ? Number(v).toFixed(v < 1 ? 3 : 1) : v}`;
    }
  },
  check_result: () => poll(),
  cost_update: () => poll(),
});
poll();
setupScenes();
refreshMask();
setInterval(poll, 4000);
setInterval(refreshMask, 1500);
