"""
Webhook-версия бота для облачных платформ (Render, Railway, AWS, etc.)
Использует FastAPI + python-telegram-bot для обработки webhook от Telegram.
"""
import os
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from telegram import Update

# Ленивая загрузка bot — не импортируем create_application сразу
# чтобы при ошибках конфигурации приложение не падало при импорте модуля
_bot_module = None
_ptb_app = None
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ WEBHOOK ===
WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-in-render-env")

# Render предоставляет внешний хост в переменной RENDER_EXTERNAL_HOSTNAME
RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if RENDER_HOST:
    WEBHOOK_URL = f"https://{RENDER_HOST}{WEBHOOK_PATH}"
else:
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")


def _get_bot_app():
    """Ленивая инициализация PTB-приложения."""
    global _bot_module, _ptb_app
    if _ptb_app is None:
        import bot as _bot_module
        _ptb_app = _bot_module.create_application()
    return _ptb_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Жизненный цикл FastAPI:
    - При старте: инициализируем PTB, пробуем установить webhook
    - При остановке: останавливаем PTB
    """
    logger.info("=== Старт приложения ===")
    
    # Инициализация PTB
    try:
        ptb = _get_bot_app()
        await ptb.initialize()
        await ptb.start()
        logger.info("PTB приложение запущено.")
    except Exception as e:
        logger.error("Ошибка запуска PTB: %s", e, exc_info=True)
        raise
    
    # Установка webhook (если URL известен)
    if WEBHOOK_URL:
        try:
            await ptb.bot.set_webhook(
                url=WEBHOOK_URL,
                secret_token=WEBHOOK_SECRET,
                allowed_updates=Update.ALL_TYPES,
            )
            logger.info("Webhook установлен: %s", WEBHOOK_URL)
        except Exception as e:
            logger.warning("Не удалось установить webhook автоматически: %s", e)
            logger.info("Используйте /setup-webhook или установите вручную через Telegram API")
    else:
        logger.warning(
            "WEBHOOK_URL не определён. Рендер-хост неизвестен. "
            "Перейдите на /setup-webhook после деплоя."
        )
    
    yield
    
    logger.info("=== Остановка приложения ===")
    try:
        await ptb.stop()
        await ptb.shutdown()
        await ptb.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook удалён. PTB остановлен.")
    except Exception as e:
        logger.error("Ошибка при остановке: %s", e, exc_info=True)


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
    """
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret and secret != WEBHOOK_SECRET:
        return {"detail": "Unauthorized"}, status.HTTP_401_UNAUTHORIZED
    
    data = await request.json()
    ptb = _get_bot_app()
    update = Update.de_json(data, ptb.bot)
    await ptb.process_update(update)
    
    return {"ok": True}


@fastapi_app.get("/health")
async def health_check():
    """Health check для Render / балансировщиков."""
    return {
        "status": "ok",
        "service": "ai-telegram-bot",
        "webhook_url": WEBHOOK_URL or "not configured",
    }


@fastapi_app.get("/")
async def root():
    """Корневой endpoint — информация о боте."""
    return {
        "message": "AI Telegram Bot is running",
        "docs": "/docs",
        "health": "/health",
        "setup_webhook": "/setup-webhook",
        "webhook_url": WEBHOOK_URL or "not configured",
    }


@fastapi_app.get("/setup-webhook")
async def setup_webhook_manual():
    """
    Ручная установка webhook (если автоматическая не сработала).
    Просто откройте этот URL в браузере после деплоя.
    """
    if not WEBHOOK_URL:
        return {
            "ok": False,
            "error": "WEBHOOK_URL не определён. "
                     "Проверьте переменную окружения RENDER_EXTERNAL_HOSTNAME или WEBHOOK_URL."
        }
    
    try:
        ptb = _get_bot_app()
        await ptb.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=Update.ALL_TYPES,
        )
        return {
            "ok": True,
            "message": "Webhook установлен!",
            "webhook_url": WEBHOOK_URL,
            "next_step": "Напишите боту в Telegram /start",
        }
    except Exception as e:
        logger.error("Ошибка ручной установки webhook: %s", e, exc_info=True)
        return {
            "ok": False,
            "error": str(e),
        }
