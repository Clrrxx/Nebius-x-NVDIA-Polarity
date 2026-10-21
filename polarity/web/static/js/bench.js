// Bench view: step card, Check (Space), hold-to-ask (V), verdict card with captions + voice, Call TA,
// live quality chips, camera banner, demo scene picker and the completion screen.
import { Recorder, createRecognizer } from "./audio.js";
import { tts } from "./tts.js";
import {
  $, CHECK_RESULT, STATUS, api, cfg, defaultConnection, el, fmtSeconds, icon, inTextField, initTopbar, renderChips,
  setConnection, toast,
} from "./ui.js";
import { connectEvents } from "./ws.js";

initTopbar();
defaultConnection();

const RETAKE_ICON = { dark: "lamp", bright: "lamp", glare: "tilt", blur: "focus", markers: "markers", motion: "hand" };
const TIMEOUT_S = Number(cfg.check_timeout_s || 30);

let lab = null;           // full lab definition
let state = null;         // SessionState from the server
let viewStepId = null;    // step shown in the card (stays on a passed step until "Next step")
let checking = false;
let staged = null;        // { kind: "audio", blob, seconds } | { kind: "text", text }
let recorder = null;
let recognizer = null;
let holding = false;
let lastSpoken = "";

const slot = $("#verdict-slot");
const checkBtn = $("#check-btn");
const audioMode = cfg.audio_mode;

// ── rendering ─────────────────────────────────────────────────────────────────────────────────
function stepById(id) { return lab.steps.find((s) => s.id === id); }
function stepIndex(id) { return lab.steps.findIndex((s) => s.id === id); }

function renderTopbar() {
  $("#tb-title").textContent = lab.title;
  const s = state.session;
  $("#tb-sub").textContent = `${s.student_alias}${s.bench_id ? " · Bench " + s.bench_id : ""}`;
  const dots = $("#dots");
  dots.replaceChildren(...lab.steps.map((st, i) => {
    const prog = state.progress[i];
    const done = prog && prog.passed;
    const current = st.id === state.current_step_id;
    const label = `Step ${i + 1}: ${st.title}${done ? " (done)" : current ? " (current)" : ""}`;
    return el("li", { class: done ? "is-done" : current ? "is-current" : "", tabindex: "0", "aria-label": label },
      done ? icon("pass", "icon") : String(i + 1), el("span", { class: "tip", text: `${i + 1}. ${st.title}` }));
  }));
  const help = (state.open_help || []).length > 0;
  $("#help-pill").hidden = !help;
}

function renderStep(stepId) {
  viewStepId = stepId;
  const step = stepById(stepId);
  const idx = stepIndex(stepId);
  $("#step-eyebrow").textContent = `Step ${idx + 1} of ${lab.steps.length} · ${step.title}`;
  $("#step-title").textContent = step.title;
  $("#step-instruction").textContent = step.instruction;
  const illus = $("#step-illus");
  if (step.illustration) {
    illus.hidden = false;
    $("#step-illus-img").src = `/static/img/steps/${step.illustration}`;
    $("#step-illus-img").alt = `Illustration for step ${idx + 1}: ${step.title}`;
  } else {
    illus.hidden = true;
  }
  $("#step-checks").replaceChildren(...step.checks.map((c) =>
    el("li", { class: c.allow_uncertain ? "fine" : "" }, el("span", { text: c.statement }))));
  $("#mic-help").textContent = step.led_check ? step.led_check.instruction_for_capture : (step.capture_tip || "");
}

function compact(on) {
  $("#step-card").classList.toggle("is-compact", on);
  const t = $("#details-toggle");
  t.hidden = !on;
  t.setAttribute("aria-expanded", String(!on));
  t.textContent = "Step details";
}

function showResult() {
  compact(true);
  $("#side-scroll").scrollTo({ top: 0 });
}

function placeholder() {
  slot.replaceChildren();
  compact(false);
  $("#mic-help").textContent = "Press Check when you're ready. Hold V (or the mic) to ask a question first.";
}

