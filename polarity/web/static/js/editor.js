// Lab editor (TA): list labs, compile a handout with Nemotron (Omni reads pages, Super drafts the lab), edit every
// field, save as a draft or publish. AI drafts stay marked "AI-drafted — review before use" until published.
import { $, api, defaultConnection, el, icon, initTopbar, toast } from "./ui.js";
import { connectEvents } from "./ws.js";

initTopbar();
defaultConnection();

let current = null;          // lab being edited (plain object)
let currentSource = null;    // "published" | "draft" | "new"
let uploadId = null;

// ── lab list ──────────────────────────────────────────────────────────────────────────────────
async function loadList() {
  const { ok, data } = await api("/api/labs");
  if (!ok) return;
  $("#lablist").replaceChildren(...data.items.map((l) => el("li", {},
    el("button", { class: "btn btn--ghost btn--block lab-item", type: "button", on: { click: () => openLab(l.id) } },
      el("span", { class: "stack", style: "gap:0;text-align:left" }, el("strong", { text: l.title }),
        el("span", { class: "muted", style: "font-size:13px", text: `${l.id} · ${l.steps} steps · ${l.source}${l.ai_drafted ? " · AI-drafted" : ""}` }))))));
}

async function openLab(id) {
  const { ok, data } = await api(`/api/labs/${encodeURIComponent(id)}`);
  if (!ok) { toast("Could not load that lab.", "error"); return; }
  showForm(data.lab, data.source);
}

// ── form ──────────────────────────────────────────────────────────────────────────────────────
function field(label, value, { textarea = false, rows = 2, key, hint } = {}) {
  const id = `f-${key}-${Math.random().toString(36).slice(2, 8)}`;
  const input = textarea ? el("textarea", { class: "input", id, rows, dataset: { key } }) : el("input", { class: "input", id, dataset: { key } });
  input.value = value ?? "";
  return el("div", { class: "field" }, el("label", { for: id, text: label }), input, hint ? el("span", { class: "help", text: hint }) : null);
}

function checkbox(label, checked, key) {
  const id = `c-${key}-${Math.random().toString(36).slice(2, 8)}`;
  return el("label", { class: "switch", for: id, style: "justify-content:flex-start;gap:8px;font-size:14px" },
    el("input", { type: "checkbox", id, checked: !!checked, dataset: { key } }), el("span", { text: label }));
}

function checkRow(c) {
  return el("div", { class: "subcard check-row" },
    el("div", { class: "row wrap", style: "gap:8px" }, field("Check id", c.id, { key: "id" }),
      checkbox("Required", c.required !== false, "required"), checkbox("Hard to see (allow can't-tell)", c.allow_uncertain, "allow_uncertain"),
      el("button", { class: "btn btn--ghost btn--icon", type: "button", "aria-label": "Remove check", on: { click: (e) => e.currentTarget.closest(".check-row").remove() } }, icon("close"))),
    field("Statement (true when the step is right, visible from above)", c.statement, { key: "statement" }));
}

function errorRow(e) {
  return el("details", { class: "subcard error-row" },
    el("summary", {}, el("strong", { text: e.id || "New mistake" }), el("span", { class: "muted", text: `  ${e.description || ""}` })),
    el("div", { class: "stack", style: "margin-top:8px" },
      el("div", { class: "row wrap", style: "gap:8px" }, field("Error id", e.id, { key: "id" }),
        el("button", { class: "btn btn--ghost", type: "button", on: { click: (ev) => ev.currentTarget.closest(".error-row").remove() } }, icon("close"), "Remove")),
      field("What it looks like", e.description, { key: "description" }),
      field("Visual cue from above", e.visual_cue, { key: "visual_cue" }),
      field("Hint 1 — where to look", e.fix_hint_l1, { key: "fix_hint_l1" }),
      field("Hint 2 — what's wrong", e.fix_hint_l2, { key: "fix_hint_l2" }),
      field("Hint 3 — exact fix", e.fix_hint_l3, { key: "fix_hint_l3" }),
      field("Related check ids (comma separated)", (e.related_checks || []).join(", "), { key: "related_checks" })));
}

