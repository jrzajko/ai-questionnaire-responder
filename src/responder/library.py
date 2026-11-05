"""The answer library: human-approved answers, reused when Jev says a new question asks the same thing."""
from __future__ import annotations

import datetime
import json
import sqlite3
import threading

from .retrieval import to_fts_query


class AnswerLibrary:
    def __init__(self, path: str = "answer_library.db"):
        self.path = path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY, question TEXT, answer TEXT, sources TEXT, category TEXT,
                policy_versions TEXT, decision TEXT, reviewer TEXT, approved_at TEXT, run_id TEXT,
                times_reused INTEGER DEFAULT 0);
            CREATE VIRTUAL TABLE IF NOT EXISTS answers_fts USING fts5(question, tokenize = 'porter unicode61');""")

    def __len__(self) -> int:
        with self._lock:
            return self.conn.execute("SELECT count(*) FROM answers").fetchone()[0]

    def candidates(self, question: str, k: int = 3) -> list[dict]:
        fts = to_fts_query(question)
        if not fts:
            return []
        with self._lock:
            return [dict(r) for r in self.conn.execute("""
                SELECT a.*, -bm25(answers_fts) AS score FROM answers_fts JOIN answers a ON a.id = answers_fts.rowid
                WHERE answers_fts MATCH ? ORDER BY score DESC LIMIT ?""", (fts, k)).fetchall()]

    def lookup(self, question: str, versions: dict, same_prob, threshold: float) -> dict:
        """Best approved answer for `question`, skipping any whose policy sections changed version.

        `same_prob(new_question, approved_question)` returns Jev's probability that both ask the same thing."""
        best, checked = None, []
        for row in self.candidates(question):
            stored = json.loads(row["policy_versions"] or "{}")
            stale = [s for s, v in stored.items() if versions.get(s) != v]
            if stale:
                checked.append({"id": row["id"], "stale": stale})
                continue
            p = round(same_prob(question, row["question"]), 3)
            checked.append({"id": row["id"], "p_same": p})
            if p >= threshold and (best is None or p > best["p_same"]):
                best = {**row, "p_same": p}
        return {"match": best, "checked": checked}

    def add(self, question, answer, sources, category, decision, reviewer, versions: dict, run_id="") -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO answers (question, answer, sources, category, policy_versions, decision, reviewer,
                   approved_at, run_id) VALUES (?,?,?,?,?,?,?,?,?)""",
                (question, answer, json.dumps(sources), category, json.dumps({s: versions.get(s) for s in sources}),
                 decision, reviewer, datetime.datetime.now().isoformat(timespec="seconds"), run_id))
            self.conn.execute("INSERT INTO answers_fts (rowid, question) VALUES (?, ?)", (cur.lastrowid, question))
            self.conn.commit()
            return cur.lastrowid

    def bump(self, entry_id: int):
        with self._lock:
            self.conn.execute("UPDATE answers SET times_reused = times_reused + 1 WHERE id = ?", (entry_id,))
            self.conn.commit()

    def all(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM answers ORDER BY id")]
