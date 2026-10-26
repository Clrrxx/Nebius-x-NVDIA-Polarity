# Team to-do (things only humans can do)

Updated Thu 22 Oct 2026 (SGT). Hard deadline: **Sat 31 Oct 2026, 01:00 SGT** (Fri 30 Oct, 10:00 PDT).
Internal deadline: **Thu 29 Oct 23:59 SGT**.

## Done

- [x] Token Factory key in `.env` (committed and shared; the app reads it). Phase 0 passed live on 22 Oct:
  `docs/PHASE0_REPORT.md`, README model table.
- [x] 27 Oct: T3 "Text smoke test" FAIL with `fast_text: APITimeoutError` is Nano 30B hanging on Token Factory's
  side (5 of 6 direct calls timed out that night), not our code. The app now falls back to Super when Nano hangs,
  and verify retries once. T7/T8 audio FAIL/REJECTED is expected (our account has no Omni model).
- [x] Real prices in `config/pricing.yaml`.
- [x] First 12 rig photos in `data/real_photos/`. The board locator handles their hand-placed marker layout.

## Ordered checklist

- [ ] **Every teammate: pull, run setup, run verify once.** macOS: `scripts/setup_mac.sh`, `scripts/verify_mac.sh`,
  `scripts/run_mac.sh`. Windows: the matching `.bat` files. `verify` writes this machine's `data/capabilities.json`
  (gitignored) and also rewrites `docs/PHASE0_REPORT.md` and the README model table. Don't commit those two unless the
  results really changed (`git checkout -- README.md docs/PHASE0_REPORT.md`).
- [ ] **Before the repo goes public: rotate the key and remove `.env` from git history** (commit e970896 added it
  with the shared key). After that, everyone keeps the new key in their own `.env.local` (gitignored).
- [ ] **Change `TA_PIN`** before any demo or recording: put `TA_PIN=…` in `.env.local` on the demo laptop. That file
  is gitignored, so the change never shows up in `git status`/`git diff`; that is expected. Restart the app after.
- [ ] Optional: get a `TAVILY_API_KEY` (Best Use of Tavily bonus) and try `NE555` from the bench.
- [ ] **Decide the demo lab and match the kit.** Lab 1 is a 3 V battery pack, push button and red LED on a
  breadboard; `lab1_5v` is the same circuit on a 5 V supply. The rig photos show a full-size breadboard, a blue LED,
  a resistor, jumpers and an Arduino UNO, but no battery pack or push button yet. Either get the Lab 1 parts (2×AA
  holder with switch, 6×6 mm push button, red LED, 100 Ω resistor), or set `DEFAULT_LAB=lab1_5v`, power the rails
  from the UNO's 5V and GND pins, add a push button and a 220 Ω resistor, and set `led_check.colour: blue` in the lab
  file if the LED stays blue. Build it once for real and fix the wording or strip numbers in the lab file.
- [ ] **Build the rig**: camera 25–35 cm above the board, a lamp, the four markers taped at the board's corners (any
  order and rotation; the whole board inside the rectangle they outline). Check the layout with
  `python -m polarity locate <photo>` or the bench's "What the AI sees" view, then run `python -m polarity calibrate`
  and paste the printed thresholds into `config/settings.yaml`.
- [ ] **Confirm the TA ratio with a real SIT lab TA** and get a one-line quote. Replace every `{{TA_RATIO_CONFIRMED}}`
  (README, DEVPOST, DEMO_SCRIPT). Do not state a ratio before this.
- [ ] **Capture the evaluation dataset**: at least 5 photos per (step, label) with varied lighting, about 80–120 photos
  (~45 min): `python -m polarity capture --step s3 --label E_LED_REVERSED` …, plus `--label _baseline` for s6.
- [ ] **Run the real eval** (`python -m polarity eval`) and tune in the order in docs/EVAL_RESULTS.md, logging each
  iteration. Only these numbers may be quoted anywhere. Watch false passes closely: one live check passed a
  synthetic shorted-resistor board.
- [ ] **Record the demo video** following `docs/DEMO_SCRIPT.md` (≥ 60 s continuous rig footage; real model ID on
  screen; simulated banner visible on the TA segment).
- [ ] Upload the video to YouTube (**public**), put the link in the README (`{{YOUTUBE_URL}}`) and Devpost.
- [ ] Replace the README hero screenshot with a GIF of the real rig; add a rig photo; fill in the Team table.
- [ ] Fill in the remaining `TODO-TEAM` / `[VERIFY]` items: `docs/DEVPOST.md` (TA ratio, "works on real hardware"
  after the rig build, lessons learned), `docs/FEEDBACK.md` ("Our own experience"). Done: the Super VL model list in
  DEVPOST/DEMO_SCRIPT (Wenjie, 26 Oct) and the README's "Where Token Factory accelerated our workflow" (27 Oct).
- [ ] Check that CI is green on Linux, macOS and Windows (GitHub → Actions).
- [ ] Make the repo public (after the key is rotated and purged) and submit on Devpost.

## Timeline

| Date | Milestone |
|---|---|
| Wed 21 – Thu 22 Oct | Phase 0 live with the key; buy/collect the kit; print the marker mat; build the rig |
| Thu 22 – Sat 24 Oct | Phases 1–3 working live on the real rig |
| Sun 25 Oct | Phase 4; confirm the TA ratio + get a quote from a real TA |
| Mon 26 Oct | Capture the eval dataset (≥ 5 photos per step/label) |
| Tue 27 Oct | Eval + tuning iterations; P1 features if on track |
| Wed 28 Oct | Docs, README, architecture SVG; record the video |
| Thu 29 Oct | Edit the video, upload to YouTube (public); fill Devpost; **internal deadline 23:59** |
| Fri 30 Oct | Buffer; final submit by evening SGT (hard deadline Sat 31 Oct 01:00 SGT) |
