"""
Конфигурация Telegram-бота AI Assistant
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === OБЯЗАТЕЛЬНЫЕ ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# === AI API ===
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.moonshot.ai/v1")
AI_MODEL = os.getenv("AI_MODEL", "kimi-k2.5")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "1"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2048"))

# === АДМИНЫ ===
ADMIN_USER_IDS = [550553189]

# === ИСТОРИЯ ===
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
MAX_MESSAGE_LENGTH = 4000

# === СИСТЕМНЫЙ ПРОМПТ ===
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    """Ты — полноценный AI-ассистент на русском языке. Профессиональный, дружелюбный, помнишь историю разговора, используешь Markdown."""
)

# === BRIEF ===
BRIEF_PROMPT = os.getenv(
    "BRIEF_PROMPT",
    """Ты — персональный ассистент. Составь краткий утренний бриф на основе истории сообщений."""
)

# === ПОИСК ===
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

# === ПУТИ ===
BASE_DIR = Path(__file__).parent
# Для Render Starter с Persistent Disk:
DB_PATH = Path("/app/data/chat_history.db")
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

def validate_config():
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN не указан")
    if not AI_API_KEY:
        errors.append("AI_API_KEY не указан")
    if errors:
        raise ValueError("\n".join(errors))
