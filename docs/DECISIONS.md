# Decisions log

Choices made while building without stopping to ask (BUILD_PROMPT.md rule 0.4). Each entry says what was
decided, why, and how to change it. Newest phase at the bottom.

## Phase 0: infrastructure verification

| Date | Decision | Reason | How to change it |
|---|---|---|---|
| 2026-10-21 | Replaced the Apache-2.0 `LICENSE` from the repo's initial commit with MIT, copyright "2026 The Polarity Team". | Section 1 of the build prompt requires MIT at the repo root. | `git checkout e2fe0c4 -- LICENSE`, then update `license` in `pyproject.toml` and the README badge. |
| 2026-10-21 | `requires-python = ">=3.11,<3.13"` in `pyproject.toml`. | The prompt says 3.12 recommended, 3.11 supported, not 3.13; pip now refuses unsupported versions up front instead of failing later on a wheel. | Edit `requires-python` once all dependencies ship wheels for newer Pythons. |
| 2026-10-21 | Phase 0 talks to the raw OpenAI-compatible client, not `ModelRouter`. | The router is configured from `data/capabilities.json`, which Phase 0 produces. Every probe call's tokens are still totalled, printed and written to the report. | None needed; this is the only code path that bypasses the router. |
| 2026-10-21 | T3 counts HTTP 200 as PASS and records "says OK" separately. | With `max_tokens=16` a reasoning model can spend the whole budget thinking and return empty content even though the model works. | `t3_smoke` in `polarity/verify/run_verify.py`. |
| 2026-10-21 | Thinking control: a variant "works" when the reply says OK and no reasoning text appears. Prefer `chat_template_kwargs` if it works for both perception and reasoning, else `system_flag`, else whichever works for perception, else `none`. | Perception is the latency-critical role. When nothing works, later probes use `max_tokens >= 1500` so thinking cannot starve the answer. | `t4_thinking` and `_mt` in `run_verify.py`. |
| 2026-10-21 | T9 reports `ACCEPTED_UNVERIFIED` when the API returns 200 but the digits are wrong. | The listed values (`VERIFIED`/`REJECTED`/`SKIPPED`) cannot describe that case honestly. Video is not used by the product. | `t9_video`. |
| 2026-10-21 | If only the 1 kHz tone could be produced, T7 is `INFO`, `audio_input.supported=false`, T8 is `UNPROVEN`, and the recommended audio mode is `browser_stt`. | A tone cannot prove the model understood speech, so it must not unlock the omni audio modes. | Install a TTS engine (Linux: `espeak-ng`) or run `verify --record`. |
| 2026-10-21 | T12 makes its own tiny Ultra call with thinking allowed, separate from the T3 smoke call. | `deep` is the only role that runs with thinking on, so availability and latency are measured that way. | `t12_ultra`. |
| 2026-10-21 | A run without a key writes nothing; any run with a key writes the latest report (and `capabilities.json` once a base URL works). | A keyless run must never overwrite a good report; git history keeps earlier reports. | `Verifier.run`. |
| 2026-10-21 | `data/capabilities.json` is gitignored; `data/capabilities.example.json` (illustrative values only) is committed. | Each machine generates its own file; the prompt asks for a gitignored copy plus a committed example. | `.gitignore`. |
| 2026-10-21 | Added optional env overrides `POLARITY_HOME`, `POLARITY_DATA_DIR`, `POLARITY_ENV_FILE`, `POLARITY_DOCS_DIR`. | Tests run against temp folders and must never touch the real database, `.env` or docs. | `polarity/paths.py`. |
| 2026-10-21 | Requirements keep lower bounds; `requirements.lock.txt` records the exact versions installed on the dev Mac (openai 3.x, OpenCV 5.0, Pillow 13, FastAPI 0.15x, Starlette 1.x). | The prompt asks for lower bounds plus a frozen lock file for reproducibility. The code avoids APIs that differ between the lower bounds and these versions. | `pip install -r requirements.lock.txt` reproduces the tested set on macOS arm64. |
| 2026-10-21 | The offline test suite runs the full T1–T12 pipeline against a local fake Token Factory (`tests/fake_token_factory.py`). | No API key is available yet. The fake lists a mixed-case Omni ID that only works lowercased, rejects `input_audio` and `json_schema`, and returns `reasoning_content`, so every fallback path is exercised. It proves the verifier logic only; it is not evidence about the real API. | `tests/test_phase0_verify.py`. |