function thinking(seconds) {
  checkBtn.disabled = true;
  $("#check-label").textContent = `Looking closely… ${seconds} s`;
  if (seconds === 0) {
    showResult();
    slot.replaceChildren(el("div", { class: "card stack", "aria-busy": "true" },
      el("div", { class: "row" }, icon("search"), el("strong", { text: "Checking your step…" })),
      el("div", { class: "skeleton sk-line", style: "width:80%" }), el("div", { class: "skeleton sk-line", style: "width:60%" }),
      el("div", { class: "skeleton sk-block" })));
  }
}

function timeoutCard() {
  showResult();
  slot.replaceChildren(el("div", { class: "card verdict verdict--uncertain" },
    el("div", { class: "verdict__banner" }, icon("clock"), el("span", { class: "status", text: "STILL WAITING" })),
    el("div", { class: "verdict__body" },
      el("p", { class: "caption", text: "I couldn't reach the AI. Your work is saved — try Check again." }),
      el("p", { class: "muted", text: "If an answer arrives in the next few seconds it will appear here." }))));
}

function errorCard({ title, message, iconName = "fix", tone = "danger", retry = true }) {
  const card = el("div", { class: `card verdict verdict--${tone}` },
    el("div", { class: "verdict__banner" }, icon(iconName), el("span", { class: "status", text: title })),
    el("div", { class: "verdict__body" }, el("p", { class: "caption", text: message })));
  if (retry) {
    card.querySelector(".verdict__body").append(el("div", { class: "row" },
      el("button", { class: "btn btn--primary", type: "button", on: { click: () => runCheck() } }, icon("refresh"), "Try again")));
  }
  showResult();
  slot.replaceChildren(card);
}

function speak(...texts) {
  const text = texts.filter(Boolean).join(" ");
  lastSpoken = text;
  if (cfg.speak_feedback !== false) tts.speak(text);
}

function regionBox(region) {
  return el("div", { class: "region", style: `left:${region.x * 100}%;top:${region.y * 100}%;width:${region.w * 100}%;height:${region.h * 100}%`, "aria-hidden": "true" });
}

