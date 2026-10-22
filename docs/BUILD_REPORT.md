# Polarity build report

## Summary (5 lines)

1. All eight phases (0–7) are built and committed locally, one commit per phase: about 9,500 lines of Python, 1,700 of
   vanilla JS, 163 tests passing offline on macOS (Python 3.12), `ruff` clean.
2. Phase 0 ran live on 2026-10-22 against `https://api.tokenfactory.nebius.com/v1/` (exit 0, about $0.001). The
   account has no Nano Omni model and rejects audio input, so perception runs on Nemotron 3.5 Super VL and speech
   is recognised in the browser. Exact IDs, latencies and evidence: docs/PHASE0_REPORT.md.
3. Without the key, the whole product runs in demo mode (synthetic boards + canned answers, MOCK MODE bar on every
   screen). The Phase 0 verifier and the router's live path were exercised end to end against a local fake
   OpenAI-compatible server.
4. Hardware-dependent checks (real webcam, LED detector on the rig, microphone and speech in a real browser) and
   the real evaluation dataset are **PENDING the rig and team photos**. No accuracy number exists yet.
5. The phase commits and the fixes after the first live run are on `origin/main` (see "After the first live run").

## Phase 0 results

| Role | Exact model ID | Case used | Latency |
|---|---|---|---|
| perception | `nvidia/Nemotron-3.5-Super-VL` (no Omni on the account; VL fallback) | exact | 2278 ms |
| fast_text | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | exact | 866 ms |
| reasoning | `nvidia/nemotron-3-super-120b-a12b` | exact | 895 ms |
| deep | `nvidia/Nemotron-3-Ultra-550b-a55b` | exact | 779 ms |

Base URL: `https://api.tokenfactory.nebius.com/v1/` (28 models). The us-central1 host lists no vision model for
this account, and `https://tokenfactory.nebius.com/` is the console web page, not the API.

OMNI COMBINED IMAGE+AUDIO → REJECTED (HTTP 422: content parts must be `text`, `image_url` or `video_url`)

Capabilities: json_mode=json_schema, tools_mode=native, thinking_control=chat_template_kwargs, audio_mode=browser_stt,
video input VERIFIED. A probe on 2026-10-22 confirmed `enable_thinking: false` stops reasoning on Nano 30B, Super and
Super VL (T4 marks Super "no" only because it did not reply with exactly "OK").

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
| Live checks, voice Q&A, TA summaries, class report, lab compiler tried on the real rig | the rig (one live check on a synthetic board worked in about 2–3 s) |
| Tavily lookup returning real cited sources for "NE555" | `TAVILY_API_KEY` |
| Real webcam preview/chips, LED detector thresholds on the rig, mic + speech in a browser | the rig (hardware) |
| Evaluation numbers (false-pass, selective accuracy, …) | team photos (`polarity capture`) |
| CI green on Linux/macOS/Windows | check the Actions tab after the push |
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
| A live check passed a synthetic shorted-resistor board (one run, 2026-10-22) | Synthetic images are not evidence either way; capture real error photos and run `eval` before trusting PASS |
| The shared key is committed in `.env.local` | Fine while the repo is private; rotate the key and purge the file from history before it goes public |

## After the first live run (2026-10-22)

- The app reads `.env` and then `.env.local` (the team keeps the shared key there); real environment variables win.
- `verify` and `doctor` now say when `NEBIUS_BASE_URL` is the console page instead of the API, and suggest the URL
  that works. Without a configured URL, `verify` picks the endpoint that resolves the most roles (including vision).
- Model overrides and `config/pricing.yaml` keys corrected to the exact IDs the account lists.
- The board locator accepts hand-placed markers in any order and rotation, measures the board's real shape from the
  markers (a full-size breadboard warps to about 1024×352, turned to landscape) and infers a hidden marker's corner.
  Checked on the team's first 12 rig photos (`data/real_photos/`, all found). New command: `python -m polarity locate`.

## Decisions made autonomously

See [DECISIONS.md](DECISIONS.md): every choice made without asking, per phase, with the reason and how to change it.