function stepCard(s, index) {
  const checks = el("div", { class: "stack checks-box" }, ...(s.checks || []).map(checkRow));
  const errors = el("div", { class: "stack errors-box" }, ...(s.common_errors || []).map(errorRow));
  const led = s.led_check || null;
  const ledBox = el("div", { class: "row wrap led-box", style: "gap:8px" },
    checkbox("Power test: LED should light", !!led, "has_led"),
    field("LED colour", led ? led.colour : "red", { key: "led_colour" }),
    field("Capture instruction", led ? led.instruction_for_capture : "Hold the button down, then press Check.", { key: "led_instruction" }));
  return el("section", { class: "card step-editor", dataset: { index } },
    el("div", { class: "row" }, el("h3", { text: `Step ${index + 1}` }), el("div", { class: "spacer" }),
      el("button", { class: "btn btn--ghost", type: "button", on: { click: (e) => { e.currentTarget.closest(".step-editor").remove(); renumber(); } } }, icon("close"), "Remove step")),
    el("div", { class: "row wrap", style: "gap:8px" }, field("Step id", s.id, { key: "id" }), field("Title", s.title, { key: "title" }),
      field("Illustration file (optional)", s.illustration || "", { key: "illustration" })),
    field("Instruction", s.instruction, { textarea: true, key: "instruction" }),
    field("Capture tip", s.capture_tip || "Keep the whole board inside the four markers.", { key: "capture_tip" }),
    el("h4", { class: "eyebrow", text: "Checks" }), checks,
    el("button", { class: "btn btn--ghost", type: "button", on: { click: () => checks.append(checkRow({ id: "c_new", statement: "", required: true })) } }, "+ Add check"),
    el("h4", { class: "eyebrow", text: "Common mistakes" }), errors,
    el("button", { class: "btn btn--ghost", type: "button", on: { click: () => errors.append(errorRow({})) } }, "+ Add mistake"),
    ledBox);
}

function renumber() {
  document.querySelectorAll(".step-editor").forEach((n, i) => { n.querySelector("h3").textContent = `Step ${i + 1}`; });
}

function showForm(lab, source) {
  current = lab;
  currentSource = source;
  $("#editor-empty").hidden = true;
  $("#form-card").hidden = false;
  $("#form-errors").hidden = true;
  $("#form-title").textContent = lab.title || lab.id;
  $("#draft-badge").hidden = !lab.ai_drafted;
  const steps = el("div", { class: "stack", id: "steps-box" }, ...(lab.steps || []).map(stepCard));
  $("#labform").replaceChildren(
    el("div", { class: "row wrap", style: "gap:8px" }, field("Lab id", lab.id, { key: "id" }), field("Title", lab.title, { key: "title" }), field("Version", lab.version, { key: "version" })),
    field("Summary", lab.summary, { textarea: true, key: "summary" }),
    field("Kit (one item per line)", (lab.kit || []).join("\n"), { textarea: true, rows: 4, key: "kit" }),
    field("Safety notes (one per line)", (lab.safety_notes || []).join("\n"), { textarea: true, rows: 3, key: "safety_notes" }),
    field("Breadboard conventions (sent to the model with every check)", lab.breadboard_conventions, { textarea: true, rows: 4, key: "breadboard_conventions" }),
    steps,
    el("button", { class: "btn", type: "button", on: { click: () => { steps.append(stepCard({ id: `s${steps.children.length + 1}`, title: "", instruction: "", checks: [{ id: "c_new", statement: "" }] }, steps.children.length)); } } }, "+ Add step"));
}

const val = (root, key) => { const n = root.querySelector(`:scope [data-key="${key}"]`); return n ? (n.type === "checkbox" ? n.checked : n.value.trim()) : ""; };
const lines = (text) => text.split("\n").map((t) => t.trim()).filter(Boolean);

function collect() {
  const form = $("#labform");
  const top = (key) => { const n = form.querySelector(`:scope > .row [data-key="${key}"], :scope > .field [data-key="${key}"]`); return n ? n.value.trim() : ""; };
  const steps = Array.from(form.querySelectorAll(".step-editor")).map((sc) => {
    const own = (key) => { const n = sc.querySelector(`:scope > .row [data-key="${key}"], :scope > .field [data-key="${key}"]`); return n ? n.value.trim() : ""; };
    const checks = Array.from(sc.querySelectorAll(".check-row")).map((r) => ({
      id: val(r, "id"), statement: val(r, "statement"), required: val(r, "required"), allow_uncertain: val(r, "allow_uncertain") }));
    const errs = Array.from(sc.querySelectorAll(".error-row")).map((r) => ({
      id: val(r, "id"), description: val(r, "description"), visual_cue: val(r, "visual_cue"), fix_hint_l1: val(r, "fix_hint_l1"),
      fix_hint_l2: val(r, "fix_hint_l2"), fix_hint_l3: val(r, "fix_hint_l3"),
      related_checks: val(r, "related_checks").split(",").map((t) => t.trim()).filter(Boolean) }));
    const led = sc.querySelector('[data-key="has_led"]').checked ? { expect_lit: true, colour: val(sc.querySelector(".led-box"), "led_colour") || "red",
      instruction_for_capture: val(sc.querySelector(".led-box"), "led_instruction") } : null;
    return { id: own("id"), title: own("title"), instruction: own("instruction"), illustration: own("illustration") || null,
      capture_tip: own("capture_tip") || "Keep the whole board inside the four markers.", checks, common_errors: errs, led_check: led };
  });
  return { id: top("id"), title: top("title"), version: top("version") || "0.1", summary: top("summary"),
    kit: lines(top("kit")), safety_notes: lines(top("safety_notes")), breadboard_conventions: top("breadboard_conventions"),
    steps, ai_drafted: current ? !!current.ai_drafted : true };
}

