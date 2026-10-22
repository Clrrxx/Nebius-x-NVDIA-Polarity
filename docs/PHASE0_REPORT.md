# Phase 0 report: Nebius Token Factory verification

- **Run at:** 2026-10-22 12:26+08:00
- **Base URL:** `https://api.tokenfactory.nebius.com/v1/`
- **Machine:** Darwin 25.3.0 arm64 · Python 3.12.12
- **API key:** ****KvAG

## Resolved models

| Role | Exact model ID | Case used | Latency (ms) |
|---|---|---|---|
| `perception` | `nvidia/Nemotron-3.5-Super-VL` | exact | 2278 |
| `fast_text` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | exact | 866 |
| `reasoning` | `nvidia/nemotron-3-super-120b-a12b` | exact | 895 |
| `deep` | `nvidia/Nemotron-3-Ultra-550b-a55b` | exact | 779 |

> No Nemotron Omni model listed; using a Nemotron VL model for perception.

## Capabilities

- **OMNI COMBINED IMAGE+AUDIO:** `REJECTED`
- **Audio input:** supported=False, variant=`None` (audio asset method: say)
- **Video input:** `VERIFIED`
- **JSON mode:** `json_schema` · **Tools mode:** `native` · **Thinking control:** `chat_template_kwargs`
- **Perception fallback to VL:** True

## Recommended AUDIO_MODE

`browser_stt`: Audio understanding could not be proven via the API, so the browser's Web Speech API transcribes speech (Chrome/Edge), with a typed box as the fallback.

## Tests

| Test | Status | Details |
|---|---|---|
| T0 Environment | **PASS** | Python 3.12.12 on Darwin arm64; packages OK; cv2 available (video test possible); NEBIUS_API_KEY=****KvAG |
| T1 Base URL probe | **PASS** | Using https://api.tokenfactory.nebius.com/v1/ (from NEBIUS_BASE_URL) |
| T2 Model discovery | **PASS** | perception=nvidia/Nemotron-3.5-Super-VL, fast_text=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, reasoning=nvidia/nemotron-3-super-120b-a12b, deep=nvidia/Nemotron-3-Ultra-550b-a55b |
| T3 Text smoke test | **PASS** | perception: 200 in 2278 ms, case=exact, says_ok=False, reasoning_seen=True, finish=length \| fast_text: 200 in 866 ms, case=exact, says_ok=False, reasoning_seen=True, finish=length \| reasoning: 200 in 895 ms, case=exact, says_ok=False, reasoning_seen=True, finish=length \| deep: 200 in 675 ms, case=exact, says_ok=True, reasoning_seen=False, finish=length |
| T4 Thinking control | **PASS** | chosen=chat_template_kwargs \| perception/chat_template_kwargs: works (200, 637 ms) \| perception/system_flag: no (200, 732 ms) \| reasoning/chat_template_kwargs: no (200, 450 ms) \| reasoning/system_flag: no (200, 780 ms) |
| T5 Generate test assets | **PASS** | board.png (15762 B); speech.wav via say (3.7 s, modality_proof=True); count.mp4: ok |
| T6 Omni image-only | **PASS** | 1085 ms; expects 'red' and '7' |
| T7 Omni audio-only | **FAIL** | input_audio: HTTP 422 \| audio_url: HTTP 422 |
| T8 Omni COMBINED image+audio | **REJECTED** | HTTP 422 |
| T9 Omni video (optional) | **VERIFIED** | 862 ms |
| T10 JSON output | **PASS** | json_mode=json_schema \| json_schema: valid JSON |
| T11 Tool calling (reasoning) | **PASS** | tool_calls=[{'name': 'lookup_part', 'arguments': '{"part_number": "NE555"}'}] |
| T12 Ultra availability | **PASS** | 779 ms (thinking allowed) |

## Evidence (model replies, truncated to 300 chars)

**T1 Base URL probe:**

> https://api.tokenfactory.nebius.com/v1/ → 200 (28 models)

**T6 Omni image-only:**

> The LED is red and the label says 7.

**T9 Omni video (optional):**

> 1, 2, 3

**T10 JSON output:**

> { "colour": "red", "count": 3 }

**T12 Ultra availability:**

> OK


## Error bodies

**T7 Omni audio-only:**

