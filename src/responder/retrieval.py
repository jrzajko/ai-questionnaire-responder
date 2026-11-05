"""Policy pack -> labelled sections -> SQLite FTS5 index with BM25 ranking."""
from __future__ import annotations

import pathlib
import re
import sqlite3
import threading

STOPWORDS = set("""a an and are as at be by can do does for from has have how i if in into is it its of on
or our please provide the their there this to us we what when where which who will with you your yours
any all describe detail details""".split())


def parse_doc(path: pathlib.Path) -> list[dict]:
    """Split one markdown policy into sections on '## ID Heading' lines, keeping front-matter metadata."""
    text = path.read_text(encoding="utf-8")
    meta = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        text = text[m.end():]
    chunks = []
    for section in re.split(r"\n(?=## )", text):
        head = re.match(r"## ([A-Z]+-\d+) (.+)", section)
        if head:
            chunks.append({"section_id": head.group(1), "heading": head.group(2).strip(),
                           "doc_id": meta.get("doc_id", ""), "doc_title": meta.get("title", path.stem),
                           "version": meta.get("version", ""), "text": section[head.end():].strip()})
    return chunks


def to_fts_query(text: str) -> str:
    terms = [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1]
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))   # quoted terms are safe from FTS syntax


def format_hits(hits: list[dict]) -> str:
    return "\n\n".join(f"[{h['section_id']}] {h['doc_title']}: {h['heading']} (score {h['score']:.2f})\n{h['text']}"
                       for h in hits)


class PolicyIndex:
    """In-memory FTS5 index over the policy pack. Thread-safe for the parallel batch run."""

    def __init__(self, policy_dir: str | pathlib.Path):
        self.chunks = [c for p in sorted(pathlib.Path(policy_dir).glob("*.md")) for c in parse_doc(p)]
        if not self.chunks:
            raise FileNotFoundError(f"No policy sections found in {policy_dir}")
        self.versions = {c["section_id"]: c["version"] for c in self.chunks}
        self.titles = {c["section_id"]: c["doc_title"] for c in self.chunks}
        self.by_id = {c["section_id"]: c for c in self.chunks}
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""CREATE VIRTUAL TABLE passages USING fts5(
            section_id UNINDEXED, doc_id UNINDEXED, doc_title UNINDEXED, version UNINDEXED,
            heading, text, tokenize = 'porter unicode61')""")
        self.conn.executemany("INSERT INTO passages VALUES (:section_id, :doc_id, :doc_title, :version, :heading, :text)",
                              self.chunks)

    def __len__(self) -> int:
        return len(self.chunks)

    def search(self, query: str, k: int = 6) -> list[dict]:
        fts = to_fts_query(query)
        if not fts:
            return []
        with self._lock:
            rows = self.conn.execute("""
                SELECT section_id, doc_title, heading, text, -bm25(passages, 0, 0, 0, 0, 2.0, 1.0) AS score
                FROM passages WHERE passages MATCH ? ORDER BY score DESC LIMIT ?""", (fts, k)).fetchall()
        return [dict(r) for r in rows]