async function save(publish) {
  const lab = collect();
  const { ok, data } = await api(`/api/labs/${encodeURIComponent((current && current.id) || lab.id)}`, { method: "PUT", json: { lab, publish } });
  const box = $("#form-errors");
  if (!ok) {
    box.hidden = false;
    box.replaceChildren(el("strong", { text: "Please fix these before saving:" }),
      el("ul", {}, ...String(data.message || "Invalid lab").split("; ").map((m) => el("li", { text: m }))));
    box.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  box.hidden = true;
  current = { ...lab, ai_drafted: publish ? false : lab.ai_drafted };
  $("#draft-badge").hidden = !current.ai_drafted;
  toast(publish ? `Published ${data.lab_id} — students can pick it now.` : `Draft ${data.lab_id} saved.`, "ok");
  loadList();
}

// ── compile ───────────────────────────────────────────────────────────────────────────────────
async function startUpload(form) {
  $("#compile-card").hidden = false;
  $("#progress").replaceChildren(el("li", { text: "Reading the file…" }));
  const { ok, data } = await api("/api/labs/compile", { method: "POST", form });
  if (!ok) { $("#progress").replaceChildren(el("li", { class: "tone-danger", text: data.message || "Upload failed." })); return; }
  uploadId = data.upload_id;
  $("#pages").replaceChildren(...data.pages.map((src, i) => el("figure", { class: "page-thumb" }, el("img", { src, alt: `Page ${i + 1}` }), el("figcaption", { text: `Page ${i + 1}` }))));
  const e = data.estimate;
  $("#estimate").textContent = `${e.pages} page${e.pages > 1 ? "s" : ""} · ${e.calls} model calls · ~${e.tokens_estimate.toLocaleString()} tokens · cost ${e.cost_estimate_usd === null ? "n/a (fill pricing.yaml)" : "$" + e.cost_estimate_usd.toFixed(3)}`;
  $("#progress").replaceChildren(el("li", { text: "Ready. Check the estimate, then compile." }));
  $("#compile-btn").disabled = false;
}

$("#upload-input").addEventListener("change", (e) => {
  const files = Array.from(e.target.files || []);
  if (!files.length) return;
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  startUpload(form);
  e.target.value = "";
});
$("#sample-btn").addEventListener("click", () => { const form = new FormData(); form.append("sample", "true"); startUpload(form); });
$("#compile-btn").addEventListener("click", async (e) => {
  if (!uploadId) return;
  e.currentTarget.disabled = true;
  const form = new FormData();
  form.append("upload_id", uploadId);
  form.append("confirm", "true");
  const { ok, data } = await api("/api/labs/compile", { method: "POST", form });
  if (!ok) toast(data.message || "Could not start compiling.", "error");
});
$("#save-btn").addEventListener("click", () => save(false));
$("#publish-btn").addEventListener("click", () => save(true));

connectEvents({
  compile_progress: (p) => {
    if (p.upload_id !== uploadId) return;
    const text = p.stage === "page" ? `Reading page ${p.page} of ${p.total} with Nano Omni…` : p.stage === "assemble" ? "Drafting steps with Nemotron Super…" : "Done.";
    $("#progress").append(el("li", { text }));
  },
  compile_done: (r) => {
    if (r.upload_id !== uploadId) return;
    toast("Draft ready — review every field before publishing.", "ok");
    showForm(r.lab, "draft");
    $("#form-card").scrollIntoView({ behavior: "smooth", block: "start" });
    loadList();
  },
  compile_failed: (r) => {
    if (r.upload_id !== uploadId) return;
    $("#progress").append(el("li", { class: "tone-danger", text: `Failed: ${r.message}` }));
    $("#compile-btn").disabled = false;
  },
});
loadList();
