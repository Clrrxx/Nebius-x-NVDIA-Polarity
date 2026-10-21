# Evaluation dataset (team photos)

Capture photos on the real rig with:

```bash
python -m polarity capture --lab lab1 --step s3 --label E_LED_REVERSED
```

Each Space press saves `NNNN_raw.jpg` and `NNNN_warped.jpg` into `lab1/<step>/<label>/`. Labels are `correct` or a
common error id from `labs/lab1.yaml`. Aim for at least 5 photos per (step, label) with slightly varied lighting.
For the power test, also capture LED-off photos into `lab1/s6/_baseline/`.

Then run `python -m polarity eval --dataset data/eval/lab1`; results go to `docs/EVAL_RESULTS.md`.
