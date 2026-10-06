"""Hybrid RAG retriever over the credit policy.

Prototype: word TF-IDF + character n-gram TF-IDF (robust to abbreviations,
typos and partial words) with banking-term query expansion. Production swaps
in Azure AI Search (hybrid vector + keyword + semantic ranker) over the bank's
real policy corpus; the interface stays the same.
"""
from __future__ import annotations

import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

POLICY_PATH = Path(__file__).with_name("credit_policy.md")

# domain abbreviations / colloquial terms -> policy vocabulary
SYNONYMS = {
    r"\bltv\b": "loan to value collateral valuation",
    r"\bdscr\b": "debt service coverage ratio",
    r"\bdebt service\b": "debt service coverage",
    r"\bleverage\b": "total debt ebitda leverage",
    r"\bpep\b|politic|minister|government official": "politically exposed person pep enhanced due diligence",
    r"\bkyc\b|\baml\b": "sanctions politically exposed beneficial owner due diligence",
    r"sanction|ofac": "sanctions decline",
    r"\bubo\b|beneficial|owner": "beneficial owner declaration",
    r"who approves|approv|authority|sign off|sign-off|committee|million": "approval authority matrix credit committee board",
    r"disburs|release funds|drawdown": "conditions precedent disbursement",
    r"\bcp\b|condition": "conditions precedent",
    r"covenant|early warning|\bews\b|monitor": "monitoring covenants early warning signal",
    r"years? old|vintage|new company|start-?up|track record|history": "vintage operating history years",
    r"audit|financial statements|accounts": "audited financial statements",
    r"valuation|valuer|appraisal of collateral": "collateral valuation empanelled valuer",
    r"bounce|overdraft|cash.?flow stress|conduct": "account conduct bounces overdraft",
    r"concentration|single customer|top customer": "customer concentration",
    r"infra|toll|power|real estate|watchlist|sector": "sector watchlist infrastructure stress test",
    r"news|media|fraud|corruption|bribery": "adverse media compliance",
}


def expand(query: str) -> str:
    q = query.lower()
    extra = [v for pat, v in SYNONYMS.items() if re.search(pat, q)]
    return " ".join([q, *extra])


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
        corpus = [f"{c['title']} {c['title']} {c['text']}" for c in self.clauses.values()]  # title weighted x2
        self._word = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True).fit(corpus)
        self._char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True).fit(corpus)
        self._wm, self._cm = self._word.transform(corpus), self._char.transform(corpus)

    def get(self, clause_id: str) -> dict[str, str]:
        return self.clauses[clause_id]

    def search(self, query: str, k: int = 3, min_score: float = 0.08) -> list[dict[str, str | float]]:
        q = expand(query)
        ws = cosine_similarity(self._word.transform([q]), self._wm)[0]
        cs = cosine_similarity(self._char.transform([q]), self._cm)[0]
        score = 0.6 * ws + 0.4 * cs
        ranked = score.argsort()[::-1][:k]
        return [{**self.clauses[self._ids[i]], "score": round(float(score[i]), 3)} for i in ranked if score[i] >= min_score]
