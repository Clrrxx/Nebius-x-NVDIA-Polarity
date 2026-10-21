# Phase 0 report: Nebius Token Factory verification

**Status: PENDING, needs `NEBIUS_API_KEY`.**

No Token Factory API key was available when the repository was built (2026-10-21), so no live call has been
made yet and no model IDs, latencies or capabilities are recorded here. The only facts observed so far
without a key: all three candidate base URLs (`api.tokenfactory.us-central1.nebius.com`,
`api.tokenfactory.nebius.com`, `api.studio.nebius.com`) answer `GET /v1/models` with HTTP 401, so they
exist and require authentication.

To produce the real report:

```bash
cp .env.example .env            # Windows: copy .env.example .env
# paste NEBIUS_API_KEY=... into .env
scripts/verify_mac.sh           # Windows: scripts\verify_windows.bat
```

The run overwrites this file with the base URL, the exact model ID per role and the case that worked,
PASS/FAIL evidence for tests T0–T12 (including the critical combined image + audio test T8), error bodies,
token usage, and the recommended `AUDIO_MODE`. It also writes `data/capabilities.json`, which the
app reads at startup. Until then the app runs in mock mode (`POLARITY_MOCK_MODELS=1`) with a visible
MOCK MODE badge.
