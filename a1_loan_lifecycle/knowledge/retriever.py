"""Lightweight RAG over the credit policy.

Prototype uses TF-IDF; production swaps in Azure AI Search (hybrid vector +
keyword) over the bank's real policy corpus. The interface stays the same.
"""
from __future__ import annotations

import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

POLICY_PATH = Path(__file__).with_name("credit_policy.md")


class PolicyRetriever:
    def __init__(self, path: Path = POLICY_PATH):
        text = path.read_text(encoding="utf-8")
        self.clauses: dict[str, dict[str, str]] = {}
        for block in re.split(r"\n(?=## )", text):
            m = re.match(r"## (CP-[\d.]+) (.+?)\n(.+)", block.strip(), re.S)
            if m:
                cid, title, body = m.groups()
                self.clauses[cid] = {"id": cid, "title": title.strip(), "text": body.strip()}
        self._ids = list(self.clauses)
        corpus = [f"{c['title']} {c['text']}" for c in self.clauses.values()]
        self._vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self._matrix = self._vec.fit_transform(corpus)

    def get(self, clause_id: str) -> dict[str, str]:
        return self.clauses[clause_id]

    def search(self, query: str, k: int = 3) -> list[dict[str, str | float]]:
        sims = cosine_similarity(self._vec.transform([query]), self._matrix)[0]
        ranked = sims.argsort()[::-1][:k]
        return [{**self.clauses[self._ids[i]], "score": round(float(sims[i]), 3)} for i in ranked if sims[i] > 0]
