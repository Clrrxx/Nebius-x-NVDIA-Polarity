# Team to-do (things only humans can do)

Today is Wed 21 Oct 2026 (SGT). Hard deadline: **Sat 31 Oct 2026, 01:00 SGT** (Fri 30 Oct, 10:00 PDT).
Internal deadline: **Thu 29 Oct 23:59 SGT**.

## Ordered checklist

- [ ] **Get the Token Factory key into `.env`** and run `scripts/verify_mac.sh` (or `scripts\verify_windows.bat`).
  This fills in `docs/PHASE0_REPORT.md`, `data/capabilities.json` and the README model table. Commit the report.
- [ ] **Copy real prices** from the Token Factory console into `config/pricing.yaml` (the budget guard needs them).
- [ ] Optional: get a `TAVILY_API_KEY` (Best Use of Tavily bonus) and try `NE555` from the bench.
- [ ] **Change `TA_PIN`** in `.env` before any demo or recording.
- [ ] **Print the marker mat** (`assets/print/marker_mat_A4.pdf`) at 100% and check the 1 cm bar with a ruler.
- [ ] **Buy or collect the Lab 1 kit**: half-size breadboard, 2×AA holder with switch, red LED, 100 Ω resistor,
  6×6 mm push button, jumpers.
- [ ] **Build Lab 1 once for real** and confirm the LED lights; adjust `labs/lab1.yaml` if your kit differs.
- [ ] **Build the rig**: camera 25–35 cm above the board, lamp or ring light, mat taped down. Run
  `python -m polarity calibrate` and paste the printed thresholds into `config/settings.yaml`.
- [ ] **Confirm the TA ratio with a real SIT lab TA** and get a one-line quote. Replace every `{{TA_RATIO_CONFIRMED}}`
  (README, DEVPOST, DEMO_SCRIPT). Do not state a ratio before this.
- [ ] **Capture the evaluation dataset**: at least 5 photos per (step, label) with varied lighting, about 80–120 photos
  (~45 min): `python -m polarity capture --step s3 --label E_LED_REVERSED` …, plus `--label _baseline` for s6.
- [ ] **Run the real eval** (`python -m polarity eval`) and tune in the order in docs/EVAL_RESULTS.md, logging each
  iteration. Only these numbers may be quoted anywhere.
- [ ] **Record the demo video** following `docs/DEMO_SCRIPT.md` (≥ 60 s continuous rig footage; real model ID on
  screen; simulated banner visible on the TA segment).
- [ ] Upload the video to YouTube (**public**), put the link in the README (`{{YOUTUBE_URL}}`) and Devpost.
- [ ] Replace the README hero screenshot with a GIF of the real rig; add a rig photo; fill in the Team table.
- [ ] Fill in the `TODO-TEAM` / `[VERIFY]` items in `docs/DEVPOST.md`, `docs/FEEDBACK.md` and the README's
  "Where Token Factory accelerated our workflow".
- [ ] Push to GitHub (public repo) and check that CI is green on Linux, macOS and Windows.
- [ ] Submit on Devpost.

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
