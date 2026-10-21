# UI checklist

Every state below was driven end to end in demo mode (`CAMERA_SOURCE=demo`, `POLARITY_MOCK_MODELS=1`), in both
the dark (bench) and light (projector) themes, at 1366×768. A Playwright script drove Microsoft Edge (headless)
through the real flow: start a session, pick demo scenes, press Space / click, and screenshot each state. The
screenshots were reviewed by eye for layout, overflow, contrast and wording. Every screen shows the amber
"MOCK MODE — NOT REAL AI OUTPUT" bar in this mode.

| State | How it was produced | Dark | Light | Notes |
|---|---|---|---|---|
| Quality fail (CAN'T TELL, no cloud call) | scene `s2/_glare`, Check | ✅ | ✅ | Caption "I can't tell yet…" plus one specific retake instruction with a tilt icon; Light/Focus/Glare chips turn amber with a warning icon. |
| PASS | scene `s1/correct`, Space | ✅ | ✅ | Banner icon + word + colour; "Next step" replaces Check in the action dock and takes focus (Enter works). |
| PASS · 1 thing to double-check | scene `s3/_partial` | ✅ | ✅ | Lists the fine-detail check the student should confirm themselves. |
| FIX, hint level 1 → 2 → 3 | scene `s4/E_BTN_NOT_STRADDLING`, three checks | ✅ | ✅ | Hint dots fill 1/2/3; the TA-authored hint line is hidden when it would repeat the caption; third FIX raises "TA notified". |
| CAN'T TELL (model: hands over board) | scene `s*/_hand` | ✅ | ✅ | Covered by API tests and checked manually; retake asks for hands out of frame. |
| Thinking | any Check | ✅ | ✅ | Step card collapses to its header, skeleton verdict, button counts "Looking closely… N s"; no layout jump when the verdict replaces the skeleton. |
| Timeout (30 s) | Debug → "Simulate slow model (35 s)" | ✅ | ✅ | "I couldn't reach the AI. Your work is saved — try Check again." The late answer still replaces it when it arrives. |
| Budget exceeded | Debug → "Simulate budget limit" | ✅ | ✅ | "BUDGET LIMIT" card with the scope and amount; no retry button. |
| Typed question / answer | ask form, "Which leg of the LED is longer?" | ✅ | ✅ | "You asked …" + answer bubble + model and latency footer. |
| Second look | scene `s4/correct` (mock confidence 0.78) | ✅ | ✅ | "second look" tag in the footer. |
| Power test pass (physical LED evidence) | scene `s6/correct` | ✅ | ✅ | "Confirmed by the on-device LED detector" and the detector's signal strength. |
| Completed | finish s6 | ✅ | ✅ | All steps ticked, total time, total checks, "Show your TA — great work". |
| Start screen | `/` | ✅ | ✅ | Five quality chips; Start enabled only when all are green (demo link bypasses in demo mode). |
| Debug panel | `/debug` | ✅ | ✅ | Routing, budget meter (warns when prices are empty), last 20 calls, live sliders, LED mask, scene picker, raw verdict, capabilities. Controls need the TA PIN. |
| TA PIN gate | `/ta` without cookie | ✅ | ✅ | |
| TA dashboard (live session) | `/ta` after a bench session | ✅ | ✅ | Help queue card, heatmap row, insights, counters. |
| TA with simulated data | Phase 4 seed | ⏳ | ⏳ | Verified in Phase 4. |
| Class report | Phase 4 report | ⏳ | ⏳ | Verified in Phase 4. |

Accessibility checks applied while reviewing: every status shows icon + word + colour; focus rings are visible
(3 px accent); buttons are at least 44 px tall; the verdict region is `aria-live="polite"`; captions are always on
screen, so speech is never the only channel; Space is ignored while typing; animations honour
`prefers-reduced-motion`; light-theme status and accent colours were darkened for contrast and checked with a
palette validator.

Not verifiable here (needs a person at the rig): real-webcam preview and chip behaviour, microphone capture and
speech playback in a real browser session, Safari's first-click audio unlock.
