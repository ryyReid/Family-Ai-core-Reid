"""
Family Memory Database (FMDB) + Message Bus
All agents and master read/write through here.
SQLite with WAL mode — fast, local, no server needed.
"""

import sqlite3
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "family_fabric.db"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""

        -- ── Family members ────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS members (
            name        TEXT PRIMARY KEY,
            role        TEXT DEFAULT 'family',
            preferences TEXT DEFAULT '{}',
            dietary     TEXT DEFAULT '[]',
            created_at  TEXT NOT NULL
        );

        -- ── Family Atomic Events: everything that happens ─────────────────
        CREATE TABLE IF NOT EXISTS fae (
            id           TEXT PRIMARY KEY,
            member       TEXT NOT NULL,
            action       TEXT NOT NULL,
            activity     TEXT NOT NULL,
            detail       TEXT DEFAULT '',
            timestamp    TEXT NOT NULL,
            source       TEXT DEFAULT 'chat',
            privacy      TEXT DEFAULT 'shared',
            created_at   TEXT NOT NULL
        );

        -- ── Message bus: how master <-> agents communicate ─────────────────
        -- from_agent: 'master' | agent name (e.g. 'agent_mom')
        -- to_agent:   'master' | agent name
        -- msg_type:   'nudge' | 'fae' | 'question' | 'alert' | 'ack'
        -- status:     'pending' | 'delivered' | 'read'
        CREATE TABLE IF NOT EXISTS messages (
            id          TEXT PRIMARY KEY,
            from_agent  TEXT NOT NULL,
            to_agent    TEXT NOT NULL,
            msg_type    TEXT NOT NULL,
            payload     TEXT NOT NULL,   -- JSON blob
            status      TEXT DEFAULT 'pending',
            created_at  TEXT NOT NULL,
            delivered_at TEXT
        );

        -- ── Per-agent conversation history (each agent keeps its own) ──────
        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent       TEXT NOT NULL,   -- which agent's thread
            role        TEXT NOT NULL,   -- 'user' | 'assistant' | 'system'
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        -- ── Chores ─────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS chores (
            id          TEXT PRIMARY KEY,
            member      TEXT NOT NULL,
            task        TEXT NOT NULL,
            frequency   TEXT DEFAULT 'weekly',
            status      TEXT DEFAULT 'pending',
            last_done   TEXT,
            created_at  TEXT NOT NULL
        );

        -- ── Grocery list ───────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS grocery (
            id          TEXT PRIMARY KEY,
            item        TEXT NOT NULL,
            qty         TEXT DEFAULT '1',
            category    TEXT DEFAULT 'general',
            added_by    TEXT DEFAULT 'family',
            done        INTEGER DEFAULT 0,
            created_at  TEXT NOT NULL
        );

        -- ── Meal log ───────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS meals (
            id          TEXT PRIMARY KEY,
            meal        TEXT NOT NULL,
            planned_for TEXT,
            rating      INTEGER,
            notes       TEXT,
            created_at  TEXT NOT NULL
        );

        -- ── Agent memory: reflections, learned preferences ─────────────────
        CREATE TABLE IF NOT EXISTS agent_memory (
            id           TEXT PRIMARY KEY,
            agent        TEXT NOT NULL,
            memory_type  TEXT DEFAULT 'observation',
            content      TEXT NOT NULL,
            related_to   TEXT,
            created_at   TEXT NOT NULL
        );
        """)


# ══════════════════════════════════════════════════════════════════════════════
#  MESSAGE BUS
# ══════════════════════════════════════════════════════════════════════════════

def send_message(from_agent: str, to_agent: str, msg_type: str, payload: dict) -> str:
    """Post a message on the bus. Returns message id."""
    msg_id = f"msg-{uuid.uuid4().hex[:10]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
            (msg_id, from_agent, to_agent, msg_type,
             json.dumps(payload), "pending", _now(), None)
        )
    return msg_id


def get_pending_messages(to_agent: str) -> list[dict]:
    """Fetch all undelivered messages for an agent."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE to_agent=? AND status='pending' ORDER BY created_at",
            (to_agent,)
        ).fetchall()
    return [dict(r) for r in rows]


