"""Provider-agnostic LLM client.

* ``azure`` mode calls Azure OpenAI; ``openai`` mode calls the OpenAI API (both chat completions, JSON mode).
* ``mock`` mode returns a deterministic fallback supplied by the calling agent,
  so demos run offline and are reproducible.
* ``auto`` (default) uses Azure if configured, else OpenAI if OPENAI_API_KEY is set, else mock.

Every call is recorded in ``LLMClient.telemetry`` (agent, mode, latency, tokens)
for the observability panel in the apps.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[TAX_ID]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\+?\d{1,3}[ -]?)?\d{3}[ -]?\d{3}[ -]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{12,19}\b"), "[ACCOUNT_NO]"),
]

INJECTION_MARKERS = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard the above",
    "you are now",
    "system prompt",
    "approve this loan regardless",
]


def mask_pii(text: str) -> str:
    """Mask obvious PII before text leaves the trust boundary."""
    for pattern, token in PII_PATTERNS:
        text = pattern.sub(token, text)
    return text


def detect_injection(text: str) -> list[str]:
    """Return injection markers found in untrusted document text."""
    low = text.lower()
    return [m for m in INJECTION_MARKERS if m in low]


@dataclass
class LLMCall:
    agent: str
    mode: str
    model: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    ok: bool
    note: str = ""


@dataclass
class LLMClient:
    mode: str = field(default_factory=lambda: os.getenv("LLM_MODE", "auto").lower())
    telemetry: list[LLMCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
        has_azure = bool(self.endpoint and self.api_key and "<" not in self.endpoint)
        has_openai = bool(os.getenv("OPENAI_API_KEY"))
        if self.mode == "auto":
            self.mode = "azure" if has_azure else "openai" if has_openai else "mock"
        if (self.mode == "azure" and not has_azure) or (self.mode == "openai" and not has_openai):
            self.mode = "mock"
        self._client = None
        if self.mode == "azure":
            from openai import AzureOpenAI

            self._client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
            )
        elif self.mode == "openai":
            from openai import OpenAI

            self.deployment = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            self._client = OpenAI()  # reads OPENAI_API_KEY from the environment

    @property
    def model_name(self) -> str:
        return f"{self.mode}:{self.deployment}" if self._client else "mock-deterministic-v1"

    def complete_json(
        self,
        agent: str,
        system: str,
        user: str,
        fallback: Callable[[], dict[str, Any]],
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Ask the model for a JSON object. Falls back to ``fallback()`` in mock
        mode or on any provider error (the failure is recorded, never hidden)."""
        start = time.perf_counter()
        user = mask_pii(user)
        if self._client is None:
            result = fallback()
            self._record(agent, start, len(system + user) // 4, len(json.dumps(result)) // 4, True)
            return result
        try:
            resp = self._client.chat.completions.create(
                model=self.deployment,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system + "\nRespond with a single JSON object."},
                    {"role": "user", "content": user},
                ],
            )
            result = json.loads(resp.choices[0].message.content or "{}")
            usage = resp.usage
            self._record(agent, start, usage.prompt_tokens, usage.completion_tokens, True)
            return result
        except Exception as exc:  # provider/network/parse failure -> safe fallback
            result = fallback()
            self._record(agent, start, 0, 0, False, f"fallback: {type(exc).__name__}: {exc}"[:200])
            return result

    def _record(self, agent: str, start: float, pt: int, ct: int, ok: bool, note: str = "") -> None:
        self.telemetry.append(
            LLMCall(
                agent=agent,
                mode=self.mode,
                model=self.model_name,
                latency_ms=int((time.perf_counter() - start) * 1000),
                prompt_tokens=pt,
                completion_tokens=ct,
                ok=ok,
                note=note,
            )
        )