function renderVerdict(v, payload, silent = false) {
  const step = stepById(v.step_id) || stepById(viewStepId);
  const meta = STATUS[v.status] || STATUS.uncertain;
  const p = v.perception;
  const norm = (t) => (t || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  let caption = (p && p.spoken_feedback) || "";
  if (!caption) caption = v.status === "uncertain" ? "I can't tell yet — the picture isn't clear enough to judge your board." : v.status === "fix" ? "Something needs fixing." : "Looks right.";
  let word = meta.word;
  let sub = "";
  if (v.status === "pass_partial") {
    const n = (v.double_check || []).length || 1;
    word = `PASS · ${n} thing${n > 1 ? "s" : ""} to double-check`;
  }
  if (v.status === "fix") sub = `Hint level ${v.hint_level} of 3`;
  if (v.reason && v.reason.startsWith("led:")) sub = "Confirmed by the on-device LED detector";

  const body = el("div", { class: "verdict__body" });
  body.append(el("div", { class: "caption" },
    el("span", { text: caption }),
    el("button", { class: "btn btn--ghost btn--icon", type: "button", "aria-label": "Replay spoken feedback", on: { click: () => tts.speak(lastSpoken || caption) } }, icon("speaker"))));

  if (v.status === "fix" && v.hint_text && norm(v.hint_text) !== norm(caption)) {
    const dots = el("span", { class: "hintdots", "aria-label": `Hint level ${v.hint_level} of 3` },
      ...[1, 2, 3].map((n) => el("i", { class: n <= v.hint_level ? "on" : "" })));
    body.append(el("div", { class: "hintline" }, icon("lamp"), el("span", { text: v.hint_text }), dots));
  }
  if (v.status === "pass_partial" && (v.double_check || []).length) {
    body.append(el("div", { class: "hintline" }, icon("eye"),
      el("span", {}, el("strong", { text: "Double-check yourself: " }), (v.double_check || []).join(" · "))));
  }
  if (v.status === "uncertain" && norm(v.retake_instruction) !== norm(caption)) {
    const metric = (v.reason || "").startsWith("quality:") ? v.reason.split(":")[1] : (v.reason || "").includes("not_visible") ? "motion" : "";
    body.append(el("div", { class: "retake" }, icon(RETAKE_ICON[metric] || "camera"),
      el("span", { text: v.retake_instruction || "Hold the board still in good light, then check again." })));
  }
  if (p && p.checks && p.checks.length) {
    const rows = p.checks.map((c) => {
      const r = CHECK_RESULT[c.result] || CHECK_RESULT.not_visible;
      const stmt = (step && (step.checks.find((x) => x.id === c.id) || {}).statement) || c.id;
      return el("li", {},
        el("span", { class: `res tone-${r.tone}` }, icon(r.icon), el("span", { text: r.word })),
        el("span", { text: stmt }),
        el("span", { class: "obs", text: (c.observation || "").replace(/^\[mock\]\s*/, "") }));
    });
    body.append(el("ul", { class: "checks", "aria-label": "What I checked" }, ...rows));
  }
  if (v.led) {
    const led = v.led;
    body.append(el("div", { class: "row muted", style: "font-size:15px;gap:8px" }, icon("light"),
      el("span", { text: `LED detector: ${led.lit ? "lit" : "dark"} · signal ${Math.round((led.signal_strength || 0) * 100)}%${led.note ? " · " + led.note : ""}` })));
  }
  if (v.warped_url) {
    const fig = el("figure", { class: "evidence", style: "margin:0" }, el("img", { src: v.warped_url, alt: "The top-down image that was checked" }));
    if (p && p.evidence_region && p.confidence >= 0.75) fig.append(regionBox(p.evidence_region));
    body.append(fig);
  }
  if (p && p.student_answer) {
    body.append(el("div", { class: "bubble" }, el("div", { class: "who", text: "Answer to your question" }), el("div", { text: p.student_answer })));
  }
  const passed = v.status === "pass" || v.status === "pass_partial";
  // The dock holds the next action: "Next step" after a pass, "Check my step" otherwise.
  setNextMode(passed && !silent ? { finished: !!(payload && payload.completed) } : null);
  if (v.status === "fix" && step && step.led_check) {
    body.append(el("div", { class: "row" }, el("button", { class: "btn", type: "button", on: { click: () => runAudit() } }, icon("search"), "Find the problem (board check)")));
  }

  const metaLine = el("div", { class: "meta" },
    el("span", { text: v.model_id ? `model ${v.model_id}` : "on-device check (no cloud call)" }),
    v.latency_ms !== null && v.latency_ms !== undefined ? el("span", { text: `${v.latency_ms} ms` }) : null,
    v.second_look_used ? el("span", { class: "tag" }, icon("eye"), "second look") : null,
    v.cost_usd !== null && v.cost_usd !== undefined && v.model_id !== "MOCK" ? el("span", { text: `$${v.cost_usd.toFixed(4)}` }) : null,
    el("span", { text: v.reason }));

  const card = el("article", { class: `card verdict verdict--${meta.tone}` },
    el("div", { class: "verdict__banner" }, el("span", { class: `status status--${meta.tone}` }, icon(meta.icon), el("span", { text: word })),
      sub ? el("span", { class: "sub", text: sub }) : null),
    body, metaLine);
  showResult();
  slot.replaceChildren(card);
  if (!silent) speak(caption, v.status === "uncertain" && norm(v.retake_instruction) !== norm(caption) ? v.retake_instruction : null, p && p.student_answer);
}

let nextFinished = false;
function setNextMode(mode) {
  const next = $("#next-btn");
  next.hidden = !mode;
  checkBtn.hidden = !!mode;
  if (mode) {
    nextFinished = mode.finished;
    $("#next-label").textContent = mode.finished ? "Finish lab" : "Next step";
    $("#mic-help").textContent = mode.finished ? "That was the last step. Press Enter to finish." : "Press Enter (or the button) for the next step.";
    next.focus({ preventScroll: true });
  }
}

function renderAnswer(data) {
  const card = el("article", { class: "card stack" },
    el("div", { class: "row" }, icon("mic"), el("strong", { text: "You asked" }), el("span", { class: "muted", text: data.question ? `“${data.question}”` : "(voice clip)" })),
    el("div", { class: "bubble" }, el("div", { class: "who", text: "Answer" }), el("div", { text: data.answer })),
    data.parts && data.parts.length ? el("div", { class: "row wrap" }, ...data.parts.map((part) =>
      el("button", { class: "btn", type: "button", on: { click: () => lookupPart(part) } }, icon("chip"), `${part} pinout`))) : null,
    el("div", { class: "meta", style: "border:0;padding:0" }, el("span", { text: `model ${data.model_id}` }), el("span", { text: `${data.latency_ms} ms` })));
  showResult();
  slot.replaceChildren(card);
  speak(data.answer);
}

async function lookupPart(part) {
  const { ok, data } = await api("/api/parts/lookup", { method: "POST", json: { part } });
  if (!ok) { toast((data && data.message) || "Part lookup is not available.", "warn"); return; }
  const card = el("article", { class: "card stack" },
    el("div", { class: "row" }, icon("chip"), el("strong", { text: `${part}` }), el("span", { class: "muted", text: "from web sources (Tavily)" })),
    el("p", { text: data.summary }),
    data.pinout && data.pinout.length ? el("table", { class: "table" }, el("thead", {}, el("tr", {}, el("th", { text: "Pin" }), el("th", { text: "Name" }))),
      el("tbody", {}, ...data.pinout.map((r) => el("tr", {}, el("td", { text: r.pin }), el("td", { text: r.name }))))) : null,
    el("ul", { class: "errs" }, ...(data.sources || []).map((u) => el("li", {}, el("a", { href: u, target: "_blank", rel: "noopener noreferrer", text: u })))));
  showResult();
  slot.replaceChildren(card);
}

function renderComplete() {
  checkBtn.disabled = true;
  const done = el("section", { class: "card complete", "aria-live": "polite" },
    el("div", { class: "ring" }, icon("pass")),
    el("h1", { text: "Lab complete" }),
    el("p", { class: "muted", text: "Show your TA — great work." }),
    el("div", { class: "facts" },
      el("div", {}, el("strong", { text: fmtSeconds(state.elapsed_s) }), el("span", { class: "muted", text: "total time" })),
      el("div", {}, el("strong", { text: String(state.total_checks) }), el("span", { class: "muted", text: "checks" }))),
    el("ul", { class: "steplist" }, ...lab.steps.map((s, i) => el("li", {}, icon("pass"), `${i + 1}. ${s.title}`))),
    el("button", { class: "btn", type: "button", on: { click: async () => { await api("/api/session/reset", { method: "POST" }); location.href = "/"; } } }, "Start a new session"));
  $("#step-card").replaceChildren(done);
  $("#actions").hidden = true;
  slot.replaceChildren();
  speak("Lab complete. Show your TA — great work.");
}

// ── actions ───────────────────────────────────────────────────────────────────────────────────
async function refreshState() {
  const { ok, data } = await api("/api/session/current");
  if (!ok || !data.state) { location.href = "/"; return null; }
  state = data.state;
  lab = data.lab;
  renderTopbar();
  return data;
}

function goNext(finished) {
  setNextMode(null);
  if (finished) { renderComplete(); return; }
  if (state.current_step_id) renderStep(state.current_step_id);
  placeholder();
  checkBtn.focus();
}

async function runCheck() {
  if (checking || !state || state.completed) return;
  if (viewStepId !== state.current_step_id && state.current_step_id) { renderStep(state.current_step_id); }
  checking = true;
  tts.stop();
  let secs = 0;
  thinking(0);
  const tick = setInterval(() => { secs += 1; thinking(secs); if (secs === TIMEOUT_S) timeoutCard(); }, 1000);
  const form = new FormData();
  if (staged && staged.kind === "audio") form.append("audio", staged.blob, "question.wav");
  if (staged && staged.kind === "text") form.append("typed_question", staged.text);
  const { ok, status, data } = await api("/api/check", { method: "POST", form });
  clearInterval(tick);
  checking = false;
  checkBtn.disabled = false;
  $("#check-label").textContent = "Check my step";
  if (ok) {
    setStaged(null);
    state = data.state;
    renderTopbar();
    renderVerdict(data.verdict, data);
    if (data.help) toast("Your TA has been notified.", "info");
    if (!cfg.mock && cfg.has_key) setConnection("ok", "Token Factory · connected");
    return;
  }
  const err = (data && data.error) || "error";
  if (err === "budget") errorCard({ title: "BUDGET LIMIT", message: data.message, iconName: "clock", tone: "fix", retry: false });
  else if (err === "model_unavailable") errorCard({ title: "AI NOT SET UP", message: data.message, iconName: "chip", tone: "fix", retry: false });
  else if (err === "no_camera") errorCard({ title: "NO CAMERA", message: data.message, iconName: "camera", tone: "danger" });
  else if (err === "busy") toast("Still checking — one moment.", "warn");
  else if (err === "no_session" || err === "completed") location.href = "/";
  else {
    if (!cfg.mock) setConnection("off", status === 0 ? "Offline" : "Token Factory · unreachable");
    errorCard({ title: "COULDN'T CHECK", message: (data && data.message) || "I couldn't check that right now — try again." });
  }
}

async function runAudit() {
  const card = el("div", { class: "card stack", "aria-busy": "true" }, el("div", { class: "row" }, icon("search"), el("strong", { text: "Checking the whole board…" })),
    el("div", { class: "skeleton sk-block" }));
  showResult();
  slot.replaceChildren(card);
  const { ok, data } = await api("/api/audit", { method: "POST" });
  if (!ok) { errorCard({ title: "BOARD CHECK FAILED", message: (data && data.message) || "Try again.", retry: false }); return; }
  const list = el("ul", { class: "checks" }, ...(data.suspects || []).map((s) => {
    const st = stepById(s.step_id);
    const chk = st && st.checks.find((c) => c.id === s.check_id);
    return el("li", {}, el("span", { class: "res tone-fix" }, icon("fix"), el("span", { text: `Step ${stepIndex(s.step_id) + 1}` })),
      el("span", { text: chk ? chk.statement : s.check_id }),
      el("span", { class: "obs" }, `${s.why} `, el("button", { class: "btn btn--ghost", type: "button", on: { click: () => gotoStep(s.step_id) } }, `Go to step ${stepIndex(s.step_id) + 1}`)));
  }));
  slot.replaceChildren(el("article", { class: "card verdict verdict--fix" },
    el("div", { class: "verdict__banner" }, el("span", { class: "status status--fix" }, icon("search"), el("span", { text: "BOARD CHECK" }))),
    el("div", { class: "verdict__body" }, el("p", { class: "caption", text: data.spoken_feedback }),
      (data.suspects || []).length ? list : el("p", { class: "muted", text: "Every step looks right from above — check the battery switch and the batteries." })),
    el("div", { class: "meta" }, el("span", { text: `model ${data.model_id}` }), el("span", { text: `${data.latency_ms} ms` }))));
  speak(data.spoken_feedback);
}

async function gotoStep(stepId) {
  const { ok, data } = await api("/api/session/goto", { method: "POST", json: { step_id: stepId } });
  if (!ok) { toast(data.message || "Could not go back.", "warn"); return; }
  state = data.state;
  renderTopbar();
  renderStep(state.current_step_id);
  placeholder();
}

function setStaged(value) {
  staged = value;
  const box = $("#staged");
  if (!value) { box.hidden = true; return; }
  box.hidden = false;
  $("#staged-text").replaceChildren(value.kind === "audio"
    ? el("span", {}, el("strong", { text: `Question recorded (${value.seconds.toFixed(1)} s)` }), " · goes with your next Check")
    : el("span", {}, el("strong", { text: `“${value.text}”` }), " · goes with your next Check"));
}

async function askNow() {
  if (!staged) return;
  const form = new FormData();
  if (staged.kind === "audio") form.append("audio", staged.blob, "question.wav");
  else form.append("question", staged.text);
  showResult();
  slot.replaceChildren(el("div", { class: "card stack", "aria-busy": "true" }, el("div", { class: "row" }, icon("mic"), el("strong", { text: "Thinking about your question…" })),
    el("div", { class: "skeleton sk-line", style: "width:70%" })));
  const { ok, data } = await api("/api/ask", { method: "POST", form });
  setStaged(null);
  if (ok) {
    renderAnswer(data);
    if (data.help) toast("Your TA has been notified.", "info");
  } else {
    errorCard({ title: "COULDN'T ANSWER", message: (data && data.message) || "Try asking again.", retry: false });
  }
}

// ── voice input ───────────────────────────────────────────────────────────────────────────────
function setupVoice() {
  const micBtn = $("#mic-btn");
  const askForm = $("#ask-form");
  const canRecord = Recorder.supported();
  const sttMode = audioMode === "browser_stt";
  if (audioMode === "typed" || (sttMode && !createRecognizer()) || (!sttMode && !canRecord)) {
    micBtn.hidden = true;
    askForm.hidden = false;
  }
  askForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = $("#ask-input").value.trim();
    if (!text) return;
    setStaged({ kind: "text", text });
    $("#ask-input").value = "";
    askNow();
  });
  const meter = $("#meter-fill");
  recorder = new Recorder({ maxSeconds: Number(cfg.audio_max_seconds || 15), onLevel: (l) => { meter.style.width = `${Math.round(l * 100)}%`; }, onAutoStop: () => stopHold() });

  async function startHold() {
    if (holding || checking) return;
    holding = true;
    micBtn.classList.add("is-recording");
    $("#mic-label").textContent = "Listening… release to stop";
    tts.stop();
    if (sttMode) {
      recognizer = createRecognizer({ onResult: (text) => { $("#mic-label").textContent = text ? `“${text}”` : "Listening…"; }, onEnd: (text) => {
        if (text) setStaged({ kind: "text", text });
        micBtn.classList.remove("is-recording");
        $("#mic-label").textContent = "Hold to ask";
      }, onError: (msg) => toast(`Speech recognition: ${msg}`, "warn") });
      recognizer.start();
      return;
    }
    try {
      await recorder.start();
    } catch (err) {
      holding = false;
      micBtn.classList.remove("is-recording");
      $("#mic-label").textContent = "Hold to ask";
      toast("Microphone blocked — allow it in the browser, or type your question.", "warn");
      $("#ask-form").hidden = false;
    }
  }

  async function stopHold() {
    if (!holding) return;
    holding = false;
    if (sttMode) { if (recognizer) recognizer.stop(); return; }
    micBtn.classList.remove("is-recording");
    $("#mic-label").textContent = "Hold to ask";
    const blob = await recorder.stop();
    if (blob) {
      const seconds = (blob.size - 44) / 2 / 16000;
      setStaged({ kind: "audio", blob, seconds });
    }
  }
  micBtn.addEventListener("pointerdown", (e) => { e.preventDefault(); startHold(); });
  for (const ev of ["pointerup", "pointerleave", "pointercancel"]) micBtn.addEventListener(ev, () => stopHold());
  document.addEventListener("keydown", (e) => {
    if (inTextField(e.target)) return;
    if ((e.key === "v" || e.key === "V") && !e.repeat && !micBtn.hidden) { e.preventDefault(); startHold(); }
  });
  document.addEventListener("keyup", (e) => { if (e.key === "v" || e.key === "V") stopHold(); });
}

