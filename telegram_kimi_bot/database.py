"""
Модуль работы с базой данных SQLite для хранения истории диалогов.
"""
import sqlite3
import json
import logging
from datetime import datetime
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
        
        # Индексы для быстрого поиска
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_user_id 
            ON chat_history(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_created_at 
            ON chat_history(created_at)
        """)
        
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
    """
    Возвращает историю диалога пользователя в формате для OpenAI API.
    
    Args:
        user_id: ID пользователя Telegram
        limit: Максимальное количество сообщений (по умолчанию из конфига)
    
    Returns:
        Список словарей [{'role': 'user'/'assistant', 'content': 'текст'}]
    """
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
            # Возвращаем в хронологическом порядке (старые → новые)
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
    except Exception as e:
        logger.error("Ошибка получения истории: %s", e, exc_info=True)
        return []


def clear_user_history(user_id: int) -> int:
    """Очищает историю диалога пользователя. Возвращает количество удалённых сообщений."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM chat_history WHERE user_id = ?",
                (user_id,)
            )
            deleted = cursor.rowcount
            conn.commit()
            logger.info("История очищена для user_id=%s, удалено сообщений: %d", user_id, deleted)
            return deleted
    except Exception as e:
        logger.error("Ошибка очистки истории: %s", e, exc_info=True)
        return 0


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
            cursor.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
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


def cleanup_old_history(days: int = 30) -> int:
    """Удаляет сообщения старше N дней. Возвращает количество удалённых."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM chat_history 
                WHERE created_at < datetime('now', '-' || ? || ' days')
                """,
                (days,)
            )
            deleted = cursor.rowcount
            conn.commit()
            logger.info("Очистка старой истории: удалено %d сообщений (старше %d дней)", deleted, days)
            return deleted
    except Exception as e:
        logger.error("Ошибка очистки старой истории: %s", e, exc_info=True)
        return 0
