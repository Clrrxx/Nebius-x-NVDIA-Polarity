# Demo video script (under 3:00, with at least 60 s of continuous rig footage)

Rules from the hackathon: public YouTube, under 3 minutes, shows the project working and how Token Factory and
Nemotron are used; Physical AI needs at least 1 minute of the hardware actually operating; no copyrighted music.

Record the bench in **live mode** (`POLARITY_MOCK_MODELS=0`, real camera). The only allowed simulated data is the
seeded class on the TA dashboard, and its "simulated data" banner must stay visible.

| Time | Shot | Voice-over / on-screen |
|---|---|---|
| 0:00–0:15 | Busy lab B-roll or a staged bench; a circuit that won't light | The problem: one TA, many benches ({{TA_RATIO_CONFIRMED}}); wiring mistakes only show up at power-on. |
| 0:15–0:30 | Rig close-up: camera over the board, marker mat, laptop with the bench view | Meet Polarity: an AI lab partner on the bench. |
| 0:30–1:45 | **Continuous hardware footage**, picture-in-picture (hands + board, and the screen) | Step 1 → PASS. Step 3 with the **LED reversed** → FIX with the spoken level-1 hint → the student flips it → PASS. Tilt into the lamp → glare → **CAN'T TELL** "tilt away from the light" → retake → PASS. Hold V: "Which leg is longer?" → spoken answer. Step 6: hold the button, LED lights → **"Confirmed by the on-device LED detector"** + PASS. |
| 1:45–2:15 | TA dashboard (simulated banner visible) | Help queue with Super's summary, heatmap, step insights, "Generate class report" → Ultra report. |
| 2:15–2:40 | Architecture diagram + `/debug` panel | Edge vs cloud split; model routing (Omni / Super / Ultra / Nano) with the **real model IDs** from Phase 0; JSON verdicts; the **real eval numbers** from docs/EVAL_RESULTS.md (only if the eval has been run). |
| 2:40–3:00 | Back to the student; logo | Impact and what's next: any lab sheet → verifiable steps; Jetson bench units. |

## Shot checklist

- [ ] A real Token Factory model ID visible on screen at least once (bench footer or the Debug routing table).
- [ ] The "What the AI sees" inset visible during the bench segment.
- [ ] Captions on; no music, or only tracks you have rights to.
- [ ] No real student names (use nicknames). No API keys on screen (the Debug page never shows them).
- [ ] The simulated-data banner visible whenever the seeded class is on screen.
- [ ] Do not quote accuracy numbers unless they come from a real `polarity eval` run.

## Recording tips

OBS Studio (free) for screen + webcam picture-in-picture; a phone on a tripod for the bench; the LED ring light on.
Rehearse once with `scripts/run_mac.sh`. Before recording, run `python -m polarity seed-demo` for the TA segment
and `python -m polarity seed-demo --clear` afterwards.
