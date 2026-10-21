# POLARITY — Master Build Prompt

**Nebius x NVIDIA Global AI Hackathon · Physical AI Track**
**Build specification for an AI coding agent (Claude Code or similar)**

---

## HOW TO USE THIS FILE (for the humans)

1. Create an empty folder called `polarity` and put this file inside it as `BUILD_PROMPT.md`.
2. Open Claude Code in that folder and say:
   **"Read BUILD_PROMPT.md completely before writing any code. Then execute every phase in order, obeying Section 0 exactly. Do not skip acceptance checks."**
3. When Claude Code creates `.env.example`, copy it to `.env` and paste your `NEBIUS_API_KEY` (and optionally `TAVILY_API_KEY`). Phase 0 needs the key to run live; everything else can be built and tested in mock mode without it.
4. Things only humans can do (Claude Code will remind you in its final report):
   - print the marker mat,
   - build the rig (camera above the breadboard),
   - photograph the evaluation dataset,
   - confirm the TA-ratio fact with a real lab TA,
   - record the demo video.

---

## 0. OPERATING RULES FOR THE CODING AGENT (read first, obey always)

1. **Role.** You are the lead engineer for a hackathon team. Deliver a complete, working, demo-ready, well-documented repository. Not a prototype skeleton, not TODO stubs.
2. **Phases.** Execute Phases 0 → 7 in order.
   - Each phase ends with acceptance checks. Run them, fix until they pass.
   - Then `git commit -m "phase N: <summary>"`.
   - Initialise git in Phase 0 if needed.
3. **Never fake anything.**
   - No hardcoded model outputs in the live path.
   - No invented metrics.
   - No claimed capability that the Phase 0 report did not confirm.
   - Mock behaviour exists ONLY behind `POLARITY_MOCK_MODELS=1`. The UI must then show a clearly visible amber "MOCK MODE — not real AI output" badge on every screen.
4. **Do not stop to ask questions.** When information is missing:
   - choose the most reasonable option and implement it;
   - log it in `docs/DECISIONS.md` (date, decision, reason, how to change it).

   Only pause the *live* parts of a phase for:
   - (a) a missing secret. Continue building in mock mode and mark the live checks "PENDING — needs NEBIUS_API_KEY".
   - (b) any action that would modify files outside the repo.
5. **Cross-platform is mandatory.** Targets: macOS 13+ (Apple Silicon and Intel), Windows 10/11 x64, and Linux (Raspberry Pi 5 / Jetson) as a bonus.
   - Use `pathlib` everywhere.
   - No shell-specific calls from Python except clearly guarded OS-specific helpers.
   - Every user-facing script exists as both `.sh` (macOS/Linux) and `.ps1` + `.bat` (Windows).
   - No symlinks.
   - Always open text files with `encoding="utf-8"`.
   - Add `.gitattributes` for line endings.
   - Only use packages that ship wheels for macOS arm64/x86_64 and Windows x64 on Python 3.11 and 3.12.
6. **Secrets.**
   - Read only from environment / `.env` (python-dotenv).
   - `.env` is gitignored.
   - Never print a full key; mask to `****abcd`.
   - Never commit keys, never log request headers.
7. **Cost discipline.**
   - Every model call goes through `ModelRouter`, which records model ID, latency, token usage and estimated cost.
   - A budget guard stops calls when the configured session or day budget is exceeded, and shows a clear UI message.
8. **Robust live demo.** Every network call has:
   - a timeout,
   - retries with exponential backoff and jitter (max 2 retries for interactive calls),
   - a friendly UI state on failure.

   The camera loop must never crash the server.
9. **Code quality.**
   - Type hints throughout.
   - Pydantic v2 models for all LLM inputs and outputs.
   - Small focused modules, docstrings on public functions.
   - `ruff check` clean.
   - `pytest` green in mock mode on all three OSes (CI provided in Phase 7).
10. **Final report.** Finish with the report in Section 17.

---

## 1. HACKATHON CONTEXT AND NON-NEGOTIABLE COMPLIANCE

Confirmed from the official Devpost page, Official Rules and FAQ:

- **Platform requirement.** The project must make runtime calls to Nebius Token Factory (or run on Nebius AI Cloud) and use at least one NVIDIA open-source model.
  - Calling NVIDIA models through another provider (HuggingFace, OpenRouter, etc.) does NOT count.
  - Our compliance: every perception and reasoning call goes to Token Factory using NVIDIA Nemotron models.
- **Track:** Physical AI. Embodied/edge agents that sense and act in the real world, coordinated through an agent runtime.
- **Video.** Public YouTube, under 3 minutes, showing the project working and how Token Factory and Nemotron are used.
  - Physical AI needs at least 1 minute of footage of the hardware actually operating.
  - No copyrighted music or third-party material without permission.
- **Repository.** Public GitHub. Must include:
  - an open-source license detectable at the top of the repo page — use **MIT**, file `LICENSE` at root;
  - a README with setup instructions;
  - a clear section on how NVIDIA Nemotron and Token Factory are used, and any other Nebius tools.
- **Demo URL.** Not required for Physical AI. We still ship a no-hardware "demo mode" so judges can run it.
- **Feedback.** The submission must include feedback on Token Factory, AI Cloud and NVIDIA tools. There is a separate "Most Valuable Feedback" prize, so draft `docs/FEEDBACK.md` from real Phase 0 findings.
- **Judging.** Four equally weighted criteria:
  - Technological Implementation
  - Design
  - Potential Impact
  - Quality of the Idea

  The tie-break order starts with Technological Implementation. Stage 1 is pass/fail: a genuine attempt at the track goal that genuinely uses the required APIs.
- **Credits.** The promo credits are Token Factory credits only. There are NO AI Cloud credits, so the build must NOT depend on Nebius Serverless Endpoints, Serverless Jobs or DevPods.
- **Bonus prize: Best Use of Tavily.** Requires a functional runtime call to the Tavily API. Implemented in Phase 5 as the part/datasheet lookup tool.
- **Deadline.** Fri 30 Oct 2026, 10:00 PDT = **Sat 31 Oct 2026, 01:00 Singapore time**. Team internal deadline: **Thu 29 Oct 23:59 SGT**.
- **Language.** All materials in English.

---

## 2. PRODUCT BRIEF

**Name:** Polarity. This is a working name, defined once as `APP_NAME` in config so it can be renamed in one place.

**Tagline:** "An AI lab partner that catches wiring mistakes before the circuit fails, and shows the TA where the class is stuck."

**Primary user.** A first-year engineering/electronics student building their first breadboard circuits in a teaching lab.

**Secondary user.** The lab teaching assistant (TA) who supervises a whole class at once.

**The problem.**
- Beginner wiring mistakes stay invisible until power-on:
  - LED reversed,
  - resistor legs in the same strip (shorted out),
  - push button not straddling the centre channel,
  - power leads swapped.
- When the circuit fails, the student has to debug everything at once.
- The TA is the bottleneck: they can only look at one bench at a time.
- The TA has no class-level view of which step everyone struggles with.

> **TODO-VERIFY (humans):** Ask a real SIT lab TA how many students one TA supervises, and get a one-line quote. Do not write any specific ratio such as "1 TA per 30 students" in the README, pitch or video until it is confirmed. Use the placeholder `{{TA_RATIO_CONFIRMED}}` and leave a visible TODO.

**The solution.** A bench device (camera above the breadboard, plus the bench computer's mic and speaker) that:

1. walks the student through the lab one step at a time;
2. verifies each step from what the camera sees and gives structured verdicts with visual evidence;
3. explains the fix by voice using a hint ladder (nudge first, exact fix last);
4. honestly says **"I can't tell"** with a specific retake instruction when the image isn't good enough;
5. answers the student's spoken questions about the current step;
6. objectively confirms the final power-on test by detecting the lit LED on-device;
7. feeds a live TA dashboard (help queue + class heatmap) and an end-of-class AI report.

**The non-obvious design choices (these are the pitch — make them visible in the UI):**

1. **A step verifier, not a chatbot.** A deterministic state machine drives the session. The model returns structured, schema-validated judgments per check. Code, not the model, decides pass/fix/uncertain.
2. **Calibrated honesty.**
   - An edge quality gate (blur, light, glare, board found, steadiness) runs before any cloud call.
   - The model must mark checks "not_visible" rather than guess.
   - A self-consistency second look runs in the confidence grey zone.
   - The result is "CAN'T TELL" plus a specific retake instruction.
3. **Edge/cloud split.** The edge does continuous perception for free:
   - ArUco board localisation and top-down warp,
   - quality metrics,
   - motion,
   - LED-lit detection.

   The cloud (Token Factory) is called only when the student presses Check or asks a question.
4. **Physical ground truth.** At power-on, an on-device LED-lit detector cross-checks the AI. A fail cannot be talked into a pass.
5. **Pedagogy.** Hint ladder per step (level 1 = where to look, level 2 = what's wrong, level 3 = exact fix).
6. **Class-level insight.** TA heatmap of steps × students, a help queue with AI-written summaries, and an end-of-class report from Nemotron Ultra.
7. **Any lab, not just ours (P1).** A TA uploads a lab-sheet PDF and Nano Omni reads it (document understanding is its strength). Super compiles it into a verifiable step definition the TA reviews before publishing.

**Scope priorities.**
- **P0 (must ship):**
  - Phase 0;
  - the core engine (Phase 1);
  - edge runtime (Phase 2);
  - Bench UI and TA dashboard (Phase 3);
  - help queue, report and seeded class demo (Phase 4);
  - tests and eval harness (Phase 6);
  - setup scripts, docs and submission package (Phase 7).
- **P1 (should ship):**
  - lab-sheet compiler;
  - Tavily part lookup;
  - whole-board "bug hunt" audit;
  - hub mode for multiple benches.
- **P2 (nice to have):**
  - Raspberry Pi/Jetson packaging notes;
  - Lab 2 (soldering) template;
  - multilingual voice.

---

## 3. PHYSICAL SETUP (hardware-flexible by design)

**Minimum (must work):**
- any macOS or Windows laptop;
- its built-in camera, or any USB webcam, mounted roughly top-down over the breadboard (phone stand, gooseneck clamp, or taped to a shelf);
- any desk lamp.

**Recommended:**
- a 1080p USB webcam on a gooseneck, 25–35 cm above the board;
- a small LED ring light;
- the printed marker mat.

**Phone as camera (allowed):** macOS Continuity Camera, or DroidCam/Camo on Windows. It appears as a normal camera index.

**Optional edge boards:** Raspberry Pi 5 (8 GB) or NVIDIA Jetson Orin Nano running Linux. Same code, documented in `docs/EDGE_DEVICES.md` (P2).

**Marker mat:**
- 4 ArUco markers from `DICT_4X4_50`, IDs 0 (top-left), 1 (top-right), 2 (bottom-right), 3 (bottom-left), each 30 mm.
- Printed on A4 around a rectangle sized for a half-size (400-point) breadboard.
- Generated by `python -m polarity markers` → `assets/print/marker_mat_A4.pdf` and `.png`.
- Include a 1 cm scale bar for print-size verification.
- If markers are disabled (`MARKERS_ENABLED=false`), fall back to a configurable fixed ROI.

**Lab 1 kit (default content; low voltage only):**
- half-size breadboard;
- 2×AA battery holder with on/off switch and red/black leads (3 V);
- 1 × 5 mm red LED;
- 1 × 100 Ω resistor (brown-black-brown);
- 1 × 6×6 mm 4-pin tactile push button;
- jumper wires (red, black, any other colour).

A config variant `lab1_5v` uses a 5 V USB breadboard power module and a 220 Ω resistor (red-red-brown).

> **TODO-VERIFY (humans):** Build Lab 1 physically once and adjust `labs/lab1.yaml` if your kit differs. The circuit must actually light the LED when the button is pressed.

**Safety note** (README + start screen): batteries and USB power only. Never mains. If anything gets hot, smells, or smokes: switch off and call the TA.

---

## 4. ARCHITECTURE

### 4.1 Diagram

```
 ┌──────────────────────────── BENCH COMPUTER (edge) ────────────────────────────┐
 │                                                                                │
 │  USB camera ──► CameraService (OpenCV thread, ring buffer, MJPEG)              │
 │                     │                                                          │
 │                     ▼                                                          │
 │   BoardLocator (ArUco → homography → 1024×768 top-down warp)                   │
 │                     │                                                          │
 │        ┌────────────┼──────────────┬─────────────────┐                         │
 │        ▼            ▼              ▼                 ▼                         │
 │   QualityGate   MotionMonitor   LedDetector    Snapshot store                  │
 │        │            │              │                 │                         │
 │        └────────────┴──────┬───────┴─────────────────┘                         │
 │                            ▼                                                   │
 │          SessionEngine (state machine · hint ladder · escalation)              │
 │                            │                                                   │
 │                            ▼                                                   │
 │       ModelRouter (roles → model IDs, retries, budget, cost log)               │
 │                            │ only on "Check" / "Ask"                           │
 │  FastAPI + WebSocket ◄─────┤                                                   │
 │        ▲                   │                                                   │
 │        │                   ▼                                                   │
 │  Browser UI (localhost) ─ mic (Web Audio → 16 kHz WAV), voice (speechSynthesis)│
 │  Bench view · TA view · Lab editor · Debug                                     │
 │  SQLite + local media (images never leave the bench except the checked frame)  │
 └────────────────────────────┬───────────────────────────────────────────────────┘
                              │ HTTPS (OpenAI-compatible API)
          ┌───────────────────┴───────────────────────────┐
          ▼                                               ▼
  Nebius Token Factory                              Tavily API (P1)
  · Nemotron 3 Nano Omni  (perception: image+audio)  part / datasheet lookup
  · Nemotron 3 Nano 30B   (fast text)
  · Nemotron 3 Super 120B (reasoning, tools)
  · Nemotron 3 Ultra      (deep class report)
```

Also produce this as a Mermaid diagram in `docs/ARCHITECTURE.md` and as a clean SVG at `assets/architecture.svg` for the README and video.

### 4.2 Model routing

| Role key | Resolved model (from Phase 0) | Used for | How often |
|---|---|---|---|
| `perception` | Nemotron 3 Nano Omni | Step verification (image ± student audio), voice Q&A, reading lab-sheet pages, reading chip markings | Every Check / Ask |
| `fast_text` | Nemotron 3 Nano 30B (text) | Intent classification of student questions, shortening long spoken feedback | Occasional, cheap |
| `reasoning` | Nemotron 3 Super 120B | TA help-request diagnosis from attempt history, lab-compiler structuring, Tavily tool agent | Per escalation |
| `deep` | Nemotron 3 Ultra | End-of-class TA report | ~Once per class |

- **Fallback chain:** `deep → reasoning → fast_text`.
- `perception` has no text fallback. If it fails, the UI shows "I couldn't check that right now — try again" with a retry button, and logs the error.
- If Phase 0 finds no Nano Omni but finds a Nemotron Nano VL model, use it for `perception` and set the flag `perception_fallback_vl=true` (audio then follows AUDIO_MODE fallbacks).
- Show the routing table in the Debug panel and the README. It is a key Technological Implementation story: cheap/fast models for frequent calls, heavy models only where they earn it.

### 4.3 The "Check my step" sequence (core loop)

1. Student presses **Check** (button or Space). Optionally they hold **V** or the mic button to speak a question first. The audio is attached to the same check.
2. Edge:
   - take the sharpest frame from the last ~1 s of the ring buffer;
   - run BoardLocator → warped top-down image;
   - run QualityGate on the warped image (or the ROI).
   - If the gate fails → return immediately with a local **CAN'T TELL** and a specific retake instruction. No cloud call. Log the attempt with `status=uncertain, reason=quality:<metric>`.
3. If the step has `led_check`, run LedDetector against the step's baseline frame.
4. Build the perception request:
   - system prompt (Section 9.5.1);
   - step spec JSON (checks, common errors, hint level);
   - the warped image as JPEG (≤1280 px long side, quality 85);
   - student audio WAV, if present and AUDIO_MODE allows.
5. Call ModelRouter (`perception`, JSON mode per capabilities). Validate with Pydantic; one repair attempt if invalid (Section 9.7).
6. Decision policy (deterministic code, Section 9.4) → final status.
   - If confidence is in the grey zone → second look (zoomed crop, Section 9.4).
   - If led_check exists → apply the physical cross-check.
7. Persist the attempt (images, audio, verdict, model, latency, tokens, cost). Emit a WebSocket event. The UI renders the verdict card and the browser speaks `spoken_feedback` (captions always visible).
8. State machine:
   - pass → advance;
   - fix → increment the fix count and hint level;
   - uncertain → keep the step and show the retake instruction.

   Then evaluate escalation rules (Section 12.1).

### 4.4 Capability-adaptive strategies (driven by `data/capabilities.json` from Phase 0)

- **`AUDIO_MODE`:**
  - `omni_combined`: image + audio in one perception call (preferred);
  - `omni_separate`: an audio-only perception call returns the transcript and intent, then the text goes into the image call;
  - `browser_stt`: Web Speech API recognition in the browser (Chrome/Edge), text only;
  - `typed`: a text box.

  Auto-select the best mode Phase 0 verified. Allow an override in `.env`.
- **`JSON_MODE`:** `json_schema` | `json_object` | `prompt_only`.
- **`TOOLS_MODE`:** `native` (OpenAI tools on Super) | `manual` (code calls Tavily, then Super summarises).
- **`THINKING_CONTROL`:**
  - `chat_template_kwargs` (extra_body `{"chat_template_kwargs": {"enable_thinking": false}}`);
  - `system_flag` (`/no_think` in the system prompt);
  - `none`.

  Use whichever Phase 0 confirmed reduces latency without breaking output. Enable thinking only for `deep`.
- **`MODEL_ID_CASE`:** `exact` | `lowercase`, recorded per model.

---

## 5. TECH STACK AND CROSS-PLATFORM RULES

**Python:** 3.12 recommended, 3.11 supported. **Not 3.13.**

**Runtime dependencies** (`requirements.txt` uses lower bounds; after a successful install, write `requirements.lock.txt` via `pip freeze` for reproducibility):

```
openai>=1.40
python-dotenv>=1.0
pydantic>=2.6
pydantic-settings>=2.2
fastapi>=0.110
uvicorn[standard]>=0.29
jinja2>=3.1
python-multipart>=0.0.9
typer>=0.12
rich>=13.7
httpx>=0.27
numpy>=1.26
pillow>=10.2
opencv-contrib-python>=4.8   # NOT opencv-python alongside it — they conflict
pyyaml>=6.0
markdown>=3.6
pypdfium2>=4.28
tavily-python>=0.3
```

- **Dev** (`requirements-dev.txt`): `pytest>=8`, `ruff>=0.4`.
- **Optional extra** (`requirements-audio.txt`): `sounddevice>=0.4` (only for `verify --record`).

**Frontend:**
- No build step and no Node required.
- Vanilla ES modules + one handwritten CSS file (design tokens in Section 11).
- No CDN dependencies; everything is served locally.
- System font stack.
- The app must work with internet access only to Token Factory/Tavily.

**Database:** SQLite (stdlib `sqlite3`), WAL mode, file `data/polarity.db`.

**Server:**
- FastAPI + uvicorn on `127.0.0.1:8765` by default. If the port is busy, auto-pick the next free one.
- `--lan` binds `0.0.0.0` (hub mode).
- `--open-browser` opens the default browser.

**Packaging:**
- `pyproject.toml` defines the package and the console script `polarity`.
- Setup scripts run `pip install -r requirements.txt` then `pip install -e .`.
- `python -m polarity <command>` must always work.

**OS specifics:**
- **Camera backend:**
  - Windows: `cv2.CAP_DSHOW` first, then `cv2.CAP_MSMF`;
  - macOS: `cv2.CAP_AVFOUNDATION`;
  - Linux: `cv2.CAP_V4L2`.

  On Windows, request the `MJPG` fourcc for 1080p at 30 fps on USB cams.
- **Console:** set `PYTHONIOENCODING=utf-8` in run scripts. Use `rich` for output. Avoid printing raw emoji on Windows consoles that can't render them.
- **macOS permissions:** document camera and mic permission for Terminal/iTerm/VS Code (System Settings → Privacy & Security → Camera / Microphone).
- **Windows permissions:** document Settings → Privacy & security → Camera → "Let desktop apps access your camera".
- **Browser:** Chrome or Edge recommended (Web Audio, speechSynthesis and optional SpeechRecognition all work). Safari supported for the core flow; TTS needs one click first to unlock audio.

---

## 6. REPOSITORY STRUCTURE (create exactly this, adding files as needed)

```
polarity/
├── BUILD_PROMPT.md                 # this file (keep)
├── README.md
├── LICENSE                         # MIT, copyright "2026 The Polarity Team"
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── requirements-audio.txt
├── .env.example
├── .gitignore                      # .env, .venv/, data/polarity.db*, data/media/, __pycache__/, *.pyc, .ruff_cache/, .pytest_cache/
├── .gitattributes                  # * text=auto eol=lf ; *.ps1 *.bat text eol=crlf ; *.png *.jpg *.pdf *.wav *.mp4 binary
├── .github/workflows/ci.yml
├── config/
│   ├── settings.yaml               # non-secret defaults (thresholds, budgets, UI)
│   └── pricing.yaml                # per-model $/1M tokens (team fills from console)
├── labs/
│   ├── lab1.yaml                   # default breadboard lab (3 V)
│   ├── lab1_5v.yaml                # variant
│   └── lab2_solder_template.yaml   # P2 template, mostly allow_uncertain
├── polarity/
│   ├── __init__.py
│   ├── __main__.py                 # Typer CLI entry
│   ├── cli.py                      # commands: verify, doctor, run, devices, markers, calibrate, capture, eval, seed-demo, purge, render-synthetic
│   ├── config.py                   # pydantic-settings; merges .env + settings.yaml + capabilities.json
│   ├── logging_setup.py
│   ├── models/                     # pydantic schemas
│   │   ├── lab.py                  # LabDefinition, Step, Check, CommonError, LedCheck
│   │   ├── verdict.py              # PerceptionVerdict, CheckResult, FinalVerdict
│   │   ├── session.py              # Session, Attempt, HelpRequest, Report
│   │   └── capabilities.py
│   ├── llm/
│   │   ├── client.py               # OpenAI client factory (base URL, key, timeouts)
│   │   ├── resolver.py             # model discovery + case fallback
│   │   ├── router.py               # ModelRouter (roles, retries, budget, cost)
│   │   ├── payloads.py             # content-part builders: image, audio (variants), video
│   │   ├── jsonio.py               # extract/repair/validate JSON; strip <think> & reasoning
│   │   ├── prompts.py              # all system prompts (Section 9.5) as constants
│   │   └── mock.py                 # mock responses (only when POLARITY_MOCK_MODELS=1)
│   ├── edge/
│   │   ├── camera.py               # CameraService + DemoCameraSource
│   │   ├── board.py                # BoardLocator (ArUco + homography + ROI fallback)
│   │   ├── quality.py              # QualityGate
│   │   ├── motion.py               # MotionMonitor
│   │   ├── led.py                  # LedDetector
│   │   └── markers.py              # marker mat generator
│   ├── engine/
│   │   ├── session_engine.py       # state machine, hint ladder, escalation
│   │   ├── verifier.py             # check pipeline (Section 4.3)
│   │   ├── decision.py             # deterministic decision policy
│   │   ├── voice_qa.py
│   │   ├── diagnosis.py            # Super: help-request summary
│   │   ├── report.py               # Ultra: class report
│   │   ├── lab_compiler.py         # P1
│   │   ├── board_audit.py          # P1 bug hunt
│   │   └── parts.py                # P1 Tavily part lookup
│   ├── storage/
│   │   ├── db.py                   # schema, migrations, repository functions
│   │   └── media.py
│   ├── hub/
│   │   └── client.py               # P1 bench→hub sync
│   ├── verify/
│   │   ├── run_verify.py           # Phase 0 implementation
│   │   └── assets.py               # test asset generation (image/audio/video)
│   ├── demo/
│   │   ├── seed.py                 # simulated class data (flagged)
│   │   └── synthetic_board.py      # PIL renderer for placeholder board images
│   └── web/
│       ├── app.py                  # FastAPI app factory, routes, websocket
│       ├── events.py               # event bus
│       ├── templates/              # base.html, bench.html, ta.html, editor.html, debug.html, start.html
│       └── static/
│           ├── css/polarity.css
│           ├── js/ (bench.js, ta.js, editor.js, debug.js, ws.js, audio.js, tts.js, ui.js)
│           └── img/ (logo.svg, step illustrations *.svg, icons *.svg)
├── scripts/
│   ├── setup_mac.sh   run_mac.sh   verify_mac.sh
│   ├── setup_windows.ps1   setup_windows.bat
│   ├── run_windows.ps1     run_windows.bat
│   ├── verify_windows.bat
│   └── verify_token_factory.py     # standalone Phase 0 script (thin wrapper)
├── data/
│   ├── capabilities.json           # written by Phase 0 (gitignored copy + committed example)
│   ├── demo/lab1/                  # synthetic placeholder images per step/label (+ team's real photos later)
│   ├── eval/lab1/                  # evaluation dataset (team photos)
│   └── media/                      # runtime captures (gitignored)
├── tests/
│   ├── conftest.py
│   ├── assets/                     # tiny generated fixtures
│   └── test_*.py
├── tools/
│   └── (dev helpers if needed)
├── assets/
│   ├── architecture.svg
│   └── print/marker_mat_A4.pdf
└── docs/
    ├── ARCHITECTURE.md   DECISIONS.md   PHASE0_REPORT.md   EVAL_RESULTS.md
    ├── DEMO_SCRIPT.md    DEVPOST.md     FEEDBACK.md        PRIVACY.md
    ├── EDGE_DEVICES.md   TEAM_TODO.md
```

---

## 7. CONFIGURATION

### 7.1 `.env.example` (create with exactly these keys and comments)

```
# ── Nebius Token Factory ─────────────────────────────────────────
NEBIUS_API_KEY=
# Leave blank to auto-probe known endpoints in Phase 0 (result saved to data/capabilities.json)
NEBIUS_BASE_URL=

# Optional manual model overrides (otherwise discovered from /models in Phase 0)
POLARITY_MODEL_PERCEPTION=
POLARITY_MODEL_FAST_TEXT=
POLARITY_MODEL_REASONING=
POLARITY_MODEL_DEEP=

# ── Tavily (P1, Best Use of Tavily bonus) ─────────────────────────
TAVILY_API_KEY=

# ── Runtime ──────────────────────────────────────────────────────
POLARITY_MOCK_MODELS=0          # 1 = canned responses, shows MOCK MODE badge
CAMERA_SOURCE=opencv            # opencv | demo
CAMERA_INDEX=0
CAMERA_WIDTH=1920
CAMERA_HEIGHT=1080
MARKERS_ENABLED=true
AUDIO_MODE=auto                 # auto | omni_combined | omni_separate | browser_stt | typed
DEFAULT_LAB=lab1
PORT=8765
TA_PIN=2468                     # protects TA routes; change before demo

# ── Budget guard (USD, estimated from config/pricing.yaml) ──────
BUDGET_SESSION_USD=1.00
BUDGET_DAY_USD=5.00

# ── Privacy ──────────────────────────────────────────────────────
MEDIA_RETENTION_DAYS=14
```

### 7.2 `config/settings.yaml` defaults

```yaml
quality:
  blur_var_min: 80.0          # variance of Laplacian on 1024-wide gray warped image
  brightness_min: 70
  brightness_max: 200
  glare_ratio_max: 0.02       # fraction of pixels >= 250
  markers_min: 3
  motion_max: 6.0             # mean abs diff between frames over 0.5 s (0–255 scale)
decision:
  pass_min_conf: 0.75
  fix_min_conf: 0.60
  grey_zone: [0.50, 0.80]     # trigger second look when final confidence falls here
led:
  min_area_px: 25
  max_area_px: 4000
  v_delta_min: 45             # brightness increase vs baseline
  red_hue_ranges: [[0, 12], [165, 180]]
  s_min: 70
images:
  max_long_side: 1280
  jpeg_quality: 85
audio:
  max_seconds: 15
  sample_rate: 16000
timeouts_s:
  perception: 30
  fast_text: 15
  reasoning: 45
  deep: 120
retries:
  interactive: 2
  background: 3
ui:
  theme: dark                 # dark | light
  speak_feedback: true
```

### 7.3 `config/pricing.yaml`

Per model ID: `input_per_million` and `output_per_million` in USD. Defaults are `null`, and the cost is then shown as "n/a".

Add a comment telling the team to copy the real prices from the Token Factory console pricing page. **Do not invent prices.**

---

## 8. PHASE 0 — INFRASTRUCTURE VERIFICATION (gate; implement first)

**Goal.** Prove the platform works, discover exact model IDs, and record exactly what the API accepts. Everything later reads `data/capabilities.json`.

**Entry points:**
- `python -m polarity verify [--record] [--skip-video] [--json]`
- `python scripts/verify_token_factory.py`, a standalone wrapper. It needs only `openai`, `python-dotenv`, `pillow`, `numpy`, `rich` (and `opencv-contrib-python` for the optional video test).
- `scripts/verify_mac.sh` and `scripts/verify_windows.bat` (activate the venv and run).

### 8.1 Facts vs assumptions (bake these into code comments)

- **Confirmed.**
  - Token Factory is OpenAI-compatible.
  - Nebius's Nemotron page lists Nemotron 3 Nano 30B, Nemotron 3 Nano Omni, Nemotron 3 Super 120B and Nemotron 3 Ultra.
  - Nemotron 3 Super is text-in/text-out.
  - Nemotron 3 Nano Omni accepts text, image, video and audio, and outputs text.
- **Reported, not verified.** Nano Omni video input is MP4 up to ~2 minutes.
- **Two documented base URLs** have been seen:
  - `https://api.tokenfactory.us-central1.nebius.com/v1/` (Nebius Nemotron page);
  - `https://api.tokenfactory.nebius.com/v1/` (older marketing snippet).
- **Team-reported, unverified.** Model IDs in completion payloads must be lowercase. **Do NOT blindly lowercase.** Some IDs on Nebius historically used mixed case (e.g. `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`), and lowercasing those could itself cause "not found".
  - Implement **exact-first, lowercase-fallback**: send the exact ID returned by `/models`. If the response is 404, or the error text contains "not found" / "does not exist" / "unknown model", retry once with `.lower()`.
  - Record which worked per model in `capabilities.json` and reuse it automatically.

### 8.2 Steps (each step logs PASS / FAIL / SKIPPED with details)

**T0 — Environment**
- Python version; required packages importable.
- `NEBIUS_API_KEY` present (masked print).
- Fail fast with a friendly fix message.

**T1 — Base URL probe**
- If `NEBIUS_BASE_URL` is set, use only that.
- Otherwise try, in order:
  - `https://api.tokenfactory.us-central1.nebius.com/v1/`
  - `https://api.tokenfactory.nebius.com/v1/`
  - `https://api.studio.nebius.com/v1/` (legacy AI Studio)
- Use `client.models.list()` with a 15 s timeout.
- Keep the first that returns 200 with a non-empty list. Record it.

**T2 — Model discovery**
- Print a table of ALL model IDs returned (sorted).
- Highlight IDs containing `nemotron` (case-insensitive).
- Resolve roles with heuristics on lowercased IDs (env overrides win):
  - `perception`: contains `omni` (prefer also `nano`); else fallback to an ID containing `nemotron` and (`vl` or `vision`) → set `perception_fallback_vl=true`; else FAIL.
  - `reasoning`: contains `nemotron` and `super` (prefer `120b`).
  - `deep`: contains `nemotron` and `ultra` (prefer the largest parameter count parsed by regex `(\d+)b`).
  - `fast_text`: contains `nemotron` and `nano`, and does NOT contain `omni`/`vl`/`vision` (prefer `30b`).
- Save exact IDs as returned.

**T3 — Text smoke test per resolved model**
- Messages: system "Reply with exactly: OK", user "ping".
- `max_tokens=16`, `temperature=0`.
- Apply the case-fallback logic.
- Record latency (ms), usage, whether `reasoning_content` or `<think>` text appeared, and the case used.

**T4 — Thinking control** (on `perception` and `reasoning`)
- Variant A: `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`.
- Variant B: prepend `/no_think` to the system prompt.
- Compare latency and check that the content still says OK.
- Record which (if any) works. Catch 400s.

**T5 — Generate test assets** (`polarity/verify/assets.py`, saved to `data/verify_assets/`)

These are designed so the answer *proves* each modality was processed:

- **Image** `board.png` (1024×768, PIL):
  - a simple drawn breadboard (rails with red/blue lines, hole grid);
  - a clearly **RED** LED;
  - a resistor;
  - a large label **"TEST BOARD 7"**.
- **Audio** `speech.wav` (16 kHz mono PCM16). Text: *"Hello, this is a test. The secret word is banana."*
  - **macOS:** `say -o <path> --file-format=WAVE --data-format=LEI16@16000 "<text>"`.
  - **Windows:** PowerShell System.Speech (built in, no pip install):
    ```
    Add-Type -AssemblyName System.Speech
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SetOutputToWaveFile('<path>')
    $s.Speak('<text>')
    $s.Dispose()
    ```
    Then resample to 16 kHz mono with numpy if needed (read/write with the stdlib `wave` module).
  - **Linux:** `espeak-ng -w <path> "<text>"`, then resample.
  - **`--record`:** record 5 s from the mic with `sounddevice`. The user says the phrase.
  - **Last resort:** a 1 kHz tone WAV, flagged `modality_proof=false` (acceptance only).
- **Video** `count.mp4` (optional; skip with `--skip-video` or if the OpenCV writer fails): 3 s, 10 fps, frames showing large digits 1 → 2 → 3, fourcc `mp4v`.

**T6 — Omni image-only**
- Image as `{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}`.
- Prompt: "What colour is the LED, and what number is printed on the label? Answer in one short sentence."
- **PASS** if the reply contains `red` and `7`.

**T7 — Omni audio-only.** Try payload variants in order and stop at the first that works:
- A: `{"type":"input_audio","input_audio":{"data":"<b64>","format":"wav"}}`
- B: `{"type":"audio_url","audio_url":{"url":"data:audio/wav;base64,<b64>"}}`

Prompt: "What is the secret word spoken in the audio?" **PASS** if the reply contains `banana`. Record the working variant.

**T8 — Omni COMBINED image + audio in ONE request** (the critical test)
- Content parts: text + image + audio (variant from T7, or try both if T7 failed).
- Prompt: "Answer three things: the LED colour, the number on the label, and the secret word in the audio."
- Classify:
  - `VERIFIED`: HTTP 200 and the reply contains `red`, `7` and `banana`;
  - `ACCEPTED_AUDIO_IGNORED`: 200 but `banana` missing;
  - `ACCEPTED_IMAGE_IGNORED`: 200 but `red`/`7` missing;
  - `REJECTED`: 4xx/5xx — save the status code and error body text to the report;
  - `UNPROVEN`: the tone fallback was used.

**T9 — Omni video** (optional)
- `{"type":"video_url","video_url":{"url":"data:video/mp4;base64,..."}}`, asking which digits appear.
- Record the result. Video is NOT required by the product design.

**T10 — JSON output.** On `perception`, try in order:
- `response_format={"type":"json_schema","json_schema":{"name":"probe","strict":true,"schema":{...small schema...}}}`
- `{"type":"json_object"}`
- prompt-only

Record the first that returns valid JSON.

**T11 — Tool calling on `reasoning`**
- Define one tool `lookup_part(part_number: string)`.
- Ask: "What are the pins of an NE555? Use the tool."
- Record whether `tool_calls` came back → `TOOLS_MODE` = `native` | `manual`.

**T12 — Ultra availability.** One tiny call. Record latency and availability. If it fails, set `deep` → `reasoning` fallback.

### 8.3 Outputs

**1. `data/capabilities.json`:**

```json
{
  "generated_at": "...", "base_url": "...",
  "models": {
    "perception": {"id": "...", "case": "exact|lowercase", "latency_ms": 0},
    "fast_text":  {"id": "...", "case": "...", "latency_ms": 0},
    "reasoning":  {"id": "...", "case": "...", "latency_ms": 0},
    "deep":       {"id": "...", "case": "...", "latency_ms": 0, "available": true}
  },
  "all_model_ids": ["..."],
  "perception_fallback_vl": false,
  "image_input": true,
  "audio_input": {"supported": true, "variant": "input_audio|audio_url|null"},
  "combined_image_audio": "VERIFIED|ACCEPTED_AUDIO_IGNORED|ACCEPTED_IMAGE_IGNORED|REJECTED|UNPROVEN",
  "video_input": "VERIFIED|REJECTED|SKIPPED",
  "json_mode": "json_schema|json_object|prompt_only",
  "tools_mode": "native|manual",
  "thinking_control": "chat_template_kwargs|system_flag|none",
  "audio_mode_recommended": "omni_combined|omni_separate|browser_stt|typed"
}
```

**2. `docs/PHASE0_REPORT.md`:** date, base URL, a table of exact model IDs + case used + latency, every test with PASS/FAIL and evidence (the reply text, truncated to 300 chars), error bodies, and the recommended AUDIO_MODE with reasoning.

**3. Console:** a `rich` summary table and a final line in this exact format:

```
MODEL IDS → perception=<id> | reasoning=<id> | deep=<id> | fast_text=<id>
OMNI COMBINED IMAGE+AUDIO → <STATUS>
```

**Exit codes:** 0 if base + perception image works; 2 if no perception model; 3 if the API is unreachable; 4 if no key.

**Acceptance (Phase 0):**
- Runs end-to-end on macOS and Windows.
- Without a key: exits with code 4 and a friendly message. Then continue building later phases in mock mode.
- With a key: produces both files.
- Estimated cost < $0.10. Print the token totals.

---

## 9. PHASE 1 — CORE ENGINE

### 9.1 Lab definition schema (`polarity/models/lab.py`)

```python
class CommonError(BaseModel):
    id: str                     # e.g. "E_LED_REVERSED"
    description: str            # what it looks like
    visual_cue: str             # how to spot it from above
    fix_hint_l1: str            # where to look
    fix_hint_l2: str            # what's wrong
    fix_hint_l3: str            # exact fix

class Check(BaseModel):
    id: str                     # e.g. "c_anode_row"
    statement: str              # visually verifiable statement that should be TRUE
    required: bool = True
    allow_uncertain: bool = False   # inherently hard to see; can't-tell won't block pass_partial

class LedCheck(BaseModel):
    expect_lit: bool
    colour: Literal["red","green","yellow","blue","white"] = "red"
    instruction_for_capture: str    # e.g. "Hold the button down, then press Check"

class Step(BaseModel):
    id: str; title: str; instruction: str
    illustration: str | None    # svg filename in static/img/steps/
    checks: list[Check]
    common_errors: list[CommonError] = []
    led_check: LedCheck | None = None
    capture_tip: str = "Keep the whole board inside the four markers."

class LabDefinition(BaseModel):
    id: str; title: str; version: str; summary: str
    kit: list[str]; safety_notes: list[str]
    breadboard_conventions: str
    steps: list[Step]
```

### 9.2 `labs/lab1.yaml` (full default content — implement exactly, team may tune)

**Lab:** `lab1`, "Push-button LED (3 V)".

**Kit:** 2×AA holder with switch (OFF while building), red 5 mm LED, 100 Ω resistor, 6×6 mm tactile button, jumpers.

**Safety notes:**
- battery power only;
- keep the switch OFF until Step 6;
- if anything gets warm, switch off and call the TA.

**breadboard_conventions** (also injected into prompts):
- The long strips along the top and bottom edges are power rails. Holes along a rail are connected along its length. The red line marks '+', the blue line marks '−'.
- The middle area is split by a centre channel.
- On each side of the channel, each numbered strip of 5 holes (a–e above, f–j below) is connected internally.
- Strips on opposite sides of the channel are NOT connected.
- Two component legs in the same numbered strip on the same side are electrically joined.

**Steps:**

| id | title | instruction | checks | common_errors |
|---|---|---|---|---|
| s1 | Power rails | Battery switch OFF. Push the red lead into the top **+** rail (red line) and the black lead into the top **−** rail (blue line). | c_red_plus: red lead enters a hole on the rail marked by the red line; c_black_minus: black lead enters a hole on the rail marked by the blue line; c_leads_not_in_strips: neither lead is in the middle numbered strips | E_RAILS_SWAPPED, E_LEAD_IN_STRIP, E_SAME_RAIL |
| s2 | Resistor | Put one resistor leg in the top **+** rail and the other leg in a numbered strip in the top half (e.g. strip 10). | c_res_present; c_leg_in_plus_rail; c_other_leg_in_strip; c_not_shorted: the two legs are not in the same strip or same rail | E_RES_SHORTED, E_RES_IN_MINUS, E_RES_BOTH_IN_STRIPS |
| s3 | LED | Put the LED's **long leg (+)** in the same strip as the resistor's lower leg, and the **short leg (−, flat edge)** in the next strip along. | c_led_present; c_led_legs_different_strips; c_anode_shares_resistor_strip; c_orientation: the flat edge / short leg is on the side away from the resistor (**allow_uncertain: true**) | E_LED_REVERSED, E_LED_SAME_STRIP, E_LED_NOT_CONNECTED |
| s4 | Push button | Place the button **across the centre channel** so one pair of its legs shares the LED's short-leg strip. | c_btn_present; c_btn_straddles_channel; c_btn_shares_cathode_strip; c_btn_rotation: the button is rotated so its legs bridge the channel, not run along it (**allow_uncertain: true**) | E_BTN_NOT_STRADDLING, E_BTN_WRONG_STRIP, E_BTN_ROTATED |
| s5 | Ground wire | Add a black jumper from the button's other leg strip to the top **−** rail. | c_jumper_present; c_jumper_from_button_other_strip; c_jumper_to_minus_rail | E_GND_TO_PLUS, E_GND_WRONG_STRIP |
| s6 | Power test | Switch the battery ON. **Hold the button down**, then press Check. | c_led_lit (also verified by LedDetector, `led_check: {expect_lit: true, colour: red}`) | E_NO_LIGHT (diagnose via history + board audit) |

Write every CommonError with realistic `visual_cue` and three hint levels. Example for E_LED_REVERSED:

- **visual_cue:** "The LED's flat rim edge / short leg is on the resistor side."
- **L1:** "Take a close look at which side of the LED faces the resistor."
- **L2:** "Your LED looks reversed — the long leg should share the resistor's strip."
- **L3:** "Pull the LED out, turn it around so the long leg goes in the resistor's strip, and push it back in."

Also create:
- `lab1_5v.yaml`: same steps, 5 V USB module + 220 Ω; s1 instruction changed accordingly.
- `lab2_solder_template.yaml` (P2): a soldering lab template where joint-quality checks are all `allow_uncertain: true` and the instructions say joint quality is flagged for TA review. This is honest about the limits of visual inspection.

Also hand-draw a simple, clean SVG illustration per step in `static/img/steps/` (top-down breadboard, highlighting where the part goes; flat colours from the design tokens).

### 9.3 Verdict schema (`polarity/models/verdict.py`)

```python
class CheckResult(BaseModel):
    id: str
    result: Literal["pass","fail","not_visible"]
    observation: str                       # ≤ 25 words, cites visual evidence

class PerceptionVerdict(BaseModel):        # what the model returns
    step_id: str
    checks: list[CheckResult]
    detected_error_ids: list[str] = []
    confidence: float = Field(ge=0, le=1)  # honest probability the overall judgement is right
    evidence_region: dict | None = None    # {"x":0-1,"y":0-1,"w":0-1,"h":0-1} approximate; optional
    retake_instruction: str | None = None  # when anything is not_visible
    spoken_feedback: str                   # ≤ 25 words
    student_answer: str | None = None      # if student audio/question was attached (≤ 40 words)
    parts_seen: list[str] = []             # any printed part markings read (e.g. "NE555")

class FinalVerdict(BaseModel):             # what code decides
    status: Literal["pass","pass_partial","fix","uncertain"]
    reason: str                            # e.g. "quality:glare", "model:fail c_orientation", "led:not_lit"
    perception: PerceptionVerdict | None
    led: dict | None
    second_look_used: bool = False
    model_id: str | None; latency_ms: int | None; cost_usd: float | None
```

Provide the JSON Schema of `PerceptionVerdict` for `json_schema` mode (generated with `model_json_schema()`, `additionalProperties: false`).

### 9.4 Decision policy (`engine/decision.py`, pure function, fully unit-tested)

```
inputs: PerceptionVerdict v, Step step, LED result (optional), settings
required = checks where required=True
fails     = [c for c in v.checks if c.result=="fail"]
missing   = required checks with result "not_visible" or absent
hard_missing = [m for m in missing if not step.check(m).allow_uncertain]

if step.led_check:
    if quality bad → uncertain(reason="quality:...")
    if led.lit != expect_lit and led.signal_strength >= strong → fix(reason="led:not_lit") (physical evidence wins)
    if led.lit == expect_lit and led strong → pass (model text used only for explanation)
    otherwise fall through to model-based rules

if fails and v.confidence >= fix_min_conf             → fix
if not fails and not missing and v.confidence >= pass_min_conf → pass
if not fails and not hard_missing and missing and v.confidence >= pass_min_conf → pass_partial
else → uncertain
```

**Second look:**
- If the provisional status is pass/fix/pass_partial AND `v.confidence` is within `grey_zone`:
  - re-run perception once on a 1.6× zoomed crop centred on `evidence_region`, or on the board centre if there is no region;
  - use `temperature=0.2`;
  - add the system addendum "This is a second, closer look."
- If the two statuses disagree → uncertain (`reason="second_look_disagreement"`).

**Retake instruction for uncertain:** use the model's `retake_instruction`, otherwise map from the quality metric:
- dark → "It's too dark — switch on the ring light or move the lamp closer."
- blur → "The picture is blurry — hold the board still for a second."
- glare → "There's glare — tilt the board slightly away from the light."
- markers → "I can't see all four corner markers — slide the board back inside them."
- motion → "Hands out of frame for a moment, then press Check."

### 9.5 Prompts (`llm/prompts.py`; implement verbatim, then improve only via eval results)

#### 9.5.1 `STEP_VERIFIER_SYSTEM` (perception)

```
You are Polarity, a careful step verifier for a beginner electronics lab. You look at a top-down photo of a
student's solderless breadboard and judge ONE build step.

Rules:
1. Judge ONLY what is visible in the image. Never assume something is correct because it is expected or because
   the student says so.
2. Breadboard conventions: {breadboard_conventions}
3. For EVERY check in CHECKS, return "pass" if the statement is clearly true in the image, "fail" if it is clearly
   false, and "not_visible" if the relevant part is hidden, blurred, cropped, in shadow, glared, or ambiguous.
   "not_visible" is a correct, valued answer whenever it is true. Guessing is a failure.
4. Each observation must cite concrete visual evidence (positions, colours, which strip or rail), max 25 words.
5. If you recognise any COMMON_ERRORS, list their ids in detected_error_ids.
6. confidence = your honest probability (0–1) that your overall judgement of this step is correct.
7. If anything is not_visible, write retake_instruction: one specific action (angle, light, distance, move hands).
8. spoken_feedback: max 25 words, second person, warm and concrete. For a failing step follow HINT_LEVEL:
   1 = point to where to look without giving the answer; 2 = name the problem; 3 = give the exact fix.
   For a passing step, confirm briefly and name the next step.
9. If the student's audio or typed question is attached, answer it in student_answer (max 40 words), grounded in
   the image and this step. If it involves mains power, heat, smoke, damaged batteries, or anything unsafe, tell
   them to switch off and call the TA.
10. If you can read printed part markings (e.g. an IC label), list them in parts_seen.
11. Output ONLY one JSON object matching the schema. No markdown, no extra text.
```

**User content** (one message): a text block with JSON, then the image part, then the audio part if any.

```json
{"lab": "...", "step": {"id","title","instruction"}, "checks": [...], "common_errors": [{"id","visual_cue"}],
 "hint_level": 1, "typed_question": null, "image_note": "Top-down, perspective-corrected view of the breadboard."}
```

#### 9.5.2 `VOICE_QA_SYSTEM` (perception)

Used when the student asks without checking. Same grounding and safety rules. Answers in ≤ 40 words. If the question is unrelated to the lab, redirect politely.

Output JSON: `{"answer": str, "intent": "how_to|why|part_info|help|other", "parts_mentioned": [str]}`.

#### 9.5.3 `DIAGNOSIS_SYSTEM` (reasoning)

```
You help a lab TA triage. Given one student's attempt history for the current step (verdicts, failed checks,
error ids, hint levels used, timestamps), write a short, factual summary. Do not speculate beyond the data.
Output JSON: {"summary_for_ta": "<=40 words", "likely_root_cause": "<=20 words", "suggested_ta_action": "<=25 words",
"urgency": "low|medium|high"}  (high only if a safety-related note or repeated power-test failure exists)
```

#### 9.5.4 `CLASS_REPORT_SYSTEM` (deep)

```
You write an end-of-class report for a lab TA from aggregated statistics provided as JSON. Use ONLY numbers that
appear in the input; never invent or round into new statistics. If data includes simulated records, state that in
the first line. Output Markdown with sections:
## Snapshot  ## Where the class got stuck (top 3 steps, first-try pass %, median attempts)
## Most common mistakes (error ids → plain-English explanation, counts)
## Students who may need follow-up (aliases only, factual reason)
## Suggested re-teach for next session (2–4 bullets, concrete)
## Data caveats (uncertain-rate, quality issues, simulated data)
```

#### 9.5.5 `LAB_COMPILER_PAGE_SYSTEM` (perception, P1)

Reads one page image of a lab handout. Returns JSON: `{"page_summary", "components": [...], "steps_found": [{"title", "instruction", "figure_description"}]}`.

#### 9.5.6 `LAB_COMPILER_ASSEMBLE_SYSTEM` (reasoning, P1)

Turns the page extracts into a `LabDefinition` JSON. Rules:
- Every check must be a visually verifiable statement about the breadboard from above.
- Mark checks that depend on fine detail (polarity marks, colour bands, solder quality, small text) as `allow_uncertain: true`.
- Write 2–4 common errors per step with three hint levels.
- Never include mains-voltage steps. If found, add a safety note and exclude them.

#### 9.5.7 `BOARD_AUDIT_SYSTEM` (perception, P1)

After a failed power test, evaluate ALL steps' checks on the current image and rank the most likely culprit steps.

Output JSON: `{"suspects": [{"step_id", "check_id", "why", "confidence"}], "spoken_feedback"}`.

#### 9.5.8 `PART_LOOKUP_SYSTEM` (reasoning, P1)

Given Tavily results (title, url, content snippets), summarise the part's pinout/orientation and one safety or usage note in ≤ 80 words.
- Only use facts present in the results.
- Return JSON `{"summary", "pinout": [{"pin", "name"}], "sources": [url]}`.
- If the results are insufficient, say so.

### 9.6 ModelRouter (`llm/router.py`)

```python
result = router.call(
    role="perception" | "fast_text" | "reasoning" | "deep",
    messages=[...], schema: type[BaseModel] | None = None,
    tools=None, temperature=0.0, max_tokens=800, thinking=False, timeout=None)
# returns RouterResult(text, parsed, model_id, case_used, latency_ms, usage, cost_usd, raw_finish_reason)
```

Responsibilities:
- resolve the role → model ID from capabilities/env;
- apply the case policy;
- apply thinking control;
- apply JSON mode per capabilities;
- retries with backoff on 429/5xx/timeouts;
- budget guard (raises `BudgetExceeded`, which the UI shows);
- cost estimation from `pricing.yaml`;
- append every call to the `model_calls` table;
- emit a `cost_update` event.

### 9.7 LLM output handling (`llm/jsonio.py`)

- Strip `<think>...</think>` blocks and ignore any `reasoning_content` field.
- Extract the first balanced `{...}` JSON object (handle ```json fences, leading/trailing prose, smart quotes).
- Validate with Pydantic.
- **On failure:** one repair call to the same model with "Your previous output was not valid JSON for this schema: <errors>. Return ONLY the corrected JSON." plus the schema.
- **If the repair fails:** return `uncertain` with `reason="model:invalid_output"`. Never crash.

### 9.8 Edge computer vision (`polarity/edge/`)

**BoardLocator:**
- `cv2.aruco.ArucoDetector` with `DICT_4X4_50`.
- With 4 markers: use the inner corners to compute the homography to 1024×768.
- With 3 markers: infer the 4th via parallelogram completion.
- Otherwise: report `markers_found` and return None.
- ROI mode when markers are disabled.
- Draw the detected quad (teal) on the preview frame.

**QualityGate** (on the warped or ROI grey image):
- variance of Laplacian;
- mean brightness;
- glare ratio;
- markers found;
- motion from MotionMonitor.

Returns `{ok: bool, metrics: {...}, failing: [metric]}`. Publish metrics at 2 Hz via WebSocket for the live quality chips.

**MotionMonitor:** mean absolute difference of downscaled grey frames over a 0.5 s window.

**LedDetector:**
- At step start (and on "Set baseline" in Debug), store a warped baseline frame.
- On check:
  - convert to HSV;
  - candidate mask = (V − V_baseline ≥ `v_delta_min`) AND [(hue in red ranges AND S ≥ `s_min`) OR (V ≥ 245, to handle an over-exposed LED core with a red halo)];
  - morphological open;
  - connected components filtered by area.
- Return `{lit, signal_strength (0–1), blobs: [...]}`.
- `polarity calibrate` shows live metrics and the LED mask so the team can tune the thresholds for their rig.

**Camera ring buffer:** keep the last 15 frames with a sharpness score. On check, use the sharpest frame within the last 1 s.

### 9.9 Mock mode and synthetic placeholders

- `polarity render-synthetic` uses PIL to draw simple top-down breadboard images with ArUco markers in the corners, for every step and every common error. Saved to `data/demo/lab1/<step>/<label>.png` (label `correct` or an error id).
  - These are for UI development and CI only.
  - **They must never be used for accuracy claims.**
- `llm/mock.py` returns canned `PerceptionVerdict`s keyed by the demo image's label, plus canned diagnosis/report text.
  - Only active when `POLARITY_MOCK_MODELS=1`.
  - Every mocked response carries `model_id="MOCK"`.
- `CAMERA_SOURCE=demo` plays the demo images.
  - The Debug panel has a scene picker (step × label) so the whole UI flow can be shown with no hardware.
  - Real team photos placed in `data/demo/lab1/` override the synthetic ones.

### 9.10 Storage (`storage/db.py`)

```sql
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, student_alias TEXT, bench_id TEXT, lab_id TEXT,
  started_at TEXT, completed_at TEXT, is_simulated INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, session_id TEXT, step_id TEXT, kind TEXT, -- check|ask|audit
  status TEXT, reason TEXT, confidence REAL, hint_level INTEGER, verdict_json TEXT, led_json TEXT,
  raw_image_path TEXT, warped_image_path TEXT, audio_path TEXT, model_id TEXT, latency_ms INTEGER,
  cost_usd REAL, created_at TEXT, is_simulated INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS help_requests(id TEXT PRIMARY KEY, session_id TEXT, step_id TEXT, trigger TEXT,
  summary_json TEXT, status TEXT, created_at TEXT, resolved_at TEXT, is_simulated INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, lab_id TEXT, created_at TEXT, model_id TEXT,
  markdown TEXT, input_stats_json TEXT, cost_usd REAL);
CREATE TABLE IF NOT EXISTS model_calls(id TEXT PRIMARY KEY, role TEXT, model_id TEXT, ok INTEGER, latency_ms INTEGER,
  prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL, error TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS part_cache(part TEXT PRIMARY KEY, summary_json TEXT, created_at TEXT);
```

- Media is stored under `data/media/<session_id>/`.
- `polarity purge` deletes media older than `MEDIA_RETENTION_DAYS`.

**Acceptance (Phase 1):**
- Unit tests for schemas, decision policy (table-driven, ≥ 15 cases), jsonio (fences, think tags, prose, broken JSON), resolver (mixed-case fixtures, lowercase fallback via mocked 404), router budget guard, QualityGate (synthetic dark/blur/glare images), BoardLocator (synthetic image with drawn markers → correct warp size), LedDetector (synthetic red blob vs baseline).
- `python -m polarity eval --mock` runs over the synthetic set end-to-end.

---

## 10. PHASE 2 — EDGE RUNTIME AND API

### 10.1 CameraService

- Background thread with the backend chosen per OS (Section 5).
- Request the configured resolution and fall back to 1280×720.
- Auto-reconnect if the device drops.
- Exposes `latest()`, `sharpest_recent(seconds=1.0)`, and an MJPEG generator at ~12 fps, 960 px wide, with the overlay drawn.
- `polarity devices` probes indices 0–5 and prints which open, plus their resolution.

### 10.2 HTTP routes (FastAPI)

**Pages:**
- `GET /` → start screen (alias + lab + camera check), then the bench view;
- `GET /bench`;
- `GET /ta` (PIN);
- `GET /labs/editor` (PIN);
- `GET /debug`.

**Media:**
- `GET /stream.mjpg`;
- `GET /api/frame/warped.jpg`;
- `GET /media/{path}` (sandboxed to `data/media`).

**System:**
- `GET /api/health`;
- `GET /api/capabilities`;
- `GET /api/config` (safe subset, no secrets).

**Session:**
- `POST /api/session/start {student_alias, lab_id, bench_id?}`;
- `GET /api/session/current`;
- `POST /api/session/reset`.

**Actions:**
- `POST /api/check` (multipart: optional `audio` WAV ≤ 15 s, optional `typed_question`) → FinalVerdict;
- `POST /api/ask` (audio or text) → answer;
- `POST /api/help` → help request;
- `POST /api/baseline`.

**TA (PIN header or cookie):**
- `GET /api/ta/overview`;
- `GET /api/ta/heatmap`;
- `GET /api/ta/help`;
- `POST /api/ta/help/{id}/resolve`;
- `POST /api/ta/step/skip` (override);
- `POST /api/ta/report`;
- `GET /api/ta/report/{id}`;
- `GET /api/ta/report/{id}.md`.

**Labs (P1):**
- `GET /api/labs`;
- `GET/PUT /api/labs/{id}`;
- `POST /api/labs/compile` (PDF or images).

**Parts (P1):** `POST /api/parts/lookup {part}`.

**Demo/debug:** `POST /api/demo/scene {step, label}`, `POST /api/demo/seed`.

**WebSocket `/ws` events:**
- `quality {metrics, ok, failing}`
- `check_started {step_id}`
- `check_result {FinalVerdict}`
- `step_advanced {step_id}`
- `session_completed`
- `help_created`
- `help_resolved`
- `cost_update {session_usd, day_usd}`
- `error {message}`

The client reconnects automatically with backoff.

### 10.3 Audio and voice (browser side)

- **`audio.js`:**
  - `getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}})`;
  - capture Float32 with an AudioWorklet (fall back to ScriptProcessor);
  - downsample to 16 kHz;
  - encode PCM16 WAV;
  - 15 s cap with a live level meter.
- **Hold-to-talk:** pointerdown/up on the mic button, and keydown/keyup on **V**.
- **Space** triggers Check (ignored while typing in inputs).
- **`tts.js`:**
  - `speechSynthesis` speaks `spoken_feedback` / `student_answer`;
  - voice picker and mute toggle in settings;
  - the first user click unlocks audio (Safari);
  - captions are always shown on screen, so voice is never the only channel.
- **`AUDIO_MODE=browser_stt`:** use `webkitSpeechRecognition` where available and send text instead of audio.

**Acceptance (Phase 2):**
- With a real webcam on macOS and Windows: live preview and quality chips update.
- Check works end-to-end in mock mode, and live when a key is present.
- Audio upload works.
- Disconnecting the camera mid-run shows a banner and recovers when reconnected.

---

## 11. PHASE 3 — UI AND DESIGN SYSTEM (make it look like a real product)

### 11.1 Design tokens (`polarity.css`, `:root` + `[data-theme="light"]`)

**Dark (default, "bench") theme:**

| Token | Value |
|---|---|
| `--bg` | `#0B0F14` |
| `--surface` | `#111821` |
| `--surface-2` | `#18212D` |
| `--border` | `#243041` |
| `--text` | `#E6EDF3` |
| `--text-muted` | `#8B98A9` |
| `--accent` (teal) | `#2DD4BF` |
| `--accent-ink` | `#04201C` |
| `--pass` | `#22C55E` |
| `--fix` | `#F59E0B` |
| `--danger` | `#EF4444` |
| `--uncertain` | `#60A5FA` |
| `--mock` | `#F59E0B` |

**Light (projector) theme:**

| Token | Value |
|---|---|
| `--bg` | `#F6F8FA` |
| `--surface` | `#FFFFFF` |
| `--surface-2` | `#EEF2F6` |
| `--border` | `#D0D7DE` |
| `--text` | `#0B0F14` |
| `--text-muted` | `#57606A` |

Use the same status colours, darkened 10% if needed for AA contrast.

**Type:**
- `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`;
- mono: `ui-monospace, "SF Mono", Consolas, "Cascadia Mono", monospace`;
- scale: 14 / 16 / 18 / 20 / 24 / 32 / 48;
- bench view base size 18 px (readable from 1 m).

**Shape and motion:**
- spacing on a 4 px grid;
- radius 12 px for cards, 999 px for pills;
- one subtle shadow level;
- 180 ms ease-out transitions;
- respect `prefers-reduced-motion`.

**Status display:** always icon + word + colour, never colour alone.
- ✓ PASS
- ✓ PASS · 1 thing to double-check
- ⚠ FIX
- ? CAN'T TELL

Draw the icons as inline SVGs in `static/img/icons/`.

Create a simple, distinctive logo SVG: a stylised LED symbol (triangle + bar) inside a rounded square, wordmark "Polarity".

### 11.2 Start screen (`/`)

- Logo and tagline.
- Alias field (helper text: "Use a nickname — no real names needed").
- Lab picker.
- Bench ID.
- A camera check panel with live preview and five quality chips (Light, Focus, Glare, Board found, Steady). Every chip must be green before "Start lab" is enabled. An "I'm using demo mode" link bypasses this when `CAMERA_SOURCE=demo`.
- Links: "Print marker mat" and the safety note.

### 11.3 Bench view (`/bench`; designed for 1366×768, scales to 1920×1080)

**Top bar:**
- logo;
- lab title;
- student alias;
- step progress (6 dots with labels on hover);
- connection pill ("Token Factory · connected" in green / "MOCK MODE" in amber / "Offline" in red);
- settings gear (theme, voice, mute).

**Left (≈60%): camera panel.**
- Live MJPEG with the board quad overlay.
- Quality chips row underneath.
- A toggle to show the warped "what the AI sees" view. Make it visible by default during the demo; it sells the edge processing.

**Right (≈40%): step card.**
- "Step 3 of 6 · LED".
- Instruction text (20 px).
- Step illustration SVG.
- A "What I'll check" list built from the checks, as plain-language bullets.
- **Primary button:** "Check my step" (Space), large, teal.
- **Secondary:** the hold-to-ask mic button (V) with level meter.
- **Tertiary:** "Call TA".

**Verdict card** (slides in under the step card; announced via `aria-live`):
- a status banner in the status colour;
- `spoken_feedback` as a large caption with a speaker icon to replay;
- per-check rows with status chip + observation;
- an evidence thumbnail (the warped image, with a soft highlight rectangle when `evidence_region` exists and confidence ≥ 0.75);
- the `student_answer` bubble, if any.

Actions by status:
- PASS → "Next step";
- FIX → "Try again" (the hint level shown as 1 / 2 / 3 dots);
- CAN'T TELL → the retake instruction with a matching icon (lamp / tilt / hand / markers) and "Check again".

**Footer meta line (small, muted):** model ID · latency · "second look" tag if used. This shows judges the real model use.

**Thinking state:**
- the button becomes "Looking closely… 3 s" with a skeleton verdict card;
- at 30 s the timeout state reads "I couldn't reach the AI. Your work is saved — try Check again."

**Completion screen:** all steps ticked, total time, total checks, and "Show your TA — great work". A subtle animation, no confetti spam.

### 11.4 TA dashboard (`/ta`)

- **Header:** lab title, live counters (active benches, completed, waiting for help, median time per step), "Generate class report" button, theme toggle.
- **Banner:** if any `is_simulated` rows exist: "Includes simulated class data for demonstration".
- **Left column: Help queue.**
  - Cards sorted by wait time showing bench, alias, step, Super's `summary_for_ta`, suggested action, urgency chip, latest evidence thumbnail, and "Resolve".
  - New cards animate in and play a soft sound (toggleable).
- **Centre: Heatmap.** Rows are students/benches, columns are steps. Cell states:
  - not started (`--surface-2`);
  - in progress (outline);
  - passed first try (green);
  - passed after fixes (green with a small attempts number);
  - struggling, ≥ 2 fixes (amber);
  - stuck, ≥ 3 fixes or a help request (red);
  - many can't-tell (blue stripe).

  Clicking a cell opens a drawer with that student's attempt timeline (thumbnails, statuses, observations, model, latency).
- **Right column: Step insights.** Per step: first-try pass %, median attempts, top 3 error IDs with counts and plain-English labels.
- **Report view:** rendered Markdown from Ultra, with the model ID, tokens, cost and generation time shown. Buttons: "Download .md", "Copy".

### 11.5 Lab editor (`/labs/editor`, P1)

- A lab list.
- "Upload lab sheet (PDF or photos)" → progress per page → side-by-side page thumbnails and the generated steps form (editable fields for all schema fields).
- Validation errors shown inline.
- "Publish" writes `labs/<id>.yaml`.
- Mark "AI-drafted — review before use" until a TA saves.

### 11.6 Debug panel (`/debug`)

- `capabilities.json` viewer.
- Routing table.
- The last 20 model calls (role, model, ok, latency, tokens, cost, error).
- Raw JSON of the last verdict.
- Live quality metrics with session-only threshold sliders.
- LED mask view.
- Scene picker for demo mode.
- "Set baseline" button.
- Budget meter.

### 11.7 Accessibility and polish

- WCAG AA contrast.
- Everything keyboard-operable, with a visible focus ring (3 px accent).
- `aria-live="polite"` on the verdict.
- Captions always visible.
- Buttons ≥ 44 px tall.
- No layout shift when the verdict arrives.
- Favicon from the logo.
- Page titles set.
- Empty states designed (e.g. a TA view with no data says "No benches yet — start a session or seed demo data").

**Acceptance (Phase 3):** Write `docs/UI_CHECKLIST.md` and verify every state below in demo mode, in both themes:
- quality fail;
- pass;
- pass_partial;
- fix (hint 1–3);
- can't tell;
- timeout;
- budget exceeded;
- completed;
- TA with simulated data;
- report.

---

## 12. PHASE 4 — TA INTELLIGENCE

### 12.1 Escalation rules (deterministic, in SessionEngine)

Create a help request when any of these happen:
- `fix` count on the current step ≥ 3;
- 3 consecutive `uncertain` results on the same step;
- the student presses "Call TA";
- the power test (s6) fails twice;
- any perception answer contains a safety redirect.

On creation:
- call `reasoning` with `DIAGNOSIS_SYSTEM` asynchronously (non-blocking; the UI immediately shows "Your TA has been notified");
- store the summary;
- push `help_created` to TA clients.

### 12.2 Class report

`POST /api/ta/report`:
- aggregates stats in SQL: per-step first-try pass %, median attempts, error ID counts, uncertain rate, quality-failure counts, help requests, completion times, simulated flag;
- sends them as JSON to `deep` with `CLASS_REPORT_SYSTEM`;
- thinking is allowed for this role;
- falls back to `reasoning` if needed;
- stores and renders the report.

### 12.3 Seeded class demo (`polarity seed-demo --students 28`)

- Creates simulated sessions with `is_simulated=1` for a believable class:
  - s1: 85% first-try pass, E_RAILS_SWAPPED common;
  - s2: 70%, E_RES_SHORTED;
  - s3: 55%, E_LED_REVERSED dominant;
  - s4: 50%, E_BTN_NOT_STRADDLING / E_BTN_ROTATED;
  - s5: 80%;
  - s6: 75%;
  - 8% of attempts uncertain;
  - 4–6 help requests with canned diagnosis text marked simulated;
  - realistic timestamps over 90 minutes.
- **The UI banner must show whenever simulated data exists.**
- `polarity seed-demo --clear` removes it.
- **Never present simulated numbers as real results** in the README, Devpost text or video. In the video, show the banner.

**Acceptance (Phase 4):**
- Escalation unit tests.
- In mock mode: seed demo → heatmap, insights and help queue render → a report is generated.
- With a key: a real report from the `deep` model on seeded data. The report's first line states the data is simulated.

---

## 13. PHASE 5 — P1 FEATURES: LAB COMPILER, TAVILY PART LOOKUP, BOARD AUDIT, HUB MODE

### 13.1 Lab compiler

- Render PDF pages with `pypdfium2` at 150 dpi (images accepted directly).
- Per page: run `perception` + `LAB_COMPILER_PAGE_SYSTEM`.
- Then: `reasoning` + `LAB_COMPILER_ASSEMBLE_SYSTEM` → validate `LabDefinition` → open in the editor.
- Cap at 10 pages, with a cost estimate shown before running.
- Include a sample PDF `labs/samples/lab1_handout.pdf`, generated from `lab1.yaml` with Pillow (simple handout layout), so the feature can be demoed.

### 13.2 Tavily part lookup (Best Use of Tavily)

- **Triggers:**
  - the student asks about a part (`fast_text` intent = `part_info`, or a part-number regex such as `\b[A-Z]{1,4}\d{2,5}[A-Z]?\b` in the transcript/answer);
  - or `parts_seen` is non-empty in a verdict ("I can see an NE555 — want its pinout?" chip).
- **Flow:**
  - `TOOLS_MODE=native`: Super with the `lookup_part` tool; the code executes the tool with Tavily.
  - `manual`: the code calls Tavily directly, then Super summarises with `PART_LOOKUP_SYSTEM`.
- **Tavily call:** `TavilyClient(api_key).search(query=f"{part} pinout datasheet", max_results=5, search_depth="basic", include_answer=False)`.
- Cache results in `part_cache`.
- **UI:** a "Part info" drawer with summary, pinout table and clickable source links. Only show facts from the sources.
- If `TAVILY_API_KEY` is missing, hide the feature gracefully.
- Document this clearly in the README as a runtime Tavily call.

### 13.3 Board audit ("bug hunt")

After a failed s6 (or a TA button press), run `BOARD_AUDIT_SYSTEM` on the current image. Show the ranked suspects with "Go to step N" buttons.

### 13.4 Hub mode

- `polarity run --role hub --lan` on the TA laptop.
- Benches run `--role bench --hub-url http://<ip>:8765 --bench-id B07`.
- Benches POST attempts and help requests (thumbnails optional, off by default for privacy).
- The hub's TA dashboard aggregates all benches.
- Bench retries are queued if the hub is unreachable.

**Acceptance (Phase 5):**
- Each feature works in mock mode with tests.
- Live: the compiler runs on the sample PDF; part lookup returns cited sources for "NE555".

---

## 14. PHASE 6 — TESTS AND EVALUATION HARNESS (this produces real evidence for judges)

### 14.1 Tests

Everything runs with `POLARITY_MOCK_MODELS=1`, `CAMERA_SOURCE=demo`, and no network:

- the Phase 1 list;
- API tests with FastAPI TestClient (start session → check → advance → help → TA endpoints with PIN → report);
- WAV upload validation;
- seed-demo flags;
- budget guard;
- config loading on Windows-style paths.

### 14.2 Capture tool

`polarity capture --lab lab1 --step s3 --label E_LED_REVERSED`:
- opens a simple capture page or window with live preview and quality chips;
- Space saves raw + warped images into `data/eval/lab1/s3/E_LED_REVERSED/`;
- shows a counter.

> **TEAM TASK (humans):** capture at least 5 photos per (step, label) on the real rig, varying lighting slightly. That's about 80–120 photos and roughly 45 minutes.

### 14.3 Eval (`polarity eval --dataset data/eval/lab1 [--limit N]`)

**Ground truth:** `correct` → expected pass (or pass_partial); `E_*` → expected fix, with that error ID ideally detected.

**Metrics:**

| Metric | Meaning |
|---|---|
| coverage | % non-uncertain |
| selective accuracy | accuracy among non-uncertain |
| **false-pass rate** | wrong build marked pass — the most important number |
| error-ID hit rate | |
| uncertain rate per step | |
| latency p50/p95 | |
| cost per check | |
| confusion matrix | |

**Output:** `docs/EVAL_RESULTS.md` with date, model IDs, prompt hash, settings snapshot, tables, and a short "what we changed after eval" log. Also a CSV of every prediction.

**Decision gate:**
- Target: false-pass ≤ 5% and selective accuracy ≥ 85%.
- If not met, tune in this order:
  1. capture/lighting;
  2. crop/zoom;
  3. prompt wording;
  4. thresholds;
  5. mark hard checks `allow_uncertain`.

  Re-run and record each iteration honestly.
- **These real numbers** (not simulated) are what the README, Devpost text and video may quote.

**Acceptance (Phase 6):**
- `pytest` green on all OSes in CI.
- `eval --mock` produces the report format.
- The live eval runs once the team adds photos (mark PENDING until then).

---

## 15. PHASE 7 — SETUP SCRIPTS, DOCS AND SUBMISSION PACKAGE

### 15.1 Setup and run scripts (must work on a fresh machine)

**`scripts/setup_mac.sh`:**
1. Find `python3.12` or `python3.11`. If neither exists, print the Homebrew/python.org instructions and exit.
2. Create `.venv`.
3. `pip install -U pip wheel`.
4. Install requirements and requirements-dev, then `pip install -e .`.
5. Copy `.env.example` → `.env` if missing.
6. Run `python -m polarity doctor`.

**`scripts/setup_windows.ps1`:**
1. Find `py -3.12`, then `py -3.11`, then `python` (version-checked). If none, print the python.org/winget instructions (`winget install Python.Python.3.12`) and exit.
2. Create `.venv`.
3. Install with `.\.venv\Scripts\python.exe -m pip ...`.
4. Copy the env file.
5. Run doctor.

**`scripts/setup_windows.bat`:** `powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"`. Quote all paths; handle spaces in usernames.

**Run scripts:** `run_mac.sh` / `run_windows.ps1` / `run_windows.bat` → `python -m polarity run --open-browser`.

**Verify scripts:** `verify_mac.sh` / `verify_windows.bat` → Phase 0.

**`polarity doctor`** checks and prints fixes for:
- Python version;
- imports;
- `cv2.aruco` present (else: "uninstall opencv-python, install opencv-contrib-python");
- camera opens (with OS-specific permission instructions);
- `.env` key present (masked);
- Token Factory reachable;
- `capabilities.json` present (else "run verify");
- port free;
- disk space for media.

### 15.2 CI (`.github/workflows/ci.yml`)

- Matrix: `ubuntu-latest`, `macos-latest`, `windows-latest` × Python 3.12.
- Install requirements, then run `ruff check` and `pytest` with the mock/demo env vars.
- No secrets needed.

### 15.3 README.md (exact section order)

1. Title, tagline, MIT badge, a one-line "Built for the Nebius x NVIDIA Global AI Hackathon — Physical AI track".
2. Demo video link (placeholder `{{YOUTUBE_URL}}`) and a hero screenshot/GIF placeholder.
3. **The problem** (user, pain, TA bottleneck — with `{{TA_RATIO_CONFIRMED}}` placeholder logic).
4. **What it does** (5 bullets matching the non-obvious choices).
5. **How it works** (architecture SVG plus the check sequence in 8 numbered lines).
6. **How we use NVIDIA Nemotron and Nebius Token Factory** (required by the rules):
   - the routing table with exact model IDs from `capabilities.json`;
   - why each model;
   - a sample request snippet;
   - thinking control;
   - JSON mode;
   - how the OpenAI-compatible API let us swap models by ID;
   - real Phase 0 latency numbers.
   - **"Where Token Factory accelerated our workflow"**: honest, specific points drafted from Phase 0 and the team's experience, marked `TODO-TEAM-CONFIRM`.
7. **Tavily** (runtime part lookup).
8. **Hardware and rig** (minimum vs recommended, marker mat, photo placeholders).
9. **Quick start — macOS** and **Quick start — Windows** (copy-paste blocks, permission notes).
10. Demo mode (no camera, no credits).
11. Configuration reference.
12. **Evaluation results** (auto-inserted from `EVAL_RESULTS.md`; "pending" until real).
13. Privacy and safety (aliases, local media, what leaves the device, retention, low-voltage only; see `docs/PRIVACY.md`).
14. Limitations (honest: fine-detail checks like LED flat edge and button rotation are allowed to be uncertain; soldering-joint quality is out of scope for reliable verification; lighting dependence; cloud latency).
15. Roadmap.
16. Project structure.
17. Team (placeholders).
18. License.

### 15.4 `docs/DEMO_SCRIPT.md` (≤ 3:00; ≥ 60 s continuous rig footage)

| Time | Shot | Voice-over / on-screen |
|---|---|---|
| 0:00–0:15 | Busy lab B-roll or a staged bench; a circuit that won't light | The problem: one TA, many benches; mistakes found only at power-on (`{{TA_RATIO_CONFIRMED}}`). |
| 0:15–0:30 | Rig close-up: camera over the board, marker mat, laptop with the bench view | Meet Polarity: an AI lab partner on the bench. |
| 0:30–1:45 | **Continuous hardware footage** (picture-in-picture: real hands and board + screen) | s1 PASS → s3 with a **reversed LED** → ⚠ FIX with spoken hint L1 → student fixes → ✓ PASS. Glare moment → ? CAN'T TELL "tilt away from the light" → retake → PASS. Student holds V: "Which leg is longer?" → spoken answer. s6: hold button → LED lights → objective LED-lit detection + PASS. |
| 1:45–2:15 | TA dashboard (simulated banner visible) | Help queue with Super's summary, heatmap, step insights, "Generate class report" → Ultra report. |
| 2:15–2:40 | Architecture SVG + Debug panel | Edge vs cloud split, model routing (Omni / Super / Ultra / Nano), JSON verdicts, and the **real eval numbers**. |
| 2:40–3:00 | Back to the student; logo | Impact and what's next (any lab sheet → verifiable steps; Jetson bench units). |

Recording tips:
- OBS Studio (free) for screen + webcam;
- phone on a tripod for the bench;
- captions on;
- no copyrighted music (use silence or royalty-free tracks you have rights to);
- show a real Token Factory model ID on screen at least once.

### 15.5 `docs/DEVPOST.md`

Draft the Devpost fields:
- Inspiration;
- What it does;
- How we built it (name the models and roles, the edge CV, the decision policy);
- Challenges (fill from DECISIONS/PHASE0 reality);
- Accomplishments;
- What we learned;
- What's next;
- Built with (Python, FastAPI, OpenCV/ArUco, NVIDIA Nemotron 3 Nano Omni/Super/Ultra/Nano, Nebius Token Factory, Tavily, SQLite).

Rules for the draft:
- Mark every factual claim that needs confirmation with `[VERIFY]`.
- Never include simulated numbers as results.

### 15.6 `docs/FEEDBACK.md` (for the required feedback + Most Valuable Feedback prize)

Auto-draft concrete, constructive feedback from real Phase 0 findings:
- model ID discovery and case sensitivity behaviour;
- base URL clarity;
- multimodal payload docs (audio/video content-part formats);
- JSON/tool support;
- latency observations;
- credits onboarding;
- docs gaps.

Each item gets: what happened → impact → specific suggestion. Leave `TODO-TEAM` slots for the team's own experiences.

### 15.7 Other docs

- `docs/PRIVACY.md`:
  - aliases only;
  - media stays on the bench;
  - only the checked frame and optional voice clip are sent to Token Factory at check time;
  - retention and purge;
  - designed around data-minimisation principles (mention Singapore's PDPA as context; make no legal claims);
  - refer to Nebius's own terms for their data handling.
- `docs/EDGE_DEVICES.md`: Raspberry Pi 5 / Jetson Orin Nano notes (Linux setup, V4L2 camera, Chromium kiosk mode).
- `docs/TEAM_TODO.md`: a checklist of human tasks with suggested dates (Section 16.2).
- `docs/DECISIONS.md`: everything decided autonomously.

**Acceptance (Phase 7):**
- On a clean macOS machine and a clean Windows machine: setup script → doctor all green (except camera permission prompts) → run → demo mode works.
- CI green.
- README renders correctly on GitHub.
- The LICENSE is detected as MIT.

---

## 16. DEFINITION OF DONE AND TEAM PLAN

### 16.1 Definition of done (Claude Code verifies each, ticking in the final report)

- [ ] Phase 0 report + capabilities.json exist (or PENDING with a clear reason)
- [ ] Live check loop works with real Token Factory calls (or PENDING key)
- [ ] Quality gate prevents wasted cloud calls and gives specific retake instructions
- [ ] Decision policy is code-driven and unit-tested
- [ ] LED-lit physical cross-check works on the rig (or PENDING hardware)
- [ ] Bench UI: all states designed and working; captions + voice; keyboard shortcuts
- [ ] TA dashboard: help queue, heatmap, insights, report; simulated banner
- [ ] Mock mode is clearly labelled; demo mode runs with no hardware and no key
- [ ] Budget guard and cost logging work
- [ ] P1: lab compiler, Tavily lookup (runtime call), board audit, hub mode
- [ ] Tests green on macOS/Windows/Linux CI; ruff clean
- [ ] Setup/run/verify scripts work on macOS and Windows
- [ ] README complete with the Nemotron/Token Factory section and quick starts; MIT LICENSE at root
- [ ] DEMO_SCRIPT, DEVPOST, FEEDBACK, PRIVACY, DECISIONS, TEAM_TODO written
- [ ] No secrets committed; `.env` gitignored; keys never printed in full

### 16.2 Team timeline (write into TEAM_TODO.md; today is Wed 21 Oct 2026, SGT)

| Date | Milestone |
|---|---|
| Wed 21 – Thu 22 Oct | Phase 0 live with key; buy/collect the kit; print the marker mat; build the rig |
| Thu 22 – Sat 24 Oct | Phases 1–3 working live on the real rig |
| Sun 25 Oct | Phase 4; confirm the TA ratio + get a quote from a real TA |
| Mon 26 Oct | Capture the eval dataset (≥ 5 photos per step/label) |
| Tue 27 Oct | Eval + tuning iterations; P1 features if on track |
| Wed 28 Oct | Docs, README, architecture SVG; record the video |
| Thu 29 Oct | Edit the video, upload to YouTube (public); fill Devpost; **internal deadline 23:59** |
| Fri 30 Oct | Buffer; final submit by evening SGT (hard deadline Sat 31 Oct 01:00 SGT) |

---

## 17. FINAL REPORT FORMAT (print at the end of the run AND save as `docs/BUILD_REPORT.md`)

```
# Polarity build report
## Summary (5 lines)
## Phase 0 results
| Role | Exact model ID | Case used | Latency |
Base URL: ...
OMNI COMBINED IMAGE+AUDIO → <STATUS>  (evidence: "<reply excerpt>")
Capabilities: json_mode=..., tools_mode=..., thinking_control=..., audio_mode=...
## What works (by phase)
## What is PENDING and why (key / hardware / dataset)
## How to run (macOS) — 3 commands
## How to run (Windows) — 3 commands
## Human to-do list (ordered)
## Known risks + mitigations
## Decisions made autonomously (link to DECISIONS.md)
```

---

## 18. KNOWN UNKNOWNS AND FALLBACKS

| Unknown | Why it matters | How the build handles it |
|---|---|---|
| Exact model IDs | Every call depends on them | Discover via `/models`, heuristics, `.env` overrides |
| Lowercase requirement (team-reported) | Could cause "not found" | Exact-first, lowercase-fallback; recorded per model |
| Base URL | Two variants documented | Probe list + override |
| Audio content-part format | OpenAI `input_audio` vs `audio_url` | Phase 0 tries both; stores the working variant |
| Image + audio in one call | Might be rejected or one modality ignored | Proof-based test; AUDIO_MODE fallbacks (`omni_separate` → `browser_stt` → `typed`) |
| Video input | Not needed | Optional test only |
| JSON enforcement | Parsing reliability | `json_schema` → `json_object` → prompt + repair |
| Tool calling on Super | Tavily agent design | `native` or `manual` mode |
| Reasoning/thinking output | Latency, parsing | Strip `<think>`/`reasoning_content`; disable for interactive roles if supported |
| Per-model prices | Budget guard accuracy | `pricing.yaml` filled from console; cost "n/a" until then |
| Ultra availability/cost | Report generation | Fallback to Super |
| Omni accuracy on real breadboards | **Core product risk** | Edge warp + quality gate; `allow_uncertain`; second look; LED-lit ground truth; eval gate with honest numbers |
| Hardware available to the team | Physical AI demo | Any webcam works; demo mode for no-hardware runs; Pi/Jetson optional |
| TA ratio fact | Impact claim | Placeholder until confirmed by a real TA |

**End of build prompt.** Build it completely, honestly, and beautifully.
