"""SQLite-база данных: группы, ученики, занятия, оценки."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    module      TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    id          TEXT PRIMARY KEY,
    last_name   TEXT NOT NULL,
    first_name  TEXT NOT NULL,
    age         INTEGER,
    group_id    TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    comment     TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    topic       TEXT NOT NULL DEFAULT '',
    pc_number   TEXT NOT NULL DEFAULT '',
    client_id   TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS grades (
    id          TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    session_id  TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    value       INTEGER NOT NULL CHECK(value BETWEEN 1 AND 5),
    note        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_students_group   ON students(group_id);
CREATE INDEX IF NOT EXISTS idx_sessions_student ON sessions(student_id);
CREATE INDEX IF NOT EXISTS idx_grades_student   ON grades(student_id);
CREATE INDEX IF NOT EXISTS idx_grades_session   ON grades(session_id);
"""

_DB_NAME = ".classroom.db"


class ClassroomDB:
    def __init__(self, backup_root: Path):
        self._path = backup_root / _DB_NAME
        self._local = threading.local()
        self._lock = threading.RLock()
        self._init()

    # ── internal ──────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def _init(self) -> None:
        with self._lock:
            conn = self._conn()
            conn.executescript(_SCHEMA)
            conn.commit()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn().execute(sql, params)

    def _exec_commit(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn().execute(sql, params)
            self._conn().commit()
            return cur

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return dict(row)

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            cur = self._conn().execute(sql, params)
            return [self._row_to_dict(r) for r in cur.fetchall()]

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        with self._lock:
            cur = self._conn().execute(sql, params)
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    # ── groups ────────────────────────────────────────────────────────────────

    def list_groups(self) -> list[dict]:
        return self._rows("SELECT * FROM groups ORDER BY name")

    def get_group(self, group_id: str) -> dict | None:
        return self._one("SELECT * FROM groups WHERE id = ?", (group_id,))

    def create_group(self, name: str, module: str = "") -> dict:
        gid = self._new_id()
        self._exec_commit(
            "INSERT INTO groups (id, name, module, created_at) VALUES (?, ?, ?, ?)",
            (gid, name.strip(), module.strip(), time.time()),
        )
        return self.get_group(gid)  # type: ignore[return-value]

    def update_group(self, group_id: str, name: str | None = None, module: str | None = None) -> dict | None:
        group = self.get_group(group_id)
        if not group:
            return None
        new_name = (name or group["name"]).strip()
        new_module = (module if module is not None else group["module"]).strip()
        self._exec_commit(
            "UPDATE groups SET name = ?, module = ? WHERE id = ?",
            (new_name, new_module, group_id),
        )
        return self.get_group(group_id)

    def delete_group(self, group_id: str) -> bool:
        cur = self._exec_commit("DELETE FROM groups WHERE id = ?", (group_id,))
        return cur.rowcount > 0

    # ── students ──────────────────────────────────────────────────────────────

    def list_students(self, group_id: str | None = None) -> list[dict]:
        if group_id:
            return self._rows(
                "SELECT * FROM students WHERE group_id = ? ORDER BY last_name, first_name",
                (group_id,),
            )
        return self._rows("SELECT * FROM students ORDER BY last_name, first_name")

    def get_student(self, student_id: str) -> dict | None:
        return self._one("SELECT * FROM students WHERE id = ?", (student_id,))

    def create_student(
        self,
        last_name: str,
        first_name: str,
        group_id: str,
        age: int | None = None,
        comment: str = "",
    ) -> dict:
        sid = self._new_id()
        self._exec_commit(
            "INSERT INTO students (id, last_name, first_name, age, group_id, comment, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, last_name.strip(), first_name.strip(), age, group_id, comment.strip(), time.time()),
        )
        return self.get_student(sid)  # type: ignore[return-value]

    def update_student(
        self,
        student_id: str,
        last_name: str | None = None,
        first_name: str | None = None,
        age: int | None = ...,  # type: ignore[assignment]
        group_id: str | None = None,
        comment: str | None = None,
    ) -> dict | None:
        s = self.get_student(student_id)
        if not s:
            return None
        new_last  = (last_name or s["last_name"]).strip()
        new_first = (first_name or s["first_name"]).strip()
        new_age   = s["age"] if age is ... else age  # type: ignore[comparison-overlap]
        new_group = group_id or s["group_id"]
        new_comment = (comment if comment is not None else s["comment"]).strip()
        self._exec_commit(
            "UPDATE students SET last_name=?, first_name=?, age=?, group_id=?, comment=? WHERE id=?",
            (new_last, new_first, new_age, new_group, new_comment, student_id),
        )
        return self.get_student(student_id)

    def delete_student(self, student_id: str) -> bool:
        cur = self._exec_commit("DELETE FROM students WHERE id = ?", (student_id,))
        return cur.rowcount > 0

    # ── sessions ──────────────────────────────────────────────────────────────

    def create_session(
        self,
        student_id: str,
        topic: str = "",
        pc_number: str = "",
        client_id: str = "",
    ) -> dict:
        sess_id = self._new_id()
        self._exec_commit(
            "INSERT INTO sessions (id, student_id, topic, pc_number, client_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (sess_id, student_id, topic.strip(), pc_number.strip(), client_id.strip(), time.time()),
        )
        return self._one("SELECT * FROM sessions WHERE id = ?", (sess_id,))  # type: ignore[return-value]

    def list_sessions(self, student_id: str) -> list[dict]:
        return self._rows(
            "SELECT s.*, g.value AS grade_value, g.note AS grade_note"
            " FROM sessions s"
            " LEFT JOIN grades g ON g.session_id = s.id"
            " WHERE s.student_id = ?"
            " ORDER BY s.created_at DESC",
            (student_id,),
        )

    # ── grades ────────────────────────────────────────────────────────────────

    def set_grade(
        self,
        student_id: str,
        session_id: str | None,
        value: int,
        note: str = "",
    ) -> dict:
        # Upsert: один grade per session
        existing = None
        if session_id:
            existing = self._one(
                "SELECT * FROM grades WHERE session_id = ?", (session_id,)
            )
        if existing:
            self._exec_commit(
                "UPDATE grades SET value=?, note=?, student_id=? WHERE id=?",
                (value, note.strip(), student_id, existing["id"]),
            )
            return self._one("SELECT * FROM grades WHERE id = ?", (existing["id"],))  # type: ignore[return-value]
        gid = self._new_id()
        self._exec_commit(
            "INSERT INTO grades (id, student_id, session_id, value, note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (gid, student_id, session_id, value, note.strip(), time.time()),
        )
        return self._one("SELECT * FROM grades WHERE id = ?", (gid,))  # type: ignore[return-value]

    def get_grades(self, student_id: str) -> list[dict]:
        return self._rows(
            "SELECT * FROM grades WHERE student_id = ? ORDER BY created_at DESC",
            (student_id,),
        )
