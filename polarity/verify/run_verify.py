"""Phase 0: Nebius Token Factory infrastructure verification (BUILD_PROMPT.md Section 8).

Proves the platform works, discovers exact model IDs and records exactly what the API accepts.
Everything later reads ``data/capabilities.json``.

Facts vs assumptions (Section 8.1), kept next to the code that depends on them:
- CONFIRMED: Token Factory is OpenAI-compatible.
- CONFIRMED: Nebius's Nemotron page lists Nemotron 3 Nano 30B, Nano Omni, Super 120B and Ultra.
- CONFIRMED: Nemotron 3 Super is text-in/text-out.
- CONFIRMED: Nemotron 3 Nano Omni accepts text, image, video and audio, and outputs text.
- REPORTED, NOT VERIFIED: Nano Omni video input is MP4 up to ~2 minutes (T9 tests it; optional).
- Two documented base URLs have been seen (us-central1 host, older tokenfactory host); T1 probes both
  plus the legacy AI Studio host unless NEBIUS_BASE_URL is set.
- TEAM-REPORTED, UNVERIFIED: model IDs must be lowercase. We do NOT blindly lowercase: exact first,
  lowercase fallback on "model not found", recorded per model (see polarity/llm/resolver.py).

This probe uses the raw OpenAI-compatible client instead of ModelRouter because the router is configured
from the capabilities this probe produces. Every probe call's tokens are totalled and reported.

Exit codes: 0 = base URL + perception image test passed; 1 = other failure; 2 = no perception model;
3 = API unreachable or key rejected; 4 = no API key.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from polarity import paths

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NO_PERCEPTION = 2
EXIT_UNREACHABLE = 3
EXIT_NO_KEY = 4

REQUIRED_MODULES: tuple[tuple[str, str], ...] = (
    ("openai", "openai"),
    ("dotenv", "python-dotenv"),
    ("PIL", "pillow"),
    ("numpy", "numpy"),
    ("rich", "rich"),
)
EVIDENCE_CHARS = 300


@dataclass
class TestResult:
    key: str
    name: str
    status: str = "SKIPPED"  # PASS | FAIL | SKIPPED | INFO | or a classification (T8/T9)
    details: str = ""
    evidence: str | None = None
    error: str | None = None


@dataclass
class CallOutcome:
    ok: bool
    model: str
    status_code: int | None = None
    text: str = ""
    raw_text: str = ""
    reasoning_seen: bool = False
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    case_used: str | None = None
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _truncate(text: str | None, n: int = EVIDENCE_CHARS) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _says_ok(text: str) -> bool:
    return bool(re.search(r"\bok\b", text.lower()))


def _has_red_and_7(text: str) -> bool:
    low = text.lower()
    return bool(re.search(r"\bred\b", low)) and bool(re.search(r"\b7\b|\bseven\b", low))


def _has_banana(text: str) -> bool:
    return "banana" in text.lower()


class Verifier:
    """Runs T0–T12, then writes ``data/capabilities.json`` and ``docs/PHASE0_REPORT.md``."""

    def __init__(self, args: argparse.Namespace, console: Any) -> None:
        self.args = args
        self.console = console
        self.results: dict[str, TestResult] = {}
        self.tokens: dict[str, list[int]] = {}
        self.case_used: dict[str, str] = {}
        self.base_url: str | None = None
        self.api_key: str = ""
        self.client: Any = None
        self.all_ids: list[str] = []
        self.roles: dict[str, str | None] = {"perception": None, "fast_text": None, "reasoning": None, "deep": None}
        self.role_latency: dict[str, int | None] = {}
        self.perception_fallback_vl = False
        self.resolution_notes: list[str] = []
        self.thinking_control = "none"
        self.thinking_details: dict[str, Any] = {}
        self.image_ok = False
        self.audio_variant: str | None = None
        self.audio_supported = False
        self.audio_asset: Any = None
        self.board_png: bytes | None = None
        self.video_path: Path | None = None
        self.combined = "UNPROVEN"
        self.video = "SKIPPED"
        self.json_mode = "prompt_only"
        self.tools_mode = "manual"
        self.deep_available = False
        self.started = datetime.now().astimezone()

    # ── helpers ──────────────────────────────────────────────────────────────────────────────

    def _set(self, key: str, name: str, status: str, details: str = "", evidence: str | None = None,
             error: str | None = None) -> TestResult:
        res = TestResult(key, name, status, details, _truncate(evidence) if evidence else None,
                         _truncate(error, 1200) if error else None)
        self.results[key] = res
        colour = {"PASS": "green", "VERIFIED": "green", "FAIL": "red", "REJECTED": "red"}.get(status, "yellow")
        self.console.print(f"[bold]{key}[/bold] {name}: [{colour}]{status}[/{colour}] {details}")
        return res

    def _thinking_kwargs(self, enabled: bool = False) -> dict[str, Any]:
        """Request kwargs/system-prefix for the chosen thinking control (applied to multimodal tests)."""
        if enabled:
            return {}
        if self.thinking_control == "chat_template_kwargs":
            return {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        return {}

    def _mt(self, base: int) -> int:
        """max_tokens for a probe: generous when thinking cannot be switched off (reasoning eats the budget)."""
        return base if self.thinking_control != "none" else max(base, 1500)

    def _system(self, text: str, thinking: bool = False) -> dict[str, str]:
        if not thinking and self.thinking_control == "system_flag":
            text = "/no_think\n" + text
        return {"role": "system", "content": text}

    def chat(self, model_id: str, messages: list[dict[str, Any]], max_tokens: int, temperature: float = 0.0,
             timeout: float = 60.0, **kwargs: Any) -> CallOutcome:
        """One chat completion with the exact-first/lowercase-fallback case policy."""
        import openai

        from polarity.llm.jsonio import strip_think
        from polarity.llm.resolver import call_with_case_policy, error_text

        def _do(model: str) -> Any:
            return self.client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens,
                                                       temperature=temperature, timeout=timeout, **kwargs)

        for attempt in range(2):  # one retry: a cold model or a slow network can time out once
            t0 = time.perf_counter()
            try:
                resp, case_used, sent = call_with_case_policy(_do, model_id, self.case_used.get(model_id))
                break
            except openai.APIStatusError as exc:
                return CallOutcome(ok=False, model=model_id, status_code=exc.status_code, error=error_text(exc),
                                   latency_ms=int((time.perf_counter() - t0) * 1000))
            except openai.APIConnectionError as exc:  # includes APITimeoutError
                if attempt == 0:
                    self.console.print(f"[dim]{model_id}: {type(exc).__name__}, retrying once[/dim]")
                    continue
                return CallOutcome(ok=False, model=model_id, error=f"{type(exc).__name__} (after one retry): {exc}",
                                   latency_ms=int((time.perf_counter() - t0) * 1000))
        latency = int((time.perf_counter() - t0) * 1000)
        self.case_used[model_id] = case_used
        choice = resp.choices[0] if resp.choices else None
        msg = choice.message if choice else None
        content = (msg.content if msg else None) or ""
        extra = (msg.model_extra if msg is not None else None) or {}
        reasoning = extra.get("reasoning_content") or extra.get("reasoning")
        usage = resp.usage
        p_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
        c_tok = int(getattr(usage, "completion_tokens", 0) or 0)
        totals = self.tokens.setdefault(sent, [0, 0])
        totals[0] += p_tok
        totals[1] += c_tok
        tool_calls = []
        for tc in (msg.tool_calls if msg and msg.tool_calls else []):
            fn = getattr(tc, "function", None)
            tool_calls.append({"name": getattr(fn, "name", None), "arguments": getattr(fn, "arguments", None)})
        return CallOutcome(
            ok=True, model=model_id, status_code=200, text=strip_think(content), raw_text=content,
            reasoning_seen=bool(reasoning) or "<think>" in content.lower() or "</think>" in content.lower(),
            latency_ms=latency, prompt_tokens=p_tok, completion_tokens=c_tok, case_used=case_used,
            finish_reason=getattr(choice, "finish_reason", None), tool_calls=tool_calls,
        )

    # ── T0–T2 ────────────────────────────────────────────────────────────────────────────────

    def t0_environment(self) -> bool:
        py = sys.version_info
        problems = []
        if py < (3, 11):
            problems.append(f"Python {py.major}.{py.minor} is too old; install Python 3.12 (3.11 also supported).")
        elif py >= (3, 13):
            problems.append(f"Python {py.major}.{py.minor} is not supported; use Python 3.12 (or 3.11).")
        try:
            import cv2  # noqa: F401
            cv2_note = "cv2 available (video test possible)"
        except ImportError:
            cv2_note = "cv2 missing (video test will be skipped)"
        from dotenv import dotenv_values

        env_path = paths.env_file()
        merged: dict[str, str] = {}
        for f in paths.env_files():  # .env, then .env.local overrides it
            merged.update({k: v for k, v in dotenv_values(f).items() if v is not None})
        for k, v in merged.items():
            os.environ.setdefault(k, v)  # real environment variables still win
        self.api_key = (os.environ.get("NEBIUS_API_KEY") or "").strip()
        from polarity.llm.client import mask_secret

        details = (f"Python {platform.python_version()} on {platform.system()} {platform.machine()}; "
                   f"packages OK; {cv2_note}; NEBIUS_API_KEY={mask_secret(self.api_key)}")
        if not self.api_key:
            self._set("T0", "Environment", "FAIL", details,
                      error=f"NEBIUS_API_KEY is not set. Copy .env.example to .env ({env_path}) and paste your "
                            "Token Factory API key, then re-run.")
            return False
        if problems:
            self._set("T0", "Environment", "FAIL", details, error=" ".join(problems))
            return True  # keep going: the API can still be probed, but flag it
        self._set("T0", "Environment", "PASS", details)
        return True

    def _list_models(self, url: str) -> tuple[list[str] | None, str]:
        """``(ids, note)`` for one candidate base URL; ``ids`` is None when it is not a working API."""
        import openai

        from polarity.llm.client import make_client
        from polarity.llm.resolver import error_text

        try:
            ids = sorted({m.id for m in make_client(url, self.api_key, timeout=15.0).models.list(timeout=15.0)})
        except openai.AuthenticationError as exc:
            return None, f"401 key rejected ({_truncate(error_text(exc), 120)})"
        except openai.APIStatusError as exc:
            return None, f"HTTP {exc.status_code} ({_truncate(error_text(exc), 120)})"
        except openai.APIConnectionError as exc:
            return None, type(exc).__name__
        except Exception as exc:  # noqa: BLE001 - e.g. a web page instead of the API
            return None, f"not an OpenAI-compatible API ({type(exc).__name__}); is this the console URL?"
        return (ids, f"200 ({len(ids)} models)") if ids else (None, "200 but empty model list")

    def t1_base_url(self) -> bool:
        """Configured URL only (spec); otherwise every known endpoint, keeping the one where most roles resolve
        (an endpoint can answer but lack the vision model, as us-central1 did for our account)."""
        from polarity.llm.client import KNOWN_BASE_URLS, make_client
        from polarity.llm.resolver import resolve_roles

        configured = (os.environ.get("NEBIUS_BASE_URL") or "").strip()
        tried: list[str] = []
        if configured:
            ids, note = self._list_models(configured)
            tried.append(f"{configured} → {note}")
            if ids:
                self.base_url, self.client, self.all_ids = configured, make_client(configured, self.api_key, timeout=60.0), ids
                self._set("T1", "Base URL probe", "PASS", f"Using {configured} (from NEBIUS_BASE_URL)", evidence=" ; ".join(tried))
                return True
            hint = ""
            for url in KNOWN_BASE_URLS:  # suggest a working endpoint, but respect the explicit setting
                alt, alt_note = self._list_models(url)
                tried.append(f"{url} → {alt_note}")
                if alt and not hint:
                    hint = f" Set NEBIUS_BASE_URL={url} (or leave it blank) and run verify again."
            self._set("T1", "Base URL probe", "FAIL", f"NEBIUS_BASE_URL={configured} is not a working API.{hint}",
                      error=" ; ".join(tried))
            return False
        best: tuple[tuple[int, int, int], str, list[str]] | None = None
        for url in KNOWN_BASE_URLS:
            ids, note = self._list_models(url)
            tried.append(f"{url} → {note}")
            if not ids:
                continue
            res = resolve_roles(ids)
            score = (int(res.ids["perception"] is not None), sum(v is not None for v in res.ids.values()), len(ids))
            if best is None or score > best[0]:
                best = (score, url, ids)
        if best is None:
            self._set("T1", "Base URL probe", "FAIL", "No base URL returned a model list.", error=" ; ".join(tried))
            return False
        _, url, ids = best
        self.base_url, self.client, self.all_ids = url, make_client(url, self.api_key, timeout=60.0), ids
        self._set("T1", "Base URL probe", "PASS", f"Using {url} (most roles resolvable)", evidence=" ; ".join(tried))
        return True

    def t2_discovery(self) -> None:
        from rich.table import Table

        from polarity.llm.resolver import resolve_roles

        table = Table(title=f"Models at {self.base_url} ({len(self.all_ids)})", show_lines=False)
        table.add_column("Model ID")
        for mid in self.all_ids:
            table.add_row(f"[bold cyan]{mid}[/bold cyan]" if "nemotron" in mid.lower() else mid)
        self.console.print(table)
        overrides = {role: os.environ.get(f"POLARITY_MODEL_{role.upper()}") for role in self.roles}
        res = resolve_roles(self.all_ids, overrides)
        self.roles = dict(res.ids)
        self.perception_fallback_vl = res.perception_fallback_vl
        self.resolution_notes = res.notes
        summary = ", ".join(f"{r}={v or '—'}" for r, v in self.roles.items())
        status = "PASS" if self.roles["perception"] else "FAIL"
        self._set("T2", "Model discovery", status, summary,
                  error=None if self.roles["perception"] else "No Nemotron Omni (or VL) model found for perception.")

    # ── T3–T4 ────────────────────────────────────────────────────────────────────────────────

    def t3_smoke(self) -> None:
        messages = [{"role": "system", "content": "Reply with exactly: OK"}, {"role": "user", "content": "ping"}]
        lines, failures = [], 0
        done: dict[str, CallOutcome] = {}
        for role, mid in self.roles.items():
            if not mid:
                lines.append(f"{role}: unresolved")
                continue
            # Thinking is left at the model's default here (T4 tests switching it off), so the budget must leave
            # room for the reasoning that precedes "OK"; 16 tokens ended every reply mid-thought (finish=length).
            out = done.get(mid) or self.chat(mid, messages, max_tokens=256, temperature=0.0, timeout=60.0)
            done[mid] = out
            if out.ok:
                self.role_latency[role] = out.latency_ms
                lines.append(f"{role}: 200 in {out.latency_ms} ms, case={out.case_used}, says_ok={_says_ok(out.text)}, "
                             f"reasoning_seen={out.reasoning_seen}, finish={out.finish_reason}")
            else:
                failures += 1
                lines.append(f"{role}: HTTP {out.status_code} {_truncate(out.error, 160)}")
        self.thinking_details["baseline"] = {m: {"latency_ms": o.latency_ms, "reasoning_seen": o.reasoning_seen,
                                                 "says_ok": _says_ok(o.text)} for m, o in done.items() if o.ok}
        self._set("T3", "Text smoke test", "PASS" if failures == 0 and done else "FAIL", " | ".join(lines))

    def t4_thinking(self) -> None:
        targets = [(r, self.roles[r]) for r in ("perception", "reasoning") if self.roles.get(r)]
        if not targets:
            self._set("T4", "Thinking control", "SKIPPED", "No perception/reasoning model resolved.")
            return
        works: dict[str, dict[str, bool]] = {"chat_template_kwargs": {}, "system_flag": {}}
        lines = []
        for role, mid in targets:
            a = self.chat(mid, [{"role": "system", "content": "Reply with exactly: OK"},
                                {"role": "user", "content": "ping"}], max_tokens=32,
                          extra_body={"chat_template_kwargs": {"enable_thinking": False}})
            b = self.chat(mid, [{"role": "system", "content": "/no_think\nReply with exactly: OK"},
                                {"role": "user", "content": "ping"}], max_tokens=32)
            for name, out in (("chat_template_kwargs", a), ("system_flag", b)):
                # Works = an answer with no reasoning. Not "says OK": Super 120B answers "ping" with "pong".
                ok = out.ok and bool(out.text.strip()) and not out.reasoning_seen
                works[name][role] = ok
                self.thinking_details.setdefault(name, {})[role] = {
                    "http": out.status_code, "latency_ms": out.latency_ms, "says_ok": _says_ok(out.text),
                    "reasoning_seen": out.reasoning_seen, "error": _truncate(out.error, 200) if out.error else None}
                lines.append(f"{role}/{name}: {'works' if ok else 'no'} ({out.status_code}, {out.latency_ms} ms)")
        roles = [r for r, _ in targets]
        if all(works["chat_template_kwargs"].get(r) for r in roles):
            self.thinking_control = "chat_template_kwargs"
        elif all(works["system_flag"].get(r) for r in roles):
            self.thinking_control = "system_flag"
        elif works["chat_template_kwargs"].get("perception"):
            self.thinking_control = "chat_template_kwargs"
        elif works["system_flag"].get("perception"):
            self.thinking_control = "system_flag"
        else:
            self.thinking_control = "none"
        self._set("T4", "Thinking control", "PASS" if self.thinking_control != "none" else "INFO",
                  f"chosen={self.thinking_control} | " + " | ".join(lines))

    # ── T5–T9 multimodal ─────────────────────────────────────────────────────────────────────

    def t5_assets(self) -> None:
        from polarity.verify import assets

        out_dir = paths.data_dir() / "verify_assets"
        board = assets.make_board_png(out_dir / "board.png")
        self.board_png = board.read_bytes()
        self.audio_asset = assets.make_speech_wav(out_dir / "speech.wav", record=self.args.record)
        video = None if self.args.skip_video else assets.make_count_mp4(out_dir / "count.mp4")
        self.video_path = video
        details = (f"board.png ({len(self.board_png)} B); speech.wav via {self.audio_asset.method} "
                   f"({self.audio_asset.seconds:.1f} s, modality_proof={self.audio_asset.modality_proof}); "
                   f"count.mp4: {'skipped' if self.args.skip_video else ('ok' if video else 'writer unavailable')}")
        self._set("T5", "Generate test assets", "PASS", details)

    def t6_image(self) -> None:
        from polarity.llm.payloads import image_part, text_part

        mid = self.roles["perception"]
        if not mid or not self.board_png:
            self._set("T6", "Omni image-only", "SKIPPED", "No perception model.")
            return
        prompt = "What colour is the LED, and what number is printed on the label? Answer in one short sentence."
        out = self.chat(mid, [self._system("You are a helpful assistant."),
                              {"role": "user", "content": [text_part(prompt), image_part(self.board_png, "image/png")]}],
                        max_tokens=self._mt(400), **self._thinking_kwargs())
        if not out.ok:
            self._set("T6", "Omni image-only", "FAIL", f"HTTP {out.status_code}", error=out.error)
            return
        self.image_ok = _has_red_and_7(out.text)
        self._set("T6", "Omni image-only", "PASS" if self.image_ok else "FAIL",
                  f"{out.latency_ms} ms; expects 'red' and '7'", evidence=out.text)

    def _audio_wav(self) -> bytes:
        return Path(self.audio_asset.path).read_bytes()

    def t7_audio(self) -> None:
        from polarity.llm.payloads import AUDIO_VARIANTS, audio_part, text_part

        mid = self.roles["perception"]
        if not mid or not self.audio_asset:
            self._set("T7", "Omni audio-only", "SKIPPED", "No perception model.")
            return
        wav = self._audio_wav()
        lines, evidence, errors = [], None, []
        for variant in AUDIO_VARIANTS:
            out = self.chat(mid, [self._system("You are a helpful assistant."),
                                  {"role": "user", "content": [text_part("What is the secret word spoken in the audio?"),
                                                               audio_part(wav, variant)]}],
                            max_tokens=self._mt(200), **self._thinking_kwargs())
            if not out.ok:
                lines.append(f"{variant}: HTTP {out.status_code}")
                errors.append(f"{variant}: {out.error}")
                continue
            evidence = out.text
            if not self.audio_asset.modality_proof:
                lines.append(f"{variant}: accepted (tone only, cannot prove understanding)")
                self.audio_variant = self.audio_variant or variant
                continue
            if _has_banana(out.text):
                self.audio_variant, self.audio_supported = variant, True
                lines.append(f"{variant}: works ({out.latency_ms} ms)")
                break
            lines.append(f"{variant}: 200 but 'banana' missing")
        if self.audio_supported:
            status = "PASS"
        elif not self.audio_asset.modality_proof and self.audio_variant:
            status = "INFO"
        else:
            status = "FAIL"
        self._set("T7", "Omni audio-only", status, " | ".join(lines), evidence=evidence,
                  error=" ; ".join(errors) if errors else None)

    def t8_combined(self) -> None:
        from polarity.llm.payloads import AUDIO_VARIANTS, audio_part, image_part, text_part

        mid = self.roles["perception"]
        if not mid or not self.audio_asset or not self.board_png:
            self.combined = "UNPROVEN"
            self._set("T8", "Omni COMBINED image+audio", "SKIPPED", "No perception model.")
            return
        variants = [self.audio_variant] if self.audio_variant else list(AUDIO_VARIANTS)
        prompt = "Answer three things: the LED colour, the number on the label, and the secret word in the audio."
        wav = self._audio_wav()
        last: CallOutcome | None = None
        for variant in variants:
            out = self.chat(mid, [self._system("You are a helpful assistant."),
                                  {"role": "user", "content": [text_part(prompt), image_part(self.board_png, "image/png"),
                                                               audio_part(wav, variant)]}],
                            max_tokens=self._mt(400), **self._thinking_kwargs())
            last = out
            if out.ok:
                if not self.audio_asset.modality_proof:
                    self.combined = "UNPROVEN"
                elif _has_banana(out.text) and _has_red_and_7(out.text):
                    self.combined = "VERIFIED"
                elif not _has_banana(out.text):
                    self.combined = "ACCEPTED_AUDIO_IGNORED"
                else:
                    self.combined = "ACCEPTED_IMAGE_IGNORED"
                self.audio_variant = self.audio_variant or variant
                self._set("T8", "Omni COMBINED image+audio", self.combined,
                          f"variant={variant}, {out.latency_ms} ms", evidence=out.text)
                return
        self.combined = "REJECTED"
        self._set("T8", "Omni COMBINED image+audio", "REJECTED",
                  f"HTTP {last.status_code if last else '—'}", error=last.error if last else None)

    def t9_video(self) -> None:
        from polarity.llm.payloads import text_part, video_part

        mid = self.roles["perception"]
        path = getattr(self, "video_path", None)
        if self.args.skip_video or not path or not mid:
            self.video = "SKIPPED"
            self._set("T9", "Omni video (optional)", "SKIPPED",
                      "--skip-video" if self.args.skip_video else "No MP4 or no perception model.")
            return
        out = self.chat(mid, [self._system("You are a helpful assistant."),
                              {"role": "user", "content": [text_part("Which digits appear in this video, in order? Answer briefly."),
                                                           video_part(Path(path).read_bytes())]}],
                        max_tokens=self._mt(200), timeout=90.0, **self._thinking_kwargs())
        if not out.ok:
            self.video = "REJECTED"
            self._set("T9", "Omni video (optional)", "REJECTED", f"HTTP {out.status_code}", error=out.error)
            return
        digits_ok = all(d in out.text for d in ("1", "2", "3"))
        self.video = "VERIFIED" if digits_ok else "ACCEPTED_UNVERIFIED"
        self._set("T9", "Omni video (optional)", self.video, f"{out.latency_ms} ms", evidence=out.text)

    # ── T10–T12 ──────────────────────────────────────────────────────────────────────────────

    def t10_json(self) -> None:
        from polarity.llm.jsonio import extract_json

        mid = self.roles["perception"]
        if not mid:
            self._set("T10", "JSON output", "SKIPPED", "No perception model.")
            return
        schema = {"type": "object", "properties": {"colour": {"type": "string"}, "count": {"type": "integer"}},
                  "required": ["colour", "count"], "additionalProperties": False}
        prompt = 'Return a JSON object with "colour" set to "red" and "count" set to 3. Output only JSON.'
        modes: list[tuple[str, dict[str, Any]]] = [
            ("json_schema", {"response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "probe", "strict": True, "schema": schema}}}),
            ("json_object", {"response_format": {"type": "json_object"}}),
            ("prompt_only", {}),
        ]
        lines = []
        for name, kwargs in modes:
            out = self.chat(mid, [self._system("You output only JSON."), {"role": "user", "content": prompt}],
                            max_tokens=self._mt(200), **kwargs, **self._thinking_kwargs())
            if not out.ok:
                lines.append(f"{name}: HTTP {out.status_code}")
                continue
            data = extract_json(out.text)
            if isinstance(data, dict) and "colour" in data and "count" in data:
                self.json_mode = name
                lines.append(f"{name}: valid JSON")
                self._set("T10", "JSON output", "PASS", f"json_mode={name} | " + " | ".join(lines), evidence=out.text)
                return
            lines.append(f"{name}: 200 but no valid JSON")
        self.json_mode = "prompt_only"
        self._set("T10", "JSON output", "FAIL", "No mode returned valid JSON; using prompt_only + repair. " + " | ".join(lines))

    def t11_tools(self) -> None:
        mid = self.roles["reasoning"]
        if not mid:
            self._set("T11", "Tool calling (reasoning)", "SKIPPED", "No reasoning model; TOOLS_MODE=manual.")
            return
        tools = [{"type": "function", "function": {
            "name": "lookup_part", "description": "Look up an electronic part's datasheet and pinout.",
            "parameters": {"type": "object", "properties": {"part_number": {"type": "string"}},
                           "required": ["part_number"]}}}]
        out = self.chat(mid, [self._system("You are a helpful lab assistant."),
                              {"role": "user", "content": "What are the pins of an NE555? Use the tool."}],
                        max_tokens=self._mt(300), tools=tools, tool_choice="auto", **self._thinking_kwargs())
        if out.ok and out.tool_calls:
            self.tools_mode = "native"
            self._set("T11", "Tool calling (reasoning)", "PASS", f"tool_calls={out.tool_calls}")
        elif out.ok:
            self.tools_mode = "manual"
            self._set("T11", "Tool calling (reasoning)", "INFO", "200 but no tool_calls → TOOLS_MODE=manual",
                      evidence=out.text)
        else:
            self.tools_mode = "manual"
            self._set("T11", "Tool calling (reasoning)", "INFO", f"HTTP {out.status_code} → TOOLS_MODE=manual",
                      error=out.error)

    def t12_ultra(self) -> None:
        mid = self.roles["deep"]
        if not mid:
            self.deep_available = False
            self._set("T12", "Ultra availability", "INFO", "No Nemotron Ultra listed → deep falls back to reasoning.")
            return
        out = self.chat(mid, [{"role": "system", "content": "Reply with exactly: OK"}, {"role": "user", "content": "ping"}],
                        max_tokens=256, timeout=120.0)
        self.deep_available = out.ok
        if out.ok:
            self.role_latency["deep"] = out.latency_ms
            self._set("T12", "Ultra availability", "PASS", f"{out.latency_ms} ms (thinking allowed)", evidence=out.text)
        else:
            self._set("T12", "Ultra availability", "FAIL", f"HTTP {out.status_code} → deep falls back to reasoning",
                      error=out.error)

    # ── outputs ──────────────────────────────────────────────────────────────────────────────

    def audio_mode_recommended(self) -> str:
        if self.combined == "VERIFIED":
            return "omni_combined"
        if self.audio_supported:
            return "omni_separate"
        return "browser_stt"

    def capabilities(self) -> dict[str, Any]:
        def model_entry(role: str) -> dict[str, Any]:
            mid = self.roles.get(role)
            entry: dict[str, Any] = {"id": mid, "case": self.case_used.get(mid, "exact") if mid else None,
                                     "latency_ms": self.role_latency.get(role)}
            if role == "deep":
                entry["available"] = bool(mid) and self.deep_available
            return entry

        return {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "base_url": self.base_url,
            "models": {r: model_entry(r) for r in ("perception", "fast_text", "reasoning", "deep")},
            "all_model_ids": self.all_ids,
            "perception_fallback_vl": self.perception_fallback_vl,
            "image_input": self.image_ok,
            "audio_input": {"supported": self.audio_supported, "variant": self.audio_variant},
            "combined_image_audio": self.combined,
            "video_input": self.video,
            "json_mode": self.json_mode,
            "tools_mode": self.tools_mode,
            "thinking_control": self.thinking_control,
            "audio_mode_recommended": self.audio_mode_recommended(),
            "verified": True,
            "audio_modality_proof": bool(self.audio_asset and self.audio_asset.modality_proof),
            "thinking_details": self.thinking_details,
            "notes": self.resolution_notes,
        }

    def token_summary(self) -> tuple[list[tuple[str, int, int, float | None]], float | None]:
        from polarity.llm.pricing import estimate_cost, load_pricing

        prices = load_pricing(paths.config_dir() / "pricing.yaml")
        rows, total, known = [], 0.0, True
        for mid, (p, c) in sorted(self.tokens.items()):
            cost = estimate_cost(mid, p, c, prices)
            if cost is None:
                known = False
            else:
                total += cost
            rows.append((mid, p, c, cost))
        return rows, (total if known and rows else None)

    def write_report(self, caps: dict[str, Any] | None) -> Path:
        from polarity.llm.client import mask_secret

        lines = [
            "# Phase 0 report: Nebius Token Factory verification",
            "",
            f"- **Run at:** {self.started.isoformat(sep=' ', timespec='minutes')}",
            f"- **Base URL:** `{self.base_url or 'none reachable'}`",
            f"- **Machine:** {platform.system()} {platform.release()} {platform.machine()} · Python {platform.python_version()}",
            f"- **API key:** {mask_secret(self.api_key)}",
            "",
            "## Resolved models",
            "",
            "| Role | Exact model ID | Case used | Latency (ms) |",
            "|---|---|---|---|",
        ]
        for role in ("perception", "fast_text", "reasoning", "deep"):
            mid = self.roles.get(role)
            lat = self.role_latency.get(role)
            lines.append(f"| `{role}` | {('`' + mid + '`') if mid else '—'} | "
                         f"{self.case_used.get(mid, '—') if mid else '—'} | {lat if lat is not None else '—'} |")
        if self.resolution_notes:
            lines += ["", *[f"> {n}" for n in self.resolution_notes]]
        if caps:
            lines += [
                "",
                "## Capabilities",
                "",
                f"- **OMNI COMBINED IMAGE+AUDIO:** `{caps['combined_image_audio']}`",
                f"- **Audio input:** supported={caps['audio_input']['supported']}, variant=`{caps['audio_input']['variant']}`"
                f" (audio asset method: {self.audio_asset.method if self.audio_asset else '—'})",
                f"- **Video input:** `{caps['video_input']}`",
                f"- **JSON mode:** `{caps['json_mode']}` · **Tools mode:** `{caps['tools_mode']}` · "
                f"**Thinking control:** `{caps['thinking_control']}`",
                f"- **Perception fallback to VL:** {caps['perception_fallback_vl']}",
                "",
                "## Recommended AUDIO_MODE",
                "",
                f"`{caps['audio_mode_recommended']}`: " + {
                    "omni_combined": "T8 proved Nano Omni understood the image AND the speech in one request, so a "
                                     "student's spoken question rides along with the Check call (one round trip).",
                    "omni_separate": "Nano Omni understood audio on its own (T7) but not reliably in the same request as "
                                     "an image (T8), so audio is transcribed in a separate call and the text goes into "
                                     "the image call.",
                    "browser_stt": "Audio understanding could not be proven via the API, so the browser's Web Speech API "
                                   "transcribes speech (Chrome/Edge), with a typed box as the fallback.",
                }[caps["audio_mode_recommended"]],
            ]
        lines += ["", "## Tests", "", "| Test | Status | Details |", "|---|---|---|"]
        for res in self.results.values():
            details = res.details.replace("|", "\\|")
            lines.append(f"| {res.key} {res.name} | **{res.status}** | {details} |")
        evid = [r for r in self.results.values() if r.evidence]
        if evid:
            lines += ["", "## Evidence (model replies, truncated to 300 chars)", ""]
            for r in evid:
                lines += [f"**{r.key} {r.name}:**", "", f"> {r.evidence}", ""]
        errs = [r for r in self.results.values() if r.error]
        if errs:
            lines += ["", "## Error bodies", ""]
            for r in errs:
                lines += [f"**{r.key} {r.name}:**", "", "```", r.error or "", "```", ""]
        rows, total = self.token_summary()
        lines += ["", "## Token usage of this run", "", "| Model | Prompt tokens | Completion tokens | Est. cost (USD) |",
                  "|---|---|---|---|"]
        for mid, p, c, cost in rows:
            lines.append(f"| `{mid}` | {p} | {c} | {f'{cost:.4f}' if cost is not None else 'n/a'} |")
        lines.append(f"\nEstimated total: {f'${total:.4f}' if total is not None else 'n/a (fill config/pricing.yaml)'}")
        if self.all_ids:
            lines += ["", f"## All model IDs returned by /models ({len(self.all_ids)})", ""]
            lines += [f"- `{m}`" for m in self.all_ids]
        lines.append("")
        out = paths.docs_dir() / "PHASE0_REPORT.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        return out

    def print_summary(self, caps: dict[str, Any] | None) -> None:
        from rich.table import Table

        table = Table(title="Phase 0 summary")
        table.add_column("Test")
        table.add_column("Status")
        table.add_column("Details", overflow="fold")
        for r in self.results.values():
            colour = {"PASS": "green", "VERIFIED": "green", "FAIL": "red", "REJECTED": "red"}.get(r.status, "yellow")
            table.add_row(f"{r.key} {r.name}", f"[{colour}]{r.status}[/{colour}]", _truncate(r.details, 220))
        self.console.print(table)
        rows, total = self.token_summary()
        p_sum = sum(r[1] for r in rows)
        c_sum = sum(r[2] for r in rows)
        self.console.print(f"Tokens used by this run: prompt={p_sum}, completion={c_sum}; estimated cost: "
                           f"{f'${total:.4f}' if total is not None else 'n/a (fill config/pricing.yaml)'}")
        r = self.roles
        # Exact final-line format required by BUILD_PROMPT.md 8.3 (printed raw, not through rich markup).
        print(f"MODEL IDS → perception={r['perception']} | reasoning={r['reasoning']} | deep={r['deep']} | "
              f"fast_text={r['fast_text']}")
        print(f"OMNI COMBINED IMAGE+AUDIO → {caps['combined_image_audio'] if caps else self.combined}")

    def run(self) -> int:
        self.console.rule("Phase 0: Nebius Token Factory verification")
        if not self.t0_environment():
            self.console.print("\n[bold red]No NEBIUS_API_KEY found.[/bold red] Copy .env.example to .env, paste your "
                               "Token Factory key, and run this again. Everything else can still be built and used "
                               "in mock mode (POLARITY_MOCK_MODELS=1).")
            return EXIT_NO_KEY
        if not self.t1_base_url():
            self.write_report(None)
            self.print_summary(None)
            return EXIT_UNREACHABLE
        self.t2_discovery()
        self.t3_smoke()
        self.t4_thinking()
        self.t5_assets()
        self.t6_image()
        self.t7_audio()
        self.t8_combined()
        self.t9_video()
        self.t10_json()
        self.t11_tools()
        self.t12_ultra()
        caps = self.capabilities()
        cap_path = paths.capabilities_file()
        cap_path.parent.mkdir(parents=True, exist_ok=True)
        cap_path.write_text(json.dumps(caps, indent=2), encoding="utf-8")
        report = self.write_report(caps)
        try:
            from polarity.docs_sync import update_readme_models

            update_readme_models(caps)
        except Exception as exc:  # noqa: BLE001 - README sync is best-effort and needs the full install
            self.console.print(f"(README model table not updated: {exc})")
        self.console.print(f"Wrote {cap_path} and {report}")
        self.print_summary(caps)
        if self.args.json:
            print(json.dumps(caps, indent=2))
        if not self.roles["perception"]:
            return EXIT_NO_PERCEPTION
        return EXIT_OK if self.image_ok else EXIT_FAILED


def _check_imports() -> list[str]:
    missing = []
    for module, package in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    return missing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 0: verify Nebius Token Factory + Nemotron capabilities.")
    parser.add_argument("--record", action="store_true", help="record the audio test phrase from your microphone")
    parser.add_argument("--skip-video", action="store_true", help="skip the optional video test (T9)")
    parser.add_argument("--json", action="store_true", help="also print capabilities.json to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point shared by ``python -m polarity verify`` and ``scripts/verify_token_factory.py``."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    missing = _check_imports()
    if missing:
        print("T0 Environment: FAIL. Missing packages: " + ", ".join(missing))
        print("Fix: run the setup script (scripts/setup_mac.sh or scripts\\setup_windows.bat), or "
              "pip install " + " ".join(missing))
        return EXIT_FAILED
    from rich.console import Console

    return Verifier(args, Console()).run()


if __name__ == "__main__":
    raise SystemExit(main())
