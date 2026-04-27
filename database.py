"""
Модуль работы с базой данных SQLite для хранения истории диалогов,
напоминаний и ежедневных брифов.
"""
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager

from config import DB_PATH, MAX_HISTORY_MESSAGES

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Инициализация базы данных: создание таблиц, если их нет."""
    with _get_connection() as conn:
        cursor = conn.cursor()
        
        # Таблица истории сообщений
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица информации о пользователях
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
        
        # === НОВОЕ: Таблица напоминаний ===
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
        
        # === НОВОЕ: Таблица настроек ежедневного брифа ===
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
        
        # Индексы
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_user_id ON chat_history(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_created_at ON chat_history(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders(remind_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_sent ON reminders(is_sent)")
        
        conn.commit()
    logger.info("База данных инициализирована: %s", DB_PATH)


@contextmanager
def _get_connection():
    """Контекстный менеджер для соединения с БД."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# === ИСТОРИЯ ДИАЛОГА ===

def save_message(user_id: int, role: str, content: str) -> None:
    """Сохраняет одно сообщение в историю."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content)
            )
            conn.commit()
    except Exception as e:
        logger.error("Ошибка сохранения сообщения: %s", e, exc_info=True)


def get_user_history(user_id: int, limit: int = MAX_HISTORY_MESSAGES) -> List[Dict[str, str]]:
    """Возвращает историю диалога пользователя в формате для OpenAI API."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content 
                FROM chat_history 
                WHERE user_id = ? AND role IN ('user', 'assistant')
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit)
            )
            rows = cursor.fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
    except Exception as e:
        logger.error("Ошибка получения истории: %s", e, exc_info=True)
        return []


def clear_user_history(user_id: int) -> int:
    """Очищает историю диалога пользователя."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
            deleted = cursor.rowcount
            conn.commit()
            logger.info("История очищена для user_id=%s, удалено: %d", user_id, deleted)
            return deleted
    except Exception as e:
        logger.error("Ошибка очистки истории: %s", e, exc_info=True)
        return 0


def get_full_user_history(user_id: int, limit: int = 100) -> List[Dict]:
    """Возвращает полную историю для брифа (с датами)."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content, created_at
                FROM chat_history
                WHERE user_id = ? AND role IN ('user', 'assistant')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return []


# === ПОЛЬЗОВАТЕЛИ ===

def update_user_info(user_id: int, username: Optional[str], first_name: Optional[str], 
                     last_name: Optional[str], tokens_used: int = 0) -> None:
    """Обновляет информацию о пользователе."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name, message_count, total_tokens_used, last_active)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    message_count = message_count + 1,
                    total_tokens_used = total_tokens_used + excluded.total_tokens_used,
                    last_active = excluded.last_active
                """,
                (user_id, username, first_name, last_name, tokens_used, now)
            )
            conn.commit()
    except Exception as e:
        logger.error("Ошибка обновления пользователя: %s", e, exc_info=True)


def get_user_stats(user_id: int) -> Optional[Dict]:
    """Возвращает статистику пользователя."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error("Ошибка получения статистики: %s", e, exc_info=True)
        return None


def get_all_users_count() -> int:
    """Возвращает общее количество пользователей (для админов)."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM users")
            return cursor.fetchone()["count"]
    except Exception as e:
        logger.error("Ошибка подсчёта пользователей: %s", e, exc_info=True)
        return 0


def get_all_active_users() -> List[Dict]:
    """Возвращает всех пользователей для рассылки брифов."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY last_active DESC")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return []


# === НАПОМИНАНИЯ (REMINDERS) ===

def add_reminder(user_id: int, chat_id: int, text: str, remind_at: datetime) -> int:
    """Добавляет напоминание. Возвращает ID напоминания."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reminders (user_id, chat_id, text, remind_at) VALUES (?, ?, ?, ?)",
                (user_id, chat_id, text, remind_at.isoformat())
            )
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error("Ошибка добавления напоминания: %s", e, exc_info=True)
        return -1


def get_pending_reminders(before: datetime) -> List[Dict]:
    """Возвращает напоминания, которые нужно отправить сейчас."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM reminders 
                WHERE is_sent = 0 AND remind_at <= ?
                ORDER BY remind_at ASC
                """,
                (before.isoformat(),)
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error("Ошибка получения напоминаний: %s", e, exc_info=True)
        return []


def mark_reminder_sent(reminder_id: int) -> None:
    """Отмечает напоминание как отправленное."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET is_sent = 1 WHERE id = ?",
                (reminder_id,)
            )
            conn.commit()
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)


def get_user_reminders(user_id: int) -> List[Dict]:
    """Возвращает активные напоминания пользователя."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, text, remind_at, created_at 
                FROM reminders 
                WHERE user_id = ? AND is_sent = 0
                ORDER BY remind_at ASC
                """,
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return []


def cancel_reminder(user_id: int, reminder_id: int) -> bool:
    """Удаляет напоминание пользователя."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM reminders WHERE id = ? AND user_id = ?",
                (reminder_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return False


# === ЕЖЕДНЕВНЫЙ БРИФ ===

def set_daily_brief(user_id: int, chat_id: int, enabled: bool, time_str: str = "09:00") -> None:
    """Включает/выключает ежедневный бриф."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO daily_briefs (user_id, chat_id, is_enabled, brief_time)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    chat_id = excluded.chat_id,
                    is_enabled = excluded.is_enabled,
                    brief_time = excluded.brief_time
                """,
                (user_id, chat_id, 1 if enabled else 0, time_str)
            )
            conn.commit()
    except Exception as e:
        logger.error("Ошибка настройки брифа: %s", e, exc_info=True)


def get_daily_briefs_due(now: datetime) -> List[Dict]:
    """Возвращает пользователей, которым пора отправить бриф."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            # Выбираем тех, у кого бриф включен и last_sent < сегодня
            today = now.strftime("%Y-%m-%d")
            cursor.execute(
                """
                SELECT * FROM daily_briefs
                WHERE is_enabled = 1
                  AND (last_sent IS NULL OR last_sent < ?)
                  AND brief_time <= ?
                """,
                (today, now.strftime("%H:%M"))
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error("Ошибка получения брифов: %s", e, exc_info=True)
        return []


def mark_brief_sent(user_id: int) -> None:
    """Отмечает бриф как отправленный сегодня."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE daily_briefs SET last_sent = ? WHERE user_id = ?",
                (datetime.now().isoformat(), user_id)
            )
            conn.commit()
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)


def get_user_brief_settings(user_id: int) -> Optional[Dict]:
    """Возвращает настройки брифа пользователя."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM daily_briefs WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return None


# === ОЧИСТКА ===

def cleanup_old_history(days: int = 30) -> int:
    """Удаляет сообщения старше N дней."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM chat_history WHERE created_at < datetime('now', '-' || ? || ' days')",
                (days,)
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted
    except Exception as e:
        logger.error("Ошибка очистки: %s", e, exc_info=True)
        return 0
