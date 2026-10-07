"""Lightweight tracing for agent runs (POC placeholder for OpenTelemetry).

Every pipeline run is a *trace*; each agent step and each LLM call is a nested
*span* with duration and attributes (agent, model, tokens, ok/error). Spans are
always written to ``runtime/traces.jsonl`` and shown in the app's
Audit & observability tab.

Production: set ``OTEL_EXPORTER_OTLP_ENDPOINT`` (and install
``opentelemetry-sdk opentelemetry-exporter-otlp``). The same spans are then
exported over OTLP to any backend: Langfuse, Jaeger, AWS X-Ray (ADOT
collector) or Azure Monitor / Application Insights. The call sites don't change.
"""
from __future__ import annotations

import contextvars
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from shared.audit import RUNTIME_DIR

TRACE_FILE = RUNTIME_DIR / "traces.jsonl"
_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar("span", default=None)

_otel_tracer = None
if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    try:  # optional: real OpenTelemetry export when configured and installed
        from opentelemetry import trace as _ot
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        _provider = TracerProvider(resource=Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "agentic-poc")}))
        _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        _ot.set_tracer_provider(_provider)
        _otel_tracer = _ot.get_tracer("agentic-poc")
    except ImportError:
        _otel_tracer = None


def _write(rec: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    with TRACE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
    """Open a span; nests under the current span, or starts a new trace if none is open.
    Callers may add attributes to the yielded dict (e.g. token counts)."""
    parent = _current.get()
    rec: dict[str, Any] = {
        "trace_id": parent["trace_id"] if parent else uuid.uuid4().hex[:16],
        "span_id": uuid.uuid4().hex[:8],
        "parent_id": parent["span_id"] if parent else None,
        "name": name,
        "start": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "attrs": dict(attrs),
        "status": "ok",
    }
    token = _current.set(rec)
    t0 = time.perf_counter()
    otel_cm = _otel_tracer.start_as_current_span(name) if _otel_tracer else None
    otel_span = otel_cm.__enter__() if otel_cm else None
    try:
        yield rec["attrs"]
    except Exception as exc:
        rec["status"] = f"error: {type(exc).__name__}"
        raise
    finally:
        rec["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        _current.reset(token)
        _write(rec)
        if otel_span is not None:
            for k, v in rec["attrs"].items():
                otel_span.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
            otel_cm.__exit__(None, None, None)


def current_trace_id() -> str | None:
    cur = _current.get()
    return cur["trace_id"] if cur else None


def load_traces(limit: int = 2000) -> list[dict[str, Any]]:
    if not TRACE_FILE.exists():
        return []
    lines = TRACE_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(l) for l in lines if l.strip()]
