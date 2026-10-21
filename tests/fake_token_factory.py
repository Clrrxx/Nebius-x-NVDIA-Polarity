"""A tiny fake of the Token Factory OpenAI-compatible API, used only by tests (never by the app).

It deliberately exercises the verifier's fallback paths:
- the Omni ID is listed in mixed case but only accepted lowercased (case policy → ``lowercase``);
- ``input_audio`` parts are rejected with 400, ``audio_url`` parts accepted (variant fallback);
- ``response_format=json_schema`` is rejected with 400, ``json_object`` accepted;
- replies include ``reasoning_content`` unless thinking is disabled via ``chat_template_kwargs``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

OMNI = "nvidia/Nemotron-3-Nano-Omni-30B-A3B"
NANO = "nvidia/nvidia-nemotron-3-nano-30b-a3b"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
ULTRA = "nvidia/nemotron-3-ultra-253b"
OTHER = "meta/llama-3.3-70b-instruct"
# Router-test models: FLAKY answers 429 on its first call, BADJSON returns prose until asked to repair,
# DOWN always answers 503. They are not listed by /models (tests configure them directly).
FLAKY = "test/flaky"
BADJSON = "test/badjson"
DOWN = "test/down"
LISTED = [OMNI, NANO, SUPER, ULTRA, OTHER]
ACCEPTED = {OMNI.lower(), NANO, SUPER, ULTRA, OTHER, FLAKY, BADJSON, DOWN}


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": "invalid_request_error"}})


def _completion(model: str, content: str, reasoning: str | None = None,
                tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    if tool_calls:
        message["tool_calls"] = tool_calls
        message["content"] = None
    return {
        "id": "chatcmpl-fake", "object": "chat.completion", "created": 0, "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def create_app() -> FastAPI:
    app = FastAPI()
    app.state.calls = {}

    @app.get("/v1/models")
    def models() -> dict[str, Any]:
        return {"object": "list", "data": [{"id": m, "object": "model", "created": 0, "owned_by": "test"} for m in LISTED]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Any:
        body = await request.json()
        model = body.get("model")
        if model not in ACCEPTED:
            return _error(404, f"The model `{model}` does not exist.")
        app.state.calls[model] = app.state.calls.get(model, 0) + 1
        if model == DOWN:
            return _error(503, "service unavailable")
        if model == FLAKY and app.state.calls[model] == 1:
            return _error(429, "rate limited")
        thinking_off = (body.get("chat_template_kwargs") or {}).get("enable_thinking") is False
        messages = body.get("messages", [])
        kinds: set[str] = set()
        text = ""
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                text += content + "\n"
            elif isinstance(content, list):
                for part in content:
                    kinds.add(part.get("type"))
                    if part.get("type") == "text":
                        text += part.get("text", "") + "\n"
        reasoning = None if thinking_off or "/no_think" in text else "Let me think about this..."
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        if tool_msgs and not body.get("tools"):
            # Second leg of a native tool call: summarise ONLY the tool results (plus one invented URL that the
            # client must drop, to prove it never cites sources Tavily did not return).
            found = json.loads(tool_msgs[0].get("content") or "[]")
            urls = [r.get("url") for r in found if r.get("url")]
            return _completion(model, json.dumps({"summary": "NE555 timer: pin 1 GND, pin 8 VCC.",
                                                  "pinout": [{"pin": "1", "name": "GND"}, {"pin": "8", "name": "VCC"}],
                                                  "sources": urls + ["https://invented.example/fake"]}), reasoning)
        if model in (FLAKY, BADJSON):
            if model == BADJSON and "Return ONLY the corrected JSON" not in text:
                return _completion(model, "Sure! Here is my answer: it looks fine.", reasoning)
            return _completion(model, '<think>checking</think>```json\n{"text": "ok"}\n```', reasoning)
        if "input_audio" in kinds:
            return _error(400, "Unsupported content part type: input_audio")
        if body.get("tools"):
            return _completion(model, "", reasoning, tool_calls=[{
                "id": "call_1", "type": "function",
                "function": {"name": "lookup_part", "arguments": json.dumps({"part_number": "NE555"})}}])
        rf = (body.get("response_format") or {}).get("type")
        if rf == "json_schema":
            return _error(400, "response_format json_schema is not supported")
        if rf == "json_object" or "Output only JSON" in text:
            return _completion(model, json.dumps({"colour": "red", "count": 3}), reasoning)
        if "video_url" in kinds:
            return _completion(model, "The digits are 1, 2 and 3.", reasoning)
        answers = []
        if "image_url" in kinds:
            answers.append("The LED is red and the label says TEST BOARD 7.")
        if "audio_url" in kinds:
            answers.append("The secret word is banana.")
        if answers:
            return _completion(model, " ".join(answers), reasoning)
        if "Reply with exactly: OK" in text:
            return _completion(model, "OK", reasoning)
        return _completion(model, "Hello.", reasoning)

    return app