def mark_message_delivered(msg_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE messages SET status='delivered', delivered_at=? WHERE id=?",
            (_now(), msg_id)
        )


def get_message_history(limit: int = 30) -> list[dict]:
    """Master uses this to see all recent bus traffic."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
#  CONVERSATIONS (per-agent history)
# ══════════════════════════════════════════════════════════════════════════════

def add_conversation_turn(agent: str, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (agent, role, content, created_at) VALUES (?,?,?,?)",
            (agent, role, content, _now())
        )


def get_conversation(agent: str, limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT role, content FROM conversations
               WHERE agent=? ORDER BY id DESC LIMIT ?""",
            (agent, limit)
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


# ══════════════════════════════════════════════════════════════════════════════
#  FAMILY ATOMIC EVENTS
# ══════════════════════════════════════════════════════════════════════════════

def add_fae(member: str, action: str, activity: str,
            detail: str = "", source: str = "chat", privacy: str = "shared") -> str:
    fae_id = f"fae-{uuid.uuid4().hex[:8]}"
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO fae VALUES (?,?,?,?,?,?,?,?,?)",
            (fae_id, member, action, activity, detail, now, source, privacy, now)
        )
    return fae_id


def get_faes(member: str = None, limit: int = 40) -> list[dict]:
    with get_conn() as conn:
        if member:
            rows = conn.execute(
                "SELECT * FROM fae WHERE member=? ORDER BY timestamp DESC LIMIT ?",
                (member, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM fae ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def search_faes(keyword: str, limit: int = 20) -> list[dict]:
    k = f"%{keyword}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fae WHERE activity LIKE ? OR detail LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (k, k, limit)
        ).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
#  MEMBERS
# ══════════════════════════════════════════════════════════════════════════════

def upsert_member(name: str, role: str = "family",
                  preferences: dict = None, dietary: list = None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO members VALUES (?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 role=excluded.role,
                 preferences=excluded.preferences,
                 dietary=excluded.dietary""",
            (name, role,
             json.dumps(preferences or {}),
             json.dumps(dietary or []),
             _now())
        )


def get_members() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM members ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_member(name: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM members WHERE name=?", (name,)).fetchone()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════════════════════
#  CHORES
# ══════════════════════════════════════════════════════════════════════════════

def add_chore(member: str, task: str, frequency: str = "weekly") -> str:
    cid = f"chore-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chores VALUES (?,?,?,?,?,?,?)",
            (cid, member, task, frequency, "pending", None, _now())
        )
    return cid


def get_chores(member: str = None) -> list[dict]:
    with get_conn() as conn:
        if member:
            rows = conn.execute(
                "SELECT * FROM chores WHERE member=? AND status='pending'", (member,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM chores WHERE status='pending' ORDER BY member"
            ).fetchall()
    return [dict(r) for r in rows]


def done_chore(chore_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE chores SET status='done', last_done=? WHERE id=?",
            (_now(), chore_id)
        )


# ══════════════════════════════════════════════════════════════════════════════
#  GROCERY
# ══════════════════════════════════════════════════════════════════════════════

def add_grocery(item: str, qty: str = "1",
                category: str = "general", added_by: str = "family") -> str:
    gid = f"groc-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO grocery VALUES (?,?,?,?,?,?,?)",
            (gid, item, qty, category, added_by, 0, _now())
        )
    return gid


def get_grocery(done: bool = False) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM grocery WHERE done=? ORDER BY category, item",
            (1 if done else 0,)
        ).fetchall()
    return [dict(r) for r in rows]


def check_grocery(item_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE grocery SET done=1 WHERE id=?", (item_id,))


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT MEMORY
# ══════════════════════════════════════════════════════════════════════════════

def save_memory(agent: str, content: str,
                memory_type: str = "observation", related_to: str = None):
    mid = f"mem-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO agent_memory VALUES (?,?,?,?,?,?)",
            (mid, agent, memory_type, content, related_to, _now())
        )


def get_memories(agent: str, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_memory WHERE agent=? ORDER BY created_at DESC LIMIT ?",
            (agent, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_memories(limit: int = 30) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_memory ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
