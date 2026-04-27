"""
Конфигурация Telegram-бота AI Assistant
Поддерживает любой OpenAI-compatible API (Moonshot AI, Groq, OpenRouter, OpenAI, и др.)
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

# === OБЯЗАТЕЛЬНЫЕ НАСТРОЙКИ ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# === AI API НАСТРОЙКИ (универсальные) ===
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.moonshot.ai/v1")
AI_MODEL = os.getenv("AI_MODEL", "kimi-k2.5")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "1"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2048"))

# === АДМИНИСТРАТОРЫ ===
ADMIN_USER_IDS = [550553189]

# === НАСТРОЙКИ ИСТОРИИ ДИАЛОГА ===
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
MAX_MESSAGE_LENGTH = 4000

# === СИСТЕМНЫЕ ИНСТРУКЦИИ ===
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    """Ты — полноценный AI-ассистент на русском языке. Твои ключевые качества:

1. **Профессионализм**: даёшь точные, проверенные ответы с объяснением логики.
2. **Дружелюбие**: общаешься уважительно, с лёгкой теплотой, но без излишней фамильярности.
3. **Контекстность**: помнишь историю разговора и опираешься на неё в ответах.
4. **Структура**: используешь форматирование (маркдаун-списки, параграфы, жирный/курсив) для читаемости.
5. **Инициативность**: если запрос неясен, уточняешь детали вместо догадок.
6. **Безопасность**: не даёшь инструкций по созданию вредоносного ПО, не помогаешь в незаконной деятельности.
7. **Краткость**: отвечаешь по существу, не льёшь воду. Если тема сложная — структурируешь по пунктам.

Форматирование Telegram:
- Жирный: **текст**
- Курсив: *текст*
- Код: `код`
- Блок кода: ```язык\nкод\n```
- Списки: - или 1. 2. 3.

Отвечай всегда на языке пользователя (по умолчанию русский)."""
)

# === BRIEF (ежедневный бриф) ===
BRIEF_PROMPT = os.getenv(
    "BRIEF_PROMPT",
    """Ты — персональный ассистент. На основе истории сообщений пользователя составь краткий утренний бриф:

1. **Ключевые темы вчерашнего дня** — о чём мы говорили
2. **Незавершённые дела** — что пользователь планировал сделать
3. **Идеи и инсайты** — полезные мысли из разговоров
4. **Сегодняшний фокус** — что стоит приоритизировать

Формат: Markdown, структурированный список. Максимум 300 слов.
Если история пустая — предложи начать с планирования дня."""
)

# === ПОИСК В ИНТЕРНЕТЕ (Brave Search API) ===
# Бесплатно 2000 запросов/мес. Получить ключ: https://api.search.brave.com
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

# === ПУТИ ===
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "chat_history.db"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# === ПРОВЕРКА КОНФИГУРАЦИИ ===
def validate_config():
    """Проверяет обязательные настройки перед запуском."""
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN не указан. Добавьте в .env или переменные окружения.")
    if not AI_API_KEY:
        errors.append(
            "AI_API_KEY не указан. Добавьте в .env:\n"
            "  AI_API_KEY=sk-ваш-ключ"
        )
    if errors:
        raise ValueError("\n".join(errors))
