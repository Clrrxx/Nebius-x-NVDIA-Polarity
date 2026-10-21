# Polarity build report

## Summary (5 lines)

1. All eight phases (0–7) are built and committed locally, one commit per phase: about 9,500 lines of Python, 1,700 of
   vanilla JS, 157 tests passing offline on macOS (Python 3.12), `ruff` clean.
2. Every live part is **PENDING a `NEBIUS_API_KEY`**: no Token Factory call has been made, so model IDs, latencies
   and capabilities are not known yet. Phase 0 exits with code 4 and a clear message until the key is added.
3. Without the key, the whole product runs in demo mode (synthetic boards + canned answers, MOCK MODE bar on every
   screen). The Phase 0 verifier and the router's live path were exercised end to end against a local fake
   OpenAI-compatible server.
4. Hardware-dependent checks (real webcam, LED detector on the rig, microphone and speech in a real browser) and
   the real evaluation dataset are **PENDING the rig and team photos**. No accuracy number exists yet.
5. Nothing was pushed: the team decides when to push to the public repo (CI then runs on Linux, macOS and Windows).

## Phase 0 results

| Role | Exact model ID | Case used | Latency |
|---|---|---|---|
| perception | PENDING (needs NEBIUS_API_KEY) | — | — |
| fast_text | PENDING | — | — |
| reasoning | PENDING | — | — |
| deep | PENDING | — | — |

Base URL: PENDING. Observed without a key: `api.tokenfactory.us-central1.nebius.com`, `api.tokenfactory.nebius.com`
and `api.studio.nebius.com` all answer `GET /v1/models` with HTTP 401.

OMNI COMBINED IMAGE+AUDIO → PENDING (evidence will be in docs/PHASE0_REPORT.md)

Capabilities: json_mode=PENDING, tools_mode=PENDING, thinking_control=PENDING, audio_mode=PENDING. Until
`verify` runs, the app uses conservative defaults: prompt-only JSON + repair, manual tools, no thinking control,
browser speech recognition.

## What works (by phase)

- **Phase 0:** `verify` (T0–T12, exact-first/lowercase model IDs, thinking control, audio variants, combined image+audio
  proof, video, JSON modes, tools, Ultra), `capabilities.json`, the report, the standalone script, `.sh`/`.bat`
  wrappers. Exit codes 0/1/2/3/4 tested; full pipeline tested against a fake server.
- **Phase 1:** lab schema + Lab 1 (3 V), 5 V variant and soldering template; verbatim prompts; `ModelRouter` (roles,
  retries with jitter, JSON downgrade, repair, budget guard, cost log, fallback chain); ArUco board locator
  (3-marker homography completion), quality gate, motion, LED detector (skin rejection, occlusion guard); decision
  policy (24 table cases + second look); SQLite/media; synthetic boards; `eval --mock`.
- **Phase 2:** camera service (OS backends, reconnect, sharpest frame), demo camera, session engine (state machine, hint
  ladder, escalation), voice Q&A, FastAPI + WebSocket, MJPEG raw/warped streams, audio validation, browser
  recorder/TTS/speech recognition.
- **Phase 3:** design system (dark + light, AA-checked status colours), start screen, bench view (docked actions,
  verdict card, timeout/budget/error states, completion), TA dashboard (help queue, accessible heatmap with
  tooltips and timeline drawer, insights), debug panel (PIN-protected controls), logo and icons. Every UI state was
  screenshotted in both themes (docs/UI_CHECKLIST.md).
- **Phase 4:** background Nemotron Super help summaries, Ultra class report (falls back to Super; the simulated-data
  first line is enforced; Markdown rendered without raw HTML), seeded 28-student class (seed 10 tracks the target rates).
- **Phase 5:** lab-sheet compiler with editor (estimate → per-page progress → AI-drafted lab → review → publish;
  lossless round-trip verified), Tavily part lookup (native/manual, sources filtered to real results, cache), board
  audit ("bug hunt"), hub mode (persistent outbox, retries, no images by default).
