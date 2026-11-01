from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

from .analyzers.base import AnalyzerResult
from .models import Announcement

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  news_id TEXT PRIMARY KEY,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  published_at TEXT NOT NULL,
  doc_group TEXT NOT NULL,
  tags TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  pdf_path TEXT,
  text_status TEXT NOT NULL,
  is_revision INTEGER NOT NULL DEFAULT 0,
  revision_of TEXT
);

CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  family TEXT NOT NULL,
  type TEXT NOT NULL,
  code TEXT NOT NULL,
  news_id TEXT NOT NULL,
  effective_date TEXT,
  direction TEXT NOT NULL,
  materiality REAL NOT NULL,
  confidence REAL NOT NULL,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
  event_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  unit TEXT,
  currency TEXT,
  page INTEGER,
  quote TEXT NOT NULL,
  confidence REAL NOT NULL,
  PRIMARY KEY (event_id, key)
);

CREATE TABLE IF NOT EXISTS links (
  from_event TEXT NOT NULL,
  to_event TEXT NOT NULL,
  type TEXT NOT NULL,
  PRIMARY KEY (from_event, to_event, type)
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  report_date TEXT NOT NULL,
  window_from TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  counts TEXT NOT NULL,
  errors TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_code_date ON events(code, effective_date);
CREATE INDEX IF NOT EXISTS idx_events_family ON events(family);
CREATE INDEX IF NOT EXISTS idx_documents_date ON documents(published_at);
"""


class EventStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def upsert_announcement(self, ann: Announcement) -> None:
        self.conn.execute(
            """
            INSERT INTO documents
              (news_id, code, name, published_at, doc_group, tags, title, url,
               pdf_path, text_status, is_revision, revision_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(news_id) DO UPDATE SET
              code=excluded.code, name=excluded.name, published_at=excluded.published_at,
              doc_group=excluded.doc_group, tags=excluded.tags, title=excluded.title,
              url=excluded.url, pdf_path=excluded.pdf_path, text_status=excluded.text_status,
              is_revision=excluded.is_revision, revision_of=excluded.revision_of
            """,
            (
                ann.news_id,
                ann.primary_code,
                ann.stock_name,
                ann.published_at.isoformat(),
                ann.doc_group,
                json.dumps(ann.headline_tags, ensure_ascii=False),
                ann.title,
                ann.file_url,
                ann.pdf_path,
                ann.text_status,
                int(ann.is_revision),
                ann.revision_of,
            ),
        )

    def add_result(self, ann: Announcement, result: AnalyzerResult) -> list[str]:
        self.upsert_announcement(ann)
        families = {event.family for event in result.events} or {result.analyzer}
        self._clear_events(ann.news_id, families)
        seen: Counter[str] = Counter()
        event_ids: list[str] = []
        now = datetime.now().isoformat(timespec="seconds")
        for event in result.events:
            base = f"{event.news_id}:{event.family}:{event.type}"
            seen[base] += 1
            event_id = base if seen[base] == 1 else f"{base}#{seen[base]}"
            event_ids.append(event_id)
            self.conn.execute(
                """
                INSERT OR REPLACE INTO events
                  (event_id, family, type, code, news_id, effective_date, direction,
                   materiality, confidence, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event.family,
                    event.type,
                    event.code,
                    event.news_id,
                    event.effective_date.isoformat() if event.effective_date else None,
                    event.direction,
                    event.materiality,
                    event.confidence,
                    event.summary,
                    now,
                ),
            )
            self.conn.execute("DELETE FROM facts WHERE event_id = ?", (event_id,))
            for fact in event.facts:
                self.conn.execute(
                    """
                    INSERT INTO facts
                      (event_id, key, value, unit, currency, page, quote, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        fact.key,
                        fact.value,
                        fact.unit,
                        fact.currency,
                        fact.evidence.page,
                        fact.evidence.quote,
                        fact.confidence,
                    ),
                )
        self.conn.commit()
        return event_ids

    def _clear_events(self, news_id: str, families: set[str]) -> None:
        marks = ",".join("?" for _ in families)
        rows = self.conn.execute(
            f"SELECT event_id FROM events WHERE news_id = ? AND family IN ({marks})",
            (news_id, *families),
        ).fetchall()
        for row in rows:
            event_id = row["event_id"]
            self.conn.execute("DELETE FROM facts WHERE event_id = ?", (event_id,))
            self.conn.execute(
                "DELETE FROM links WHERE from_event = ? OR to_event = ?", (event_id, event_id)
            )
            self.conn.execute("DELETE FROM events WHERE event_id = ?", (event_id,))

    def events_for_day(self, day: str, code: str | None = None) -> list[dict]:
        sql = (
            "SELECT e.*, d.name, d.published_at, d.title, d.tags "
            "FROM events e JOIN documents d ON d.news_id = e.news_id "
            "WHERE substr(d.published_at, 1, 10) = ?"
        )
        params: list[str] = [day]
        if code:
            sql += " AND e.code = ?"
            params.append(code)
        sql += " ORDER BY d.published_at, e.event_id"
        return [dict(row) for row in self.conn.execute(sql, params)]

    def facts_for_event(self, event_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM facts WHERE event_id = ? ORDER BY key", (event_id,)
        )
        return [dict(row) for row in rows]

    def count_events(self, day: str | None = None, code: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM events e JOIN documents d ON d.news_id = e.news_id WHERE 1=1"
        params: list[str] = []
        if day:
            sql += " AND substr(d.published_at, 1, 10) = ?"
            params.append(day)
        if code:
            sql += " AND e.code = ?"
            params.append(code)
        return int(self.conn.execute(sql, params).fetchone()[0])

    def count_documents(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
