# Devpost submission draft

Every factual claim that still needs confirming is marked **[VERIFY]**. Never paste simulated numbers (from the
seeded demo class or `eval --mock`) as results; only numbers from a real `python -m polarity eval` run may be used.

## Inspiration

In a first-year electronics lab, one TA supervises a whole room of benches ({{TA_RATIO_CONFIRMED}} [VERIFY with a
real SIT lab TA]). Beginners make the same handful of wiring mistakes: an LED in backwards, a resistor shorted inside
one strip, a button that doesn't straddle the channel. Those mistakes stay invisible until power-on, and then the
student has six steps to debug at once while waiting for the TA.

## What it does

Polarity is a camera-and-voice lab partner on each bench. It walks the student through the lab one step at a time,
checks each step from a top-down photo, explains what to fix with a hint ladder (where to look, what is wrong, the
exact fix), and says "I can't tell" with a specific retake instruction when the picture isn't good enough. Students
can ask spoken questions about the step. At power-on an on-device LED detector confirms the LED actually lit. The TA
gets a live dashboard: a help queue with AI summaries, a steps × students heatmap, step insights and an end-of-class
report. A TA can also turn any lab handout PDF into checkable steps.

## How we built it

- **Edge (bench computer):** Python, OpenCV ArUco markers on a printed mat to warp the board to a 1024×768
  top-down view; an on-device quality gate (focus, brightness, glare, markers, motion) so bad photos never reach
  the cloud; an LED-lit detector against a baseline frame (with skin rejection for the finger on the button).
- **Nebius Token Factory + NVIDIA Nemotron 3** (OpenAI-compatible API), routed by role:
  - **Nano Omni:** one call per check, board image plus the student's voice clip [VERIFY combined image+audio
    status from docs/PHASE0_REPORT.md];
  - **Nano 30B:** cheap text jobs;
  - **Super 120B:** TA triage, lab compiler, Tavily tool agent;
  - **Ultra:** end-of-class report.
  Model IDs are discovered at runtime and recorded with what the API accepts (JSON mode, thinking control, audio
  format, tool calling).
- **Code decides, not the model:** schema-validated JSON verdicts per check feed a deterministic policy. Thresholds
  are 0.75 to pass and 0.60 for FIX; fine details may be "not visible"; a second, zoomed look runs in the confidence
  grey zone; inconsistent output becomes CAN'T TELL, never a pass.
- **Tavily:** runtime web search for part pinouts, summarised by Super from those sources only, with citations.
- **App:** FastAPI + WebSocket, vanilla JS (no build step), SQLite, setup scripts for macOS and Windows, CI on
  three OSes, an evaluation harness that reports the false-pass rate.

## Challenges we ran into

- **Honest uncertainty is a design problem, not a prompt.** We needed a quality gate, `not_visible` as a valued
  answer, an `allow_uncertain` flag for fine details and a second-look rule before "can't tell" felt trustworthy
  rather than evasive.
- **A finger looks like a lit LED.** In HSV, skin is "reddish" and rises above the baseline wherever it covers dark
  holes. We added a YCrCb skin band, roundness checks and an occlusion rule so physical evidence only overrides the
  model when it is unambiguous.
- **Perspective breaks the textbook trick.** Completing a hidden marker as a parallelogram was off by 26 px on a
  tilted test frame; fitting a homography to all twelve visible marker corners fixed it.
- **Not knowing the API surface in advance.** Model-ID casing, audio content-part formats, JSON-schema support and
  thinking control all had to be probed rather than assumed. Phase 0 tests each one with inputs whose answers prove
  the modality was understood. [VERIFY: add what the live Phase 0 run actually found.]
- **Cross-platform details:** OpenCV can't open non-ASCII Windows paths, so we encode and decode in memory;
  `setup_windows.ps1` handles spaces in user names.

## Accomplishments that we're proud of

A complete, working system on real hardware [VERIFY after the rig build]: an edge pipeline that saves cloud calls,
a deterministic and fully unit-tested decision policy, a power test grounded in physics, and a TA dashboard that
turns individual struggles into a class picture. The UI states each verdict with an icon, a word and a colour, keeps
captions on, and works from the keyboard.

## What we learned

TODO-TEAM: two or three honest lessons (for example, what the real eval showed about lighting or fine details).

## What's next

Any lab sheet → verifiable steps across more courses; Jetson Orin Nano bench units; soldering and multimeter labs
with honest "TA review" for what a camera can't judge; multilingual voice.

## Built with

Python · FastAPI · OpenCV (ArUco) · NumPy · Pydantic · SQLite · NVIDIA Nemotron 3 Nano Omni · Nemotron 3 Nano 30B ·
Nemotron 3 Super 120B · Nemotron 3 Ultra · Nebius Token Factory · Tavily · Web Audio · Web Speech API
