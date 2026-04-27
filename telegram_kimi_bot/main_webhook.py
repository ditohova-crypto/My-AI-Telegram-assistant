"""
Webhook-версия бота для облачных платформ (Render, Railway, AWS, etc.)
Использует FastAPI + python-telegram-bot для обработки webhook от Telegram.

Преимущества webhook перед polling для облака:
- Не требует постоянного открытого соединения
- Сервер просыпается при входящем сообщении (актуально для free tier)
- Экономит ресурсы и стабильнее при разрывах связи
"""
import os
import sys
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from telegram import Update

from bot import create_application

# === НАСТРОЙКИ WEBHOOK ===
WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-in-render-env")

# Render предоставляет внешний хост в переменной RENDER_EXTERNAL_HOSTNAME
RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if RENDER_HOST:
    WEBHOOK_URL = f"https://{RENDER_HOST}{WEBHOOK_PATH}"
else:
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# === СОЗДАНИЕ PTB ПРИЛОЖЕНИЯ ===
ptb_app = create_application()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Жизненный цикл FastAPI:
    - При старте: устанавливаем webhook в Telegram
    - При остановке: удаляем webhook, останавливаем PTB
    """
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL не задан. Укажите WEBHOOK_URL в .env или используйте Render.")
        sys.exit(1)
    
    logger.info("Установка webhook: %s", WEBHOOK_URL)
    await ptb_app.bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=Update.ALL_TYPES,
    )
    
    await ptb_app.initialize()
    await ptb_app.start()
    logger.info("PTB приложение запущено. Бот готов принимать сообщения.")
    
    yield
    
    logger.info("Остановка PTB приложения...")
    await ptb_app.stop()
    await ptb_app.shutdown()
    await ptb_app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook удалён. Приложение остановлено.")


# === FASTAPI ПРИЛОЖЕНИЕ ===
fastapi_app = FastAPI(
    title="AI Telegram Bot",
    description="AI-ассистент с webhook-интеграцией Telegram",
    lifespan=lifespan,
)


@fastapi_app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """
    Endpoint для приёма обновлений от Telegram.
    Telegram шлёт сюда POST-запрос при каждом новом сообщении.
    """
    # Проверка секретного токена (Telegram шлёт его в заголовке X-Telegram-Bot-Api-Secret-Token)
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret and secret != WEBHOOK_SECRET:
        return {"detail": "Unauthorized"}, status.HTTP_401_UNAUTHORIZED
    
    # Разбираем JSON и преобразуем в Update
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    
    # Отправляем в обработчики PTB
    await ptb_app.process_update(update)
    
    return {"ok": True}


@fastapi_app.get("/health")
async def health_check():
    """
    Health check для Render / балансировщиков / мониторинга.
    Render использует этот endpoint для проверки, что сервер жив.
    """
    return {
        "status": "ok",
        "service": "kimi-telegram-bot",
        "webhook": WEBHOOK_URL,
    }


@fastapi_app.get("/")
async def root():
    """Корневой endpoint — просто информация о боте."""
    return {
        "message": "AI Telegram Bot is running",
        "docs": "/docs",
        "health": "/health",
        "webhook_url": WEBHOOK_URL,
    }
