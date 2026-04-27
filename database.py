"""
Модуль работы с базой данных SQLite.
"""
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from contextlib import contextmanager

from config import DB_PATH, MAX_HISTORY_MESSAGES

logger = logging.getLogger(__name__)

# === ГЛАВНОЕ: создаём папку для базы если её нет ===
try:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Папка базы проверена: %s", DB_PATH.parent)
except Exception as e:
    logger.warning("Не удалось создать папку %s: %s", DB_PATH.parent, e)


def init_db() -> None:
    """Инициализация базы данных."""
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                message_count INTEGER DEFAULT 0,
                total_tokens_used INTEGER DEFAULT 0,
                last_active TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                remind_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_sent INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_briefs (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                is_enabled INTEGER DEFAULT 0,
                brief_time TEXT DEFAULT '09:00',
                timezone_offset INTEGER DEFAULT 3,
                last_sent TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_user_id ON chat_history(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_created_at ON chat_history(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders(remind_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_sent ON reminders(is_sent)")
        conn.commit()
    logger.info("База готова: %s", DB_PATH)


@contextmanager
def _get_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def save_message(user_id: int, role: str, content: str) -> None:
    try:
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content)
            )
            conn.commit()
    except Exception as e:
        logger.error("Ошибка сохранения: %s", e)


def get_user_history(user_id: int, limit: int = MAX_HISTORY_MESSAGES) -> List[Dict[str, str]]:
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                "SELECT role, content FROM chat_history WHERE user_id = ? AND role IN ('user', 'assistant') ORDER BY created_at DESC, id DESC LIMIT ?",
                (user_id, limit)
            )
            rows = cur.fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    except Exception as e:
        logger.error("Ошибка истории: %s", e)
        return []


def clear_user_history(user_id: int) -> int:
    try:
        with _get_connection() as conn:
            cur = conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
            conn.commit()
            return cur.rowcount
    except Exception as e:
        logger.error("Ошибка очистки: %s", e)
        return 0


def get_full_user_history(user_id: int, limit: int = 100) -> List[Dict]:
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                "SELECT role, content, created_at FROM chat_history WHERE user_id = ? AND role IN ('user', 'assistant') ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("Ошибка: %s", e)
        return []


def update_user_info(user_id: int, username: Optional[str], first_name: Optional[str],
                     last_name: Optional[str], tokens_used: int = 0) -> None:
    try:
        with _get_connection() as conn:
            now = datetime.now().isoformat()
            conn.execute(
                """INSERT INTO users (user_id, username, first_name, last_name, message_count, total_tokens_used, last_active)
                   VALUES (?, ?, ?, ?, 1, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       username = excluded.username,
                       first_name = excluded.first_name,
                       last_name = excluded.last_name,
                       message_count = message_count + 1,
                       total_tokens_used = total_tokens_used + excluded.total_tokens_used,
                       last_active = excluded.last_active""",
                (user_id, username, first_name, last_name, tokens_used, now)
            )
            conn.commit()
    except Exception as e:
        logger.error("Ошибка юзера: %s", e)


def get_user_stats(user_id: int) -> Optional[Dict]:
    try:
        with _get_connection() as conn:
            cur = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error("Ошибка статистики: %s", e)
        return None


def get_all_users_count() -> int:
    try:
        with _get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    except Exception as e:
        logger.error("Ошибка: %s", e)
        return 0


def add_reminder(user_id: int, chat_id: int, text: str, remind_at: datetime) -> int:
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO reminders (user_id, chat_id, text, remind_at) VALUES (?, ?, ?, ?)",
                (user_id, chat_id, text, remind_at.isoformat())
            )
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("Ошибка remind: %s", e)
        return -1


def get_pending_reminders(before: datetime) -> List[Dict]:
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM reminders WHERE is_sent = 0 AND remind_at <= ? ORDER BY remind_at ASC",
                (before.isoformat(),)
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("Ошибка: %s", e)
        return []


def mark_reminder_sent(reminder_id: int) -> None:
    try:
        with _get_connection() as conn:
            conn.execute("UPDATE reminders SET is_sent = 1 WHERE id = ?", (reminder_id,))
            conn.commit()
    except Exception as e:
        logger.error("Ошибка: %s", e)


def get_user_reminders(user_id: int) -> List[Dict]:
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                "SELECT id, text, remind_at, created_at FROM reminders WHERE user_id = ? AND is_sent = 0 ORDER BY remind_at ASC",
                (user_id,)
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("Ошибка: %s", e)
        return []


def cancel_reminder(user_id: int, reminder_id: int) -> bool:
    try:
        with _get_connection() as conn:
            cur = conn.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("Ошибка: %s", e)
        return False


def set_daily_brief(user_id: int, chat_id: int, enabled: bool, time_str: str = "09:00") -> None:
    try:
        with _get_connection() as conn:
            conn.execute(
                """INSERT INTO daily_briefs (user_id, chat_id, is_enabled, brief_time)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       chat_id = excluded.chat_id,
                       is_enabled = excluded.is_enabled,
                       brief_time = excluded.brief_time""",
                (user_id, chat_id, 1 if enabled else 0, time_str)
            )
            conn.commit()
    except Exception as e:
        logger.error("Ошибка брифа: %s", e)


def get_daily_briefs_due(now: datetime) -> List[Dict]:
    try:
        with _get_connection() as conn:
            today = now.strftime("%Y-%m-%d")
            current_time = now.strftime("%H:%M")
            cur = conn.execute(
                """SELECT * FROM daily_briefs
                   WHERE is_enabled = 1
                     AND (last_sent IS NULL OR substr(last_sent, 1, 10) < ?)
                     AND brief_time <= ?""",
                (today, current_time)
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("Ошибка: %s", e)
        return []


def mark_brief_sent(user_id: int) -> None:
    try:
        with _get_connection() as conn:
            conn.execute(
                "UPDATE daily_briefs SET last_sent = ? WHERE user_id = ?",
                (datetime.now().strftime("%Y-%m-%d"), user_id)
            )
            conn.commit()
    except Exception as e:
        logger.error("Ошибка: %s", e)


def get_user_brief_settings(user_id: int) -> Optional[Dict]:
    try:
        with _get_connection() as conn:
            cur = conn.execute("SELECT * FROM daily_briefs WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error("Ошибка: %s", e)
        return None


def cleanup_old_history(days: int = 30) -> int:
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM chat_history WHERE created_at < datetime('now', '-' || ? || ' days')",
                (days,)
            )
            conn.commit()
            return cur.rowcount
    except Exception as e:
        logger.error("Ошибка: %s", e)
        return 0
