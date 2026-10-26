// Start screen: nickname + lab + bench, and a live camera check (all five quality chips green to start).
import { $, api, cfg, defaultConnection, el, initTopbar, renderChips } from "./ui.js";
import { connectEvents } from "./ws.js";

initTopbar();
defaultConnection();

const form = $("#start-form");
const startBtn = $("#start-btn");
const alias = $("#alias");
const labSel = $("#lab");
let chipsOk = false;
let demoBypass = false;

for (const lab of (cfg.labs || []).filter((l) => l.source === "published")) {
  labSel.append(el("option", { value: lab.id, text: `${lab.title}  ·  ${lab.steps} steps`, selected: lab.id === cfg.default_lab }));
}
try { $("#bench").value = localStorage.getItem("polarity.bench") || ""; } catch (e) { /* ignore */ }

$("#cam-source").textContent = cfg.camera_source === "demo" ? "Demo camera (no hardware)" : "USB / built-in camera";
if (cfg.camera_source === "demo") {
  const link = $("#demo-link");
  link.hidden = false;
  link.addEventListener("click", (e) => {
    e.preventDefault();
    demoBypass = true;
    update();
    $("#qhint").textContent = "Demo mode: the camera check is bypassed.";
  });
}

function update() {
  const ready = alias.value.trim().length > 0 && (chipsOk || demoBypass);
  startBtn.disabled = !ready;
  $("#start-help").textContent = ready ? "Ready when you are." :
    !alias.value.trim() ? "Enter a nickname to start." : "All five camera checks must be green before you start.";
}
alias.addEventListener("input", update);

const RETAKE = cfg.retake_instructions || {};
renderChips($("#qchips"), null);
connectEvents({
  quality: (q) => {
    renderChips($("#qchips"), q.chips, q.board);
    chipsOk = Object.values(q.chips || {}).every(Boolean) && (q.chips && Object.keys(q.chips).length === 5);
    const first = (q.failing || [])[0];
    if (!demoBypass) $("#qhint").textContent = chipsOk ? "Camera looks good." : first === "camera" ? "Waiting for the camera…" : RETAKE[first] || "";
    update();
  },
}, (status) => { if (status === "closed") renderChips($("#qchips"), null); });

api("/api/session/current").then(({ ok, data }) => {
  if (ok && data && data.state && !data.state.completed) {
    $("#resume-card").hidden = false;
    $("#resume-who").textContent = `${data.state.session.student_alias} · ${data.state.lab_title}`;
  }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (startBtn.disabled) return;
  startBtn.disabled = true;
  try { localStorage.setItem("polarity.bench", $("#bench").value.trim()); } catch (err) { /* ignore */ }
  const { ok, data } = await api("/api/session/start", { method: "POST", json: {
    student_alias: alias.value.trim(), lab_id: labSel.value || cfg.default_lab, bench_id: $("#bench").value.trim() || null } });
  if (ok) {
    location.href = "/bench";
  } else {
    startBtn.disabled = false;
    $("#start-help").textContent = (data && data.message) || "Could not start the session.";
  }
});
update();
