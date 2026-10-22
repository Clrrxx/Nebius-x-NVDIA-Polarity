# Real rig photos

Photos of the team's real kit under the corner markers, taken with a phone on 21–22 Oct 2026. Each copy has its
orientation applied and all metadata removed, and is resized to a 2000 px long side (JPEG quality 90). The
full-resolution originals (1848×4000) stay on the team Drive.

## What they are for

- **Board locator regression tests.** `tests/test_edge.py` checks that `20261021_234020.jpg` (4 markers) and
  `20261021_233534.jpg` (one marker hidden) warp to a clean landscape view.
- **Seeing what the AI receives.** `python -m polarity locate data/real_photos/2026-10-21` saves the top-down views
  to `data/logs/locate/`.
- **Prompt, lab and threshold tuning on real boards.**

Polarity does not train or fine-tune a model. Nemotron is used as it is, so photos improve the product through the
evaluation set, the prompts and the thresholds. These photos show a different circuit from Lab 1 and have no labels,
so they are not evaluation data. For that, capture Lab 1 steps on the rig with `python -m polarity capture` (see
`data/eval/README.md`).

## The marker layout in these photos

Markers 0 and 1 sit upright along the top. Marker 2 (bottom-left) and marker 3 (bottom-right) are swapped compared
with the printed mat and turned 90°. A full-size breadboard sits between them. The locator handles this layout: it
measures the board at about 2.9–3.0 : 1, warps it to 1024 × about 350 px and turns it to landscape (column 1 on the
left). The LED in these photos is blue, while Lab 1 expects red: change `led_check.colour` in the lab file if you keep
a blue LED.

## 2026-10-21

| File | What is on the mat | Markers found |
|---|---|---|
| `20261021_231401.jpg` | Empty full-size breadboard. Annotated copy with red "3" and "0" drawn by the top markers; those are not the marker ids (top-left is id 0, top-right id 1). | 4 |
| `20261021_231444.jpg` | Empty full-size breadboard | 4 |
| `20261021_233159.jpg` | Arduino UNO (compatible board) on its own | 4 |
| `20261021_233232.jpg` | ESP32 dev board (ESP-WROOM-32) on its own | 4 |
| `20261021_233500.jpg` | A resistor lying loose, no breadboard | 4 |
| `20261021_233534.jpg` | Empty breadboard covering part of marker 1 | 3 (id 1 hidden) |
| `20261021_233608.jpg` | A blue LED lying loose, no breadboard | 4 |
| `20261021_233742.jpg` | Breadboard with a resistor and a blue LED, no wires | 4 |
| `20261021_233812.jpg` | Breadboard with a resistor only | 4 |
| `20261021_233928.jpg` | Resistor, blue LED and one yellow jumper | 4 |
| `20261021_234020.jpg` | Resistor, blue LED and two yellow jumpers | 4 |
| `20261022_000142.jpg` | The same circuit wired to an Arduino UNO. The UNO's red power LED is on; the blue LED does not look lit. | 4 |
