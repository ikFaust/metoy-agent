from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Document:
    id: str
    category: str
    title: str
    content: str
    tags: list[str]
    source: str
    level: str = ""
    path: str = ""


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    latin = re.findall(r"[a-z0-9]+", text)
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    phrases = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
    return latin + chinese + phrases


class LocalRetriever:
    def __init__(self, documents: list[Document]):
        self.documents = documents
        self.doc_tokens = [_tokenize(self._doc_text(doc)) for doc in documents]
        self.doc_freq: dict[str, int] = defaultdict(int)
        for tokens in self.doc_tokens:
            for token in set(tokens):
                self.doc_freq[token] += 1
        self.avg_len = sum(len(tokens) for tokens in self.doc_tokens) / max(len(self.doc_tokens), 1)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "LocalRetriever":
        docs = []
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                docs.append(
                    Document(
                        id=row["id"],
                        category=row["category"],
                        title=row["title"],
                        content=row["content"],
                        tags=row.get("tags", []),
                        source=row.get("source", "seed"),
                        level=row.get("level", ""),
                        path=row.get("path", ""),
                    )
                )
        return cls(docs)

    def search(self, query: str, top_k: int = 8, categories: set[str] | None = None) -> list[tuple[Document, float]]:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = []
        for doc, tokens in zip(self.documents, self.doc_tokens):
            if categories and doc.category not in categories:
                continue
            score = self._bm25(query_tokens, tokens)
            tag_bonus = sum(0.4 for tag in doc.tags if tag and tag in query)
            if score + tag_bonus > 0:
                scores.append((doc, score + tag_bonus))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:top_k]

    def _bm25(self, query_tokens: list[str], doc_tokens: list[str]) -> float:
        counts = Counter(doc_tokens)
        score = 0.0
        total_docs = max(len(self.documents), 1)
        k1 = 1.5
        b = 0.75
        for token in query_tokens:
            if token not in counts:
                continue
            df = self.doc_freq.get(token, 0)
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)
            tf = counts[token]
            denom = tf + k1 * (1 - b + b * len(doc_tokens) / max(self.avg_len, 1))
            score += idf * (tf * (k1 + 1) / denom)
        return score

    @staticmethod
    def _doc_text(doc: Document) -> str:
        return f"{doc.title} {' '.join(doc.tags)} {doc.content}"