- **Phase 6:** `capture` and `calibrate` rig tools, offline network guard for tests, Unicode-safe image I/O for
  Windows, CI workflow (3 OSes), PENDING `EVAL_RESULTS.md`.
- **Phase 7:** `doctor`, setup/run scripts (macOS tested on a fresh copy in a path with a space), README in the
  required order with live model/eval blocks, architecture SVG + Mermaid, demo script, Devpost draft, feedback,
  privacy, edge devices, team to-do.

## What is PENDING and why

| Item | Waiting on |
|---|---|
| Phase 0 live run, model IDs, PHASE0_REPORT, capabilities.json, README model table | `NEBIUS_API_KEY` |
| Live checks, voice Q&A, TA summaries, class report, lab compiler on real models | `NEBIUS_API_KEY` (+ verify) |
| Tavily lookup returning real cited sources for "NE555" | `TAVILY_API_KEY` |
| Real cost display and a working budget guard | prices copied into `config/pricing.yaml` |
| Real webcam preview/chips, LED detector thresholds on the rig, mic + speech in a browser | the rig (hardware) |
| Evaluation numbers (false-pass, selective accuracy, …) | team photos (`polarity capture`) + key |
| CI green on Linux/macOS/Windows | pushing to GitHub |
| Windows setup/run scripts executed on Windows | a Windows machine (written carefully, not executed here) |
| TA ratio, video link, team names, rig photos | humans (see TEAM_TODO.md) |

## How to run (macOS) — 3 commands

```bash
scripts/setup_mac.sh          # then paste NEBIUS_API_KEY into .env
scripts/verify_mac.sh
scripts/run_mac.sh            # demo without hardware or key: CAMERA_SOURCE=demo POLARITY_MOCK_MODELS=1 scripts/run_mac.sh
```

## How to run (Windows) — 3 commands

```bat
scripts\setup_windows.bat     & REM then paste NEBIUS_API_KEY into .env
scripts\verify_windows.bat
scripts\run_windows.bat
```

## Human to-do list (ordered)

1. Put the Token Factory key in `.env`, run verify, commit `docs/PHASE0_REPORT.md`.
2. Copy prices into `config/pricing.yaml`; optionally add `TAVILY_API_KEY`; change `TA_PIN`.
3. Print the marker mat at 100%, get the Lab 1 kit, build the circuit once, build the rig, run `calibrate`.
4. Confirm the TA ratio with a real SIT lab TA (+ quote) and replace `{{TA_RATIO_CONFIRMED}}`.
5. Capture ≥ 5 photos per (step, label) with `capture`; run `eval`; tune and log iterations.
6. Record the video per `docs/DEMO_SCRIPT.md`; upload publicly; add the link.
7. Fill the `TODO-TEAM` / `[VERIFY]` items; push to GitHub; check CI; submit on Devpost.

Full checklist with dates: [TEAM_TODO.md](TEAM_TODO.md).

## Known risks + mitigations

| Risk | Mitigation |
|---|---|
| Nemotron accuracy on real breadboard photos (core risk) | Top-down warp, quality gate, `not_visible` + `allow_uncertain`, second look, physical LED evidence, eval gate with honest numbers |
| Combined image + audio rejected or ignored | Proof-based Phase 0 test; automatic fallbacks (separate audio call → browser speech → typed) |
| Model IDs, case or base URL differ from expectations | Runtime discovery, exact-first/lowercase fallback, `.env` overrides |
| JSON schema or tools unsupported | Automatic downgrade + repair call; manual Tavily path |
| Budget overrun | Router budget guard (needs prices); demo mode for rehearsals |
| Lighting / glare on the rig | Ring light, `calibrate`, specific retake instructions |
| LED detector tuned only on synthetic frames | `calibrate` on the rig; it only overrides the model when evidence is strong |
| Windows scripts untested on Windows | CI runs the test suite on Windows; run `setup_windows.bat` on a team laptop early |
| Port 8765 busy (a Docker container uses it on this Mac) | `run` picks the next free port and prints the URL |

## Decisions made autonomously

See [DECISIONS.md](DECISIONS.md): every choice made without asking, per phase, with the reason and how to change it.