// ── wiring ────────────────────────────────────────────────────────────────────────────────────
checkBtn.addEventListener("click", () => runCheck());
$("#next-btn").addEventListener("click", () => goNext(nextFinished));
$("#ta-btn").addEventListener("click", async () => {
  const { ok, data } = await api("/api/help", { method: "POST" });
  if (ok) {
    toast(data.created ? "Your TA has been notified." : "Your TA already knows — they're on the way.", "info");
    $("#help-pill").hidden = false;
  } else toast((data && data.message) || "Could not reach the TA queue.", "error");
});
$("#staged-ask").addEventListener("click", () => askNow());
$("#details-toggle").addEventListener("click", (e) => {
  const card = $("#step-card");
  const nowCompact = !card.classList.contains("is-compact");
  card.classList.toggle("is-compact", nowCompact);
  e.currentTarget.setAttribute("aria-expanded", String(!nowCompact));
});
$("#staged-clear").addEventListener("click", () => setStaged(null));
$("#view-pip").addEventListener("click", (e) => {
  const pip = $("#pip");
  pip.hidden = !pip.hidden;
  e.currentTarget.setAttribute("aria-pressed", String(!pip.hidden));
});
document.addEventListener("keydown", (e) => {
  if (inTextField(e.target)) return;
  if (e.code === "Space" && !e.repeat && !checkBtn.hidden && !(e.target && e.target.tagName === "BUTTON" && e.target.id !== "check-btn")) {
    e.preventDefault();
    runCheck();
  }
});

