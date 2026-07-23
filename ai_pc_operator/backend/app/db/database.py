"""SQLite database setup and connection management."""

from __future__ import annotations

import aiosqlite
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncIterator

# Database path
ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
DB_PATH = ROOT / "ai_pc_operator" / "data" / "agent.db"

# Ensure data directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_DB: aiosqlite.Connection | None = None
_DB_LOCK = asyncio.Lock()


# SQL schema
SCHEMA = """
-- Commands table
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,  -- 'mobile', 'pc', 'api'
    device_id TEXT,
    input_text TEXT NOT NULL,
    intent TEXT,
    risk_level INTEGER DEFAULT 0,
    status TEXT NOT NULL,  -- 'pending', 'approved', 'rejected', 'completed', 'failed'
    result TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
CREATE INDEX IF NOT EXISTS idx_commands_created ON commands(created_at);

-- Approvals table
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER,
    risk_level INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    target TEXT,
    description TEXT NOT NULL,
    impact_summary TEXT,  -- JSON
    status TEXT NOT NULL,  -- 'pending', 'approved', 'rejected', 'expired'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    expires_at TIMESTAMP,
    FOREIGN KEY (command_id) REFERENCES commands(id)
);

CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_approvals_command ON approvals(command_id);

-- Actions table (tool executions)
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER,
    approval_id INTEGER,
    tool TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    risk_level INTEGER DEFAULT 0,
    status TEXT NOT NULL,  -- 'success', 'failed', 'blocked'
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (command_id) REFERENCES commands(id),
    FOREIGN KEY (approval_id) REFERENCES approvals(id)
);

CREATE INDEX IF NOT EXISTS idx_actions_command ON actions(command_id);
CREATE INDEX IF NOT EXISTS idx_actions_tool ON actions(tool);

-- Devices table (paired phones)
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    paired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP,
    active INTEGER DEFAULT 1,
    trust_until TIMESTAMP,
    device_public_key TEXT,
    biometric_key_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_devices_active ON devices(active);
CREATE INDEX IF NOT EXISTS idx_devices_trust ON devices(trust_until);

-- Vault entries (encrypted credentials)
CREATE TABLE IF NOT EXISTS vault_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    username TEXT,
    encrypted_password BLOB NOT NULL,
    salt BLOB NOT NULL,
    nonce BLOB NOT NULL,
    tag BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    UNIQUE(site, username)
);

CREATE INDEX IF NOT EXISTS idx_vault_site ON vault_entries(site);

-- Quarantine table
CREATE TABLE IF NOT EXISTS quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path TEXT NOT NULL,
    quarantine_path TEXT NOT NULL,
    command_id INTEGER,
    file_size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    restored_at TIMESTAMP,
    deleted_at TIMESTAMP,
    FOREIGN KEY (command_id) REFERENCES commands(id)
);

CREATE INDEX IF NOT EXISTS idx_quarantine_restored ON quarantine(restored_at);
CREATE INDEX IF NOT EXISTS idx_quarantine_command ON quarantine(command_id);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    full_access INTEGER DEFAULT 0,
    expires_at TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

-- Settings table
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pairing codes table (legacy 6-digit fallback)
CREATE TABLE IF NOT EXISTS pairing_codes (
    code TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pairing_expires ON pairing_codes(expires_at);

-- QR pairing sessions (new, primary method)
CREATE TABLE IF NOT EXISTS pairing_sessions (
    id TEXT PRIMARY KEY,
    public_key TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pairing_sessions_expires ON pairing_sessions(expires_at);

-- Biometric challenges (Windows Hello / phone biometric)
CREATE TABLE IF NOT EXISTS biometric_challenges (
    id TEXT PRIMARY KEY,
    device_id TEXT,
    challenge TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

CREATE INDEX IF NOT EXISTS idx_biometric_expires ON biometric_challenges(expires_at);

-- Token rotation history (audit trail)
CREATE TABLE IF NOT EXISTS token_rotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    rotated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,  -- 'scheduled', 'manual', 'suspicious'
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

CREATE INDEX IF NOT EXISTS idx_token_rotations_device ON token_rotations(device_id);
"""


async def init_db() -> None:
    """Initialize database with schema."""
    db = await get_db()
    async with _DB_LOCK:
        # Migrate first (for existing DBs without new columns)
        await _migrate_devices(db)
        # Then create schema (idempotent CREATE IF NOT EXISTS)
        await db.executescript(SCHEMA)
        await db.commit()
    print(f"Database initialized at {DB_PATH}")


async def _migrate_devices(db: aiosqlite.Connection) -> None:
    """Add new columns to devices table if missing (idempotent)."""
    # Check if devices table exists first
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='devices'"
    )
    row = await cursor.fetchone()
    if not row:
        # Table doesn't exist yet - schema will create it with all columns
        return

    cursor = await db.execute("PRAGMA table_info(devices)")
    cols = {row[1] for row in await cursor.fetchall()}

    migrations = [
        ("trust_until", "ALTER TABLE devices ADD COLUMN trust_until TIMESTAMP"),
        ("device_public_key", "ALTER TABLE devices ADD COLUMN device_public_key TEXT"),
        ("biometric_key_id", "ALTER TABLE devices ADD COLUMN biometric_key_id TEXT"),
    ]

    for col_name, sql in migrations:
        if col_name not in cols:
            await db.execute(sql)

    await db.commit()


async def get_db() -> aiosqlite.Connection:
    """Get the shared SQLite connection.

    SQLite does not benefit from opening a new connection for every small
    command step. A single shared aiosqlite worker connection keeps file handle
    churn low on 4 GB machines.
    """
    global _DB
    if _DB is None:
        _DB = await aiosqlite.connect(str(DB_PATH))
        _DB.row_factory = aiosqlite.Row
        await _DB.execute("PRAGMA journal_mode=WAL")
        await _DB.execute("PRAGMA synchronous=NORMAL")
        await _DB.execute("PRAGMA busy_timeout=5000")
        await _DB.commit()
    return _DB


@asynccontextmanager
async def db_session() -> AsyncIterator[aiosqlite.Connection]:
    """Serialize access to the shared SQLite connection."""
    db = await get_db()
    async with _DB_LOCK:
        yield db


async def close_db(db: aiosqlite.Connection | None = None) -> None:
    """Close the shared database connection."""
    global _DB
    target = db or _DB
    if target is not None:
        await target.close()
    if db is None or db is _DB:
        _DB = None