```
input_audio: Error code: 422 - {'error': {'type': 'invalid_request_error', 'message': "body.messages.1.content.str: Input should be a valid string; body.messages.1.content.list[tagged-union[ChatCompletionContentPartTextParam,ChatCompletionContentPartImageParam,ChatCompletionContentPartVideoParam]].1: Input tag 'input_audio' found using 'type' does not match any of the expected tags: 'text', 'image_url', 'video_url'", 'param': None, 'code': None}, 'detail': "Invalid request. Please check the parameters and try again. Details: body.messages.1.content.str: Input should be a valid string; body.messages.1.content.list[tagged-union[ChatCompletionContentPartTextParam,ChatCompletionContentPartImageParam,ChatCompletionContentPartVideoParam]].1: Input tag 'input_audio' found using 'type' does not match any of the expected tags: 'text', 'image_url', 'video_url'"} | {"error":{"type":"invalid_request_error","message":"body.messages.1.content.str: Input should be a valid string; body.messages.1.content.list[tagged-union[ChatCompletionContentPartTextParam,ChatCompletionContentPartImageParam,ChatCompletionContentPartVideoParam]].1: Input tag 'input_audio' found using 'type' does not match any of …
```

**T8 Omni COMBINED image+audio:**

```
Error code: 422 - {'error': {'type': 'invalid_request_error', 'message': "body.messages.1.content.str: Input should be a valid string; body.messages.1.content.list[tagged-union[ChatCompletionContentPartTextParam,ChatCompletionContentPartImageParam,ChatCompletionContentPartVideoParam]].2: Input tag 'audio_url' found using 'type' does not match any of the expected tags: 'text', 'image_url', 'video_url'", 'param': None, 'code': None}, 'detail': "Invalid request. Please check the parameters and try again. Details: body.messages.1.content.str: Input should be a valid string; body.messages.1.content.list[tagged-union[ChatCompletionContentPartTextParam,ChatCompletionContentPartImageParam,ChatCompletionContentPartVideoParam]].2: Input tag 'audio_url' found using 'type' does not match any of the expected tags: 'text', 'image_url', 'video_url'"} | {"error":{"type":"invalid_request_error","message":"body.messages.1.content.str: Input should be a valid string; body.messages.1.content.list[tagged-union[ChatCompletionContentPartTextParam,ChatCompletionContentPartImageParam,ChatCompletionContentPartVideoParam]].2: Input tag 'audio_url' found using 'type' does not match any of the expected tags: …
```


## Token usage of this run

| Model | Prompt tokens | Completion tokens | Est. cost (USD) |
|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 22 | 16 | 0.0000 |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | 44 | 34 | 0.0001 |
| `nvidia/Nemotron-3.5-Super-VL` | 1433 | 88 | 0.0005 |
| `nvidia/nemotron-3-super-120b-a12b` | 448 | 96 | 0.0002 |

Estimated total: $0.0009

## All model IDs returned by /models (28)

- `MiniMaxAI/MiniMax-M3`
- `NousResearch/Hermes-4-405B`
- `Qwen/Qwen3-235B-A22B-Instruct-2507`
- `Qwen/Qwen3-30B-A3B-Instruct-2507`
- `Qwen/Qwen3-Embedding-8B`
- `Qwen/Qwen3.5-397B-A17B`
- `Qwen/Qwen3.8-27B`
- `deepseek-ai/DeepSeek-V4-Flash-0731`
- `deepseek-ai/DeepSeek-V4-Pro`
- `deepseek-ai/DeepSeek-V4-Pro-0813`
- `deepseek-ai/DeepSeek-V4.1-Flash`
- `google/gemma-3-27b-it`
- `meta-models/muse-spark-open`
- `moonshotai/Kimi-K2.6`
- `moonshotai/Kimi-K2.7-Code`
- `moonshotai/Kimi-K3`
- `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
- `nvidia/Nemotron-3-Ultra-550b-a55b`
- `nvidia/Nemotron-3.5-Super-VL`
- `nvidia/Nemotron-3_5-Lightning`
- `nvidia/nemotron-3-super-120b-a12b`
- `openai/gpt-oss-120b`
- `openbmb/MiniCPM-V-4_5`
- `reflection/beam`
- `zai-org/GLM-5.1`
- `zai-org/GLM-5.2`
- `zai-org/GLM-5.3`
- `zai-org/GLM-5.3-Flash`
