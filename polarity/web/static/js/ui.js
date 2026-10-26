// Shared UI helpers. All text from the server (model output, aliases, lab text) is inserted with textContent,
// never innerHTML, so model or student input can never inject markup.
import { tts } from "./tts.js";

export const boot = JSON.parse(document.getElementById("boot").textContent || "{}");
export const cfg = boot.config || {};

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "on") for (const [ev, fn] of Object.entries(value)) node.addEventListener(ev, fn);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "style") node.setAttribute("style", value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function icon(name, cls = "icon") {
  const src = document.querySelector(`#icon-defs [data-icon="${name}"] svg`);
  if (!src) return document.createTextNode("");
  const svg = src.cloneNode(true);
  svg.setAttribute("class", cls);
  return svg;
}

export async function api(path, { method = "GET", json, form, headers = {} } = {}) {
  const init = { method, headers: { ...headers }, credentials: "same-origin" };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form;
  }
  try {
    const res = await fetch(path, init);
    let data = null;
    const type = res.headers.get("content-type") || "";
    if (type.includes("application/json")) data = await res.json();
    else data = await res.text();
    if (!res.ok && (data === null || typeof data !== "object")) data = { error: "http", message: `HTTP ${res.status}` };
    if (!res.ok && data && data.detail && !data.message) data.message = typeof data.detail === "string" ? data.detail : "Request failed";
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: { error: "network", message: "Can't reach the bench server." } };
  }
}

export function toast(message, kind = "ok", ms = 4200) {
  const box = document.getElementById("toasts");
  if (!box) return;
  const names = { ok: "pass", warn: "fix", error: "fix", info: "spark" };
  const node = el("div", { class: `toast toast--${kind}`, role: kind === "error" ? "alert" : "status" }, icon(names[kind] || "spark"), el("span", { text: message }));
  box.append(node);
  setTimeout(() => node.remove(), ms);
}

const store = {
  get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : v; } catch (e) { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode */ } },
};
export { store };

export const theme = {
  get() { return document.documentElement.dataset.theme || "dark"; },
  set(t) { document.documentElement.dataset.theme = t; store.set("polarity.theme", t); },
};

export function initTopbar() {
  const btn = $("#settings-btn");
  const menu = $("#settings-menu");
  if (!btn || !menu) return;
  const close = () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); };
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    btn.setAttribute("aria-expanded", String(!menu.hidden));
  });
  document.addEventListener("click", (e) => { if (!menu.contains(e.target) && e.target !== btn) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

  const themeBox = $("#set-theme");
  themeBox.checked = theme.get() === "light";
  themeBox.addEventListener("change", () => theme.set(themeBox.checked ? "light" : "dark"));

  const voiceOn = $("#set-voice-on");
  voiceOn.checked = !tts.muted && cfg.speak_feedback !== false;
  if (!tts.supported) { voiceOn.disabled = true; voiceOn.checked = false; }
  voiceOn.addEventListener("change", () => tts.setMuted(!voiceOn.checked));

  const voiceSel = $("#set-voice");
  const fillVoices = () => {
    const current = tts.voiceURI;
    voiceSel.replaceChildren(el("option", { value: "", text: "Browser default" }));
    for (const v of tts.voices()) voiceSel.append(el("option", { value: v.voiceURI, text: `${v.name} (${v.lang})`, selected: v.voiceURI === current }));
  };
  fillVoices();
  if (tts.supported) window.speechSynthesis.addEventListener?.("voiceschanged", fillVoices);
  voiceSel.addEventListener("change", () => tts.setVoice(voiceSel.value));
  // The first click anywhere unlocks speech in Safari.
  document.addEventListener("pointerdown", () => tts.unlock(), { once: true });
}

export function setConnection(kind, text) {
  const pill = $("#conn-pill");
  if (!pill) return;
  pill.className = `pill ${{ ok: "pill--ok", mock: "pill--mock", off: "pill--off", warn: "pill--warn" }[kind] || ""}`;
  pill.textContent = text;
}

export function defaultConnection() {
  if (cfg.mock) return setConnection("mock", "MOCK MODE");
  if (!cfg.has_key) return setConnection("off", "No API key");
  if (!cfg.capabilities_verified) return setConnection("warn", "Run verify first");
  return setConnection("ok", "Token Factory · connected");
}

export const STATUS = {
  pass: { icon: "pass", word: "PASS", tone: "pass" },
  pass_partial: { icon: "partial", word: "PASS", tone: "pass" },
  fix: { icon: "fix", word: "FIX", tone: "fix" },
  uncertain: { icon: "uncertain", word: "CAN'T TELL", tone: "uncertain" },
};

export const CHECK_RESULT = {
  pass: { icon: "pass", word: "Looks right", tone: "pass" },
  fail: { icon: "fix", word: "Fix", tone: "fix" },
  not_visible: { icon: "uncertain", word: "Can't see", tone: "uncertain" },
};

export const CHIPS = [
  { key: "light", label: "Light", icon: "light" },
  { key: "focus", label: "Focus", icon: "focus" },
  { key: "glare", label: "Glare", icon: "glare" },
  { key: "board", label: "Board found", icon: "markers" },
  { key: "steady", label: "Steady", icon: "steady" },
];

// board: {found, markers, ids, mode, note} from the edge monitor; explains a red "Board found" chip.
export function renderChips(container, chips, board) {
  container.replaceChildren(...CHIPS.map(({ key, label, icon: ic }) => {
    const known = chips && key in chips;
    const ok = known && chips[key];
    const cls = !known ? "is-unknown" : ok ? "is-ok" : "is-bad";
    const stateIcon = !known ? "uncertain" : ok ? "pass" : "fix";
    let text = label;
    let why = "";
    if (key === "board" && board && board.mode === "markers") {
      if (known && !ok) text = `Board ${board.markers}/4`;
      why = board.note || "";
    }
    const attrs = { class: `qchip ${cls}`, role: "status",
                    "aria-label": `${label}: ${!known ? "waiting" : ok ? "OK" : "needs attention"}${why ? ` (${why})` : ""}` };
    if (why) attrs.title = why;
    return el("span", attrs, icon(ic), el("span", { text }), el("span", { class: "state" }, icon(stateIcon)));
  }));
}

export function fmtSeconds(total) {
  if (total === null || total === undefined) return "–";
  const s = Math.max(0, Math.round(total));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${String(s % 60).padStart(2, "0")} s`;
}

export function timeAgo(iso) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return `${Math.floor(s / 3600)} h ago`;
}

export function inTextField(target) {
  const t = target && target.tagName;
  return t === "INPUT" || t === "TEXTAREA" || t === "SELECT" || (target && target.isContentEditable);
}
