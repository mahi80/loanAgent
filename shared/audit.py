"""Append-only, hash-chained JSONL audit log.

Each record carries the SHA-256 of the previous record, so any after-the-fact
edit breaks the chain and is detectable with ``verify_chain``.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_DIR = Path(__file__).resolve().parent.parent / "runtime"


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def inputs_hash(obj: Any) -> str:
    return _hash(obj)[:16]


class AuditLog:
    def __init__(self, name: str):
        RUNTIME_DIR.mkdir(exist_ok=True)
        self.path = RUNTIME_DIR / f"{name}_audit.jsonl"
        self.path.touch(exist_ok=True)

    def _last_hash(self) -> str:
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        return json.loads(lines[-1])["record_hash"] if lines else "GENESIS"

    def record(
        self,
        case_id: str,
        actor: str,
        action: str,
        payload: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "case_id": case_id,
            "actor": actor,
            "action": action,
            "model": model,
            "payload": payload or {},
            "prev_hash": self._last_hash(),
        }
        rec["record_hash"] = _hash(rec)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        return rec

    def entries(self, case_id: str | None = None) -> list[dict[str, Any]]:
        out = [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [e for e in out if case_id is None or e["case_id"] == case_id]

    def verify_chain(self) -> bool:
        prev = "GENESIS"
        for e in self.entries():
            body = {k: v for k, v in e.items() if k != "record_hash"}
            if e["prev_hash"] != prev or _hash(body) != e["record_hash"]:
                return False
            prev = e["record_hash"]
        return True
