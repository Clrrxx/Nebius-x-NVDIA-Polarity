# Demo scenes

`python -m polarity render-synthetic` draws synthetic placeholder boards into `lab1/<step>/<label>.png`
(`correct`, every common error id, and special scenes `_empty`, `_dark`, `_blur`, `_glare`, `_markers`, `_hand`,
`_partial`). They power demo mode (`CAMERA_SOURCE=demo`) and CI. They are gitignored and re-rendered on demand.

**Never use these images for accuracy claims.** Real results come only from team photos in `data/eval/`.

To show real photos in demo mode, save them as `lab1/<step>/<label>.jpg` (for example `lab1/s3/E_LED_REVERSED.jpg`).
A team photo always takes precedence over the synthetic render with the same label.