async function setupDemo() {
  const { ok, data } = await api("/api/demo/scenes");
  if (!ok || !data.enabled) return;
  const wrap = $("#demo-scene");
  const sel = $("#scene-select");
  wrap.hidden = false;
  const groups = {};
  for (const s of data.scenes) (groups[s.step] = groups[s.step] || []).push(s.label);
  for (const [step, labels] of Object.entries(groups)) {
    const st = lab.steps.find((x) => x.id === step);
    const og = el("optgroup", { label: st ? `${step} · ${st.title}` : step });
    for (const label of labels) og.append(el("option", { value: `${step}/${label}`, text: label.replace(/^_/, "(") + (label.startsWith("_") ? ")" : "") }));
    sel.append(og);
  }
  sel.value = `${data.current.step}/${data.current.label}`;
  sel.addEventListener("change", () => {
    const [step, label] = sel.value.split("/");
    api("/api/demo/scene", { method: "POST", json: { step, label } });
  });
  return sel;
}

let sceneSelect = null;
connectEvents({
  quality: (q) => {
    renderChips($("#qchips"), q.chips);
    const disconnected = q.camera && q.camera.connected === false;
    $("#cam-banner").hidden = !disconnected;
    if (disconnected) $("#cam-banner-text").textContent = `Camera disconnected — reconnecting…${q.camera.error ? " (" + q.camera.error + ")" : ""}`;
  },
  demo_scene: (s) => { if (sceneSelect) sceneSelect.value = `${s.step}/${s.label}`; },
  help_resolved: (h) => {
    if (state && h && h.session_id === state.session.id) {
      $("#help-pill").hidden = true;
      toast("Your TA marked your request as resolved.", "ok");
    }
  },
  help_created: (h) => { if (state && h && h.session_id === state.session.id) $("#help-pill").hidden = false; },
}, (status) => { if (status === "closed" && !cfg.mock) setConnection("off", "Offline"); else if (status === "open") defaultConnection(); });

(async () => {
  const data = await refreshState();
  if (!data) return;
  if (state.completed) { renderComplete(); return; }
  renderStep(state.current_step_id);
  if (data.last_verdict && data.last_verdict.step_id === state.current_step_id) renderVerdict(data.last_verdict, null, true);
  else placeholder();
  setupVoice();
  sceneSelect = await setupDemo();
})();
