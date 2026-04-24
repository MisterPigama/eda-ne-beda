# 📄 файл: database.py
import aiosqlite
import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = "data/bot.db"


from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db():
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db():
    """Создание таблиц и миграции при старте."""
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        # --- users ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # --- sessions ---
        # status: active | warned | aborted | complete | incomplete
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL REFERENCES users(id),
                status           TEXT NOT NULL DEFAULT 'active',
                current_step     TEXT,
                answers_json     TEXT NOT NULL DEFAULT '{}',
                last_interaction TEXT NOT NULL DEFAULT (datetime('now')),
                created_at       TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # --- meals ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS meals (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL REFERENCES users(id),
                session_id       INTEGER REFERENCES sessions(id),
                timestamp_part1  TEXT,
                timestamp_part2  TEXT,
                part1_data_json  TEXT NOT NULL DEFAULT '{}',
                part2_data_json  TEXT NOT NULL DEFAULT '{}',
                is_complete      INTEGER NOT NULL DEFAULT 0
            )
        """)

        # --- schema_version (для будущих миграций) ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)

        await _run_migrations(db)
        await db.commit()
        logger.info("БД инициализирована успешно.")


async def _run_migrations(db: aiosqlite.Connection):
    """Применяет миграции, которые ещё не были применены."""
    cursor = await db.execute("SELECT MAX(version) FROM schema_version")
    row = await cursor.fetchone()
    current = row[0] if row[0] is not None else 0

    migrations = {
        1: _migration_1,
    }

    for version, fn in sorted(migrations.items()):
        if version > current:
            logger.info(f"Применяю миграцию версии {version}...")
            await fn(db)
            await db.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (version,)
            )
            logger.info(f"Миграция {version} применена.")


async def _migration_1(db: aiosqlite.Connection):
    """Начальная схема уже создана в init_db — миграция-заглушка v1."""
    pass


# ---------------------------------------------------------------------------
# Вспомогательные функции для работы с сессиями
# ---------------------------------------------------------------------------

async def ensure_user(db: aiosqlite.Connection, user_id: int):
    await db.execute(
        "INSERT OR IGNORE INTO users (id) VALUES (?)",
        (user_id,)
    )


async def get_active_session(db: aiosqlite.Connection, user_id: int) -> aiosqlite.Row | None:
    cursor = await db.execute(
        """
        SELECT * FROM sessions
        WHERE user_id = ? AND status IN ('active', 'warned')
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,)
    )
    return await cursor.fetchone()


async def create_session(db: aiosqlite.Connection, user_id: int) -> int:
    await ensure_user(db, user_id)
    cursor = await db.execute(
        """
        INSERT INTO sessions (user_id, status, current_step, answers_json, last_interaction)
        VALUES (?, 'active', 'q1_step_0', '{}', datetime('now'))
        """,
        (user_id,)
    )
    await db.commit()
    return cursor.lastrowid


async def update_session_step(
    db: aiosqlite.Connection,
    session_id: int,
    step: str,
    answers_json: str
):
    await db.execute(
        """
        UPDATE sessions
        SET current_step = ?,
            answers_json = ?,
            last_interaction = datetime('now'),
            status = 'active'
        WHERE id = ?
        """,
        (step, answers_json, session_id)
    )
    await db.commit()


async def mark_session_warned(db: aiosqlite.Connection, session_id: int):
    await db.execute(
        "UPDATE sessions SET status = 'warned' WHERE id = ?",
        (session_id,)
    )
    await db.commit()


async def mark_session_aborted(db: aiosqlite.Connection, session_id: int):
    await db.execute(
        "UPDATE sessions SET status = 'aborted' WHERE id = ?",
        (session_id,)
    )
    await db.commit()


async def mark_session_complete(db: aiosqlite.Connection, session_id: int):
    await db.execute(
        "UPDATE sessions SET status = 'complete' WHERE id = ?",
        (session_id,)
    )
    await db.commit()


async def upsert_meal_part1(
    db: aiosqlite.Connection,
    user_id: int,
    session_id: int,
    part1_json: str
) -> int:
    cursor = await db.execute(
        "SELECT id FROM meals WHERE session_id = ?",
        (session_id,)
    )
    row = await cursor.fetchone()
    if row:
        await db.execute(
            """
            UPDATE meals
            SET part1_data_json = ?, timestamp_part1 = datetime('now')
            WHERE id = ?
            """,
            (part1_json, row["id"])
        )
        await db.commit()
        return row["id"]
    else:
        cursor = await db.execute(
            """
            INSERT INTO meals (user_id, session_id, timestamp_part1, part1_data_json)
            VALUES (?, ?, datetime('now'), ?)
            """,
            (user_id, session_id, part1_json)
        )
        await db.commit()
        return cursor.lastrowid


async def save_meal_part2(
    db: aiosqlite.Connection,
    session_id: int,
    part2_json: str
):
    await db.execute(
        """
        UPDATE meals
        SET part2_data_json = ?,
            timestamp_part2 = datetime('now'),
            is_complete = 1
        WHERE session_id = ?
        """,
        (part2_json, session_id)
    )
    await db.commit()