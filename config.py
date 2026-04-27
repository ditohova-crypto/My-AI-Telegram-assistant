"""
Конфигурация Telegram-бота AI Assistant
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.moonshot.ai/v1")
AI_MODEL = os.getenv("AI_MODEL", "kimi-k2.5")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "1"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2048"))

ADMIN_USER_IDS = [550553189]
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
MAX_MESSAGE_LENGTH = 4000

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", """Ты — полноценный AI-ассистент на русском языке. Твои качества:
1. Профессионализм: точные ответы с логикой.
2. Дружелюбие: уважительно, с теплотой.
3. Контекстность: помнишь историю разговора.
4. Структура: маркдаун-списки, параграфы, жирный/курсив.
5. Краткость: по существу, без воды.
6. Безопасность: не помогаешь в незаконной деятельности.

Форматирование Telegram:
- Жирный: **текст**
- Курсив: *текст*
- Код: `код`
- Блок кода: ```язык\nкод\n```
- Списки: - или 1. 2. 3.

Отвечай на языке пользователя (по умолчанию русский).""")

BRIEF_PROMPT = os.getenv("BRIEF_PROMPT", """Ты — персональный ассистент. На основе истории сообщений составь краткий утренний бриф:
1. Ключевые темы вчерашнего дня
2. Незавершённые дела
3. Идеи и инсайты
4. Сегодняшний фокус
Формат: Markdown, максимум 300 слов.""")

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

BASE_DIR = Path(__file__).parent
# Persistent Disk на Render примонтирован к /app/data
DB_PATH = Path("/app/data/chat_history.db")
LOGS_DIR = BASE_DIR / "logs"

def validate_config():
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN не указан.")
    if not AI_API_KEY:
        errors.append("AI_API_KEY не указан.")
    if errors:
        raise ValueError("\n".join(errors))
