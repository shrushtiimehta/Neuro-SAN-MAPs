"""Transactional live state for the upstream GMemory MAPS ablation.

GMemory stores completed task trajectories. This SQLite layer holds the current
episode's mutable plan, scratchpads, and trials until they can be committed as
one completed task to upstream GMemory. It never reads or writes runtime Markdown.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from coded_tools.state_dir import state_path


class GMemoryStore:
    """Keep live episode records in one transactional database."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or state_path("g_memory_live.sqlite3")
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    name TEXT PRIMARY KEY,
                    body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trials (
                    trial_id TEXT PRIMARY KEY,
                    episode INTEGER NOT NULL,
                    origin TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    episode INTEGER NOT NULL,
                    trial_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (episode, trial_id)
                );
                CREATE TABLE IF NOT EXISTS counters (
                    episode INTEGER PRIMARY KEY,
                    next_suffix INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS interactions (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode INTEGER NOT NULL,
                    turn INTEGER NOT NULL,
                    chat_kind TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    parent_name TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    committed INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_interactions_episode ON interactions(episode, committed, event_id);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def get(self, name: str) -> str | None:
        """Read one named live document."""
        with self._connect() as connection:
            row = connection.execute("SELECT body FROM documents WHERE name = ?", (name,)).fetchone()
        return str(row["body"]) if row is not None else None

    def put(self, name: str, body: str) -> None:
        """Replace one named live document."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO documents (name, body) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET body = excluded.body",
                (name, body),
            )

    def pop(self, name: str) -> str:
        """Read and delete a one-use document atomically."""
        with self._connect() as connection:
            row = connection.execute("SELECT body FROM documents WHERE name = ?", (name,)).fetchone()
            connection.execute("DELETE FROM documents WHERE name = ?", (name,))
        return str(row["body"]) if row is not None else ""

    def seed(self, name: str, body: str, overwrite: bool = False) -> bool:
        """Insert a baseline once, or replace it for a fresh run."""
        with self._connect() as connection:
            if overwrite:
                connection.execute(
                    "INSERT INTO documents (name, body) VALUES (?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET body = excluded.body",
                    (name, body),
                )
                return True
            cursor = connection.execute("INSERT OR IGNORE INTO documents VALUES (?, ?)", (name, body))
        return cursor.rowcount > 0

    def log_trial(self, episode: int, payload: dict[str, Any]) -> str:
        """Mint an ID and store its rule and criteria in one transaction."""
        with self._connect() as connection:
            row = connection.execute("SELECT next_suffix FROM counters WHERE episode = ?", (episode,)).fetchone()
            suffix = int(row["next_suffix"]) if row is not None else 1
            trial_id = f"t{episode}_{suffix}"
            connection.execute(
                "INSERT INTO counters VALUES (?, ?) "
                "ON CONFLICT(episode) DO UPDATE SET next_suffix = excluded.next_suffix",
                (episode, suffix + 1),
            )
            saved = {**payload, "trial_id": trial_id, "ep": episode}
            connection.execute(
                "INSERT INTO trials VALUES (?, ?, ?, ?, ?, 1)",
                (trial_id, episode, saved.get("origin", ""), saved.get("domain", ""), json.dumps(saved)),
            )
        return trial_id

    def trials(self, *, active: bool = True) -> list[dict[str, Any]]:
        """List stored trials in ID order."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM trials WHERE active = ? ORDER BY episode, trial_id",
                (int(active),),
            ).fetchall()
        return [json.loads(str(row["payload"])) for row in rows]

    def retire(self, trial_ids: list[str]) -> list[str]:
        """Deactivate exactly the named live trials."""
        if not trial_ids:
            return []
        retired: list[str] = []
        with self._connect() as connection:
            for trial_id in trial_ids:
                cursor = connection.execute(
                    "UPDATE trials SET active = 0 WHERE trial_id = ? AND active = 1", (trial_id,)
                )
                if cursor.rowcount:
                    retired.append(trial_id)
        return retired

    def record_outcomes(self, episode: int, outcomes: list[dict[str, Any]], retire_ids: list[str]) -> int:
        """Save macro verdicts and retire resolved trials together."""
        written = 0
        with self._connect() as connection:
            for outcome in outcomes:
                if outcome.get("origin") == "micro":
                    continue
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO outcomes VALUES (?, ?, ?)",
                    (episode, str(outcome.get("trial_id", "")), json.dumps(outcome)),
                )
                written += cursor.rowcount
            for trial_id in retire_ids:
                connection.execute("UPDATE trials SET active = 0 WHERE trial_id = ?", (trial_id,))
        return written

    def outcomes(self) -> list[dict[str, Any]]:
        """Return all cross-episode trial verdicts."""
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM outcomes ORDER BY episode, trial_id").fetchall()
        return [json.loads(str(row["payload"])) for row in rows]

    def append_interaction(self, event: dict[str, Any]) -> int:
        """Record one planner, watcher, coordinator, or specialist exchange."""
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO interactions (
                    episode, turn, chat_kind, agent_name, parent_name,
                    message_type, target_name, content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(event.get("episode", 0)),
                    int(event.get("turn", 0)),
                    str(event.get("chat_kind", "")),
                    str(event.get("agent_name", "")),
                    str(event.get("parent_name", "")),
                    str(event.get("message_type", "")),
                    str(event.get("target_name", "")),
                    str(event.get("content", "")),
                ),
            )
        return int(cursor.lastrowid)

    def interactions(self, episode: int) -> list[dict[str, Any]]:
        """Read all uncommitted agent exchanges for one completed episode."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM interactions WHERE episode = ? AND committed = 0 ORDER BY event_id",
                (episode,),
            ).fetchall()
        return [dict(row) for row in rows]

    def commit_interactions(self, episode: int, event_ids: list[int]) -> None:
        """Mark exactly the interactions represented in the upstream graph."""
        with self._connect() as connection:
            connection.executemany(
                "UPDATE interactions SET committed = 1 WHERE episode = ? AND event_id = ?",
                [(episode, event_id) for event_id in event_ids],
            )
