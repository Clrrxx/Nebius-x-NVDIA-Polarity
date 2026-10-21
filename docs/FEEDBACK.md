# Feedback on Nebius Token Factory, Nebius AI Cloud and NVIDIA tools

Draft for the submission's required feedback and the "Most Valuable Feedback" prize. Each item says what happened,
the impact, and a specific suggestion. Items marked **Observed** come from building this project; items marked
**To confirm** come from documentation gaps we planned around and will be confirmed or removed after the live
Phase 0 run (`python -m polarity verify`, report in `docs/PHASE0_REPORT.md`).

## 1. Which base URL is canonical? (Observed)

**What happened.** We found two documented hosts, `api.tokenfactory.us-central1.nebius.com/v1/` (Nemotron page) and
`api.tokenfactory.nebius.com/v1/` (older snippet), plus the legacy `api.studio.nebius.com/v1/`. Without a key, all
three answer `GET /v1/models` with HTTP 401, so there is no way to tell which one is current before onboarding.
**Impact.** We wrote a probe that tries each in turn, and teams copying an old snippet may silently use a deprecated
host. **Suggestion.** Publish one canonical base URL on every page and in the console, and have legacy hosts return
a `Deprecation`/`Link` header pointing to it.

## 2. Model-ID case sensitivity (To confirm)

**What happened.** Team members reported that model IDs in completion requests must be lowercase, while `/v1/models`
can list mixed-case IDs (for example `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`). **Impact.** We had to implement
"exact ID first, lowercase on not-found" and record the working form per model. **Suggestion.** Match model IDs
case-insensitively, or document the rule next to the `/v1/models` reference with one example.

## 3. Multimodal content-part formats for Nano Omni (To confirm)

**What happened.** We could not find documentation of which audio content-part shape Nemotron 3 Nano Omni accepts
on Token Factory (`input_audio` with base64 data vs `audio_url` with a data URL), whether image and audio can share
one request, or the video size and length limits. **Impact.** Phase 0 has to probe every variant and verify
understanding with test assets, and the app needs four audio fallbacks. **Suggestion.** A per-model "accepted
content parts" table with one working request each (image, audio, image+audio, video), including size and
duration limits.

## 4. Structured output support per model (To confirm)

**What happened.** It is unclear which models support `response_format={"type": "json_schema", ...}` with
`strict: true`, and which JSON Schema keywords are honoured. **Impact.** We generate a simplified schema, keep
Pydantic validation plus one repair call, and downgrade `json_schema` → `json_object` → prompt-only when a request is
rejected. **Suggestion.** List structured-output support and the supported keyword subset per model in the model
catalogue.

## 5. Turning reasoning off for Nemotron 3 (To confirm)

**What happened.** For latency-sensitive calls we want thinking off. It is not documented whether Token Factory
honours `chat_template_kwargs: {"enable_thinking": false}` (via `extra_body`) or a `/no_think` system prefix, or
where reasoning text appears (`reasoning_content` vs `<think>` in `content`). **Impact.** We probe both switches,
strip `<think>` blocks, and raise `max_tokens` when we can't turn thinking off, so the answer isn't truncated.
**Suggestion.** Document the supported switch and response field for each reasoning model, with an example.

## 6. Prices are not machine-readable (Observed)

**What happened.** To enforce a session/day budget we need per-model prices, which we can only copy by hand from the
console into `config/pricing.yaml`. **Impact.** Until someone copies them, our budget guard cannot stop spending and
costs show as "n/a". **Suggestion.** Include `pricing` (input/output per 1M tokens) in `/v1/models` or a `/v1/pricing`
endpoint.

## 7. Hackathon credits and products (Observed)

**What happened.** The promo credits cover Token Factory only, not AI Cloud (Serverless Endpoints, Jobs, DevPods).
This was clear in the rules, but easy to miss when exploring the console. **Impact.** We designed everything around
Token Factory calls from the bench. **Suggestion.** Show which products the active credit applies to directly in the
console's billing banner.

## 8. Tool calling on Nemotron 3 Super (To confirm)

**What happened.** We could not confirm whether OpenAI-style `tools` / `tool_calls` are enabled for Super on Token
Factory. **Impact.** The Tavily agent has a native path and a manual fallback. **Suggestion.** Mark tool-calling support
per model in the catalogue.

## Live findings from Phase 0 (TODO-TEAM after running verify)

- Latency per role (from `docs/PHASE0_REPORT.md`): TODO-TEAM
- Combined image + audio result (T8): TODO-TEAM
- Anything that surprised us (errors, rate limits, timeouts): TODO-TEAM

## Our own experience (TODO-TEAM)

- Onboarding / getting the key: TODO-TEAM
- Console and playground: TODO-TEAM
- NVIDIA Nemotron quality on breadboard photos (from the real eval): TODO-TEAM
