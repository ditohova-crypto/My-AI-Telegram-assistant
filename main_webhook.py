"""
Webhook-версия бота для Render
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update

# Импорты из наших файлов
from config import TELEGRAM_BOT_TOKEN, validate_config
from database import init_db

# === НАСТРОЙКИ ===
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")
RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")

if RENDER_HOST:
    WEBHOOK_URL = f"https://{RENDER_HOST}/telegram-webhook"
else:
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

logger = logging.getLogger(__name__)

# PTB приложение (ленивая загрузка)
_ptb_app = None

def _get_bot_app():
    global _ptb_app
    if _ptb_app is None:
        # Ленивый импорт чтобы не пада при старте
        import bot
        _ptb_app = bot.create_application()
    return _ptb_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл FastAPI"""
    logger.info("=== Старт ===")
    
    ptb = _get_bot_app()
    await ptb.initialize()
    await ptb.start()
    
    # Webhook
    if WEBHOOK_URL:
        try:
            await ptb.bot.set_webhook(
                url=WEBHOOK_URL,
                secret_token=WEBHOOK_SECRET,
                allowed_updates=Update.ALL_TYPES,
            )
            logger.info("Webhook: %s", WEBHOOK_URL)
        except Exception as e:
            logger.warning("Webhook авто: %s", e)
    
    yield
    
    logger.info("=== Стоп ===")
    await ptb.stop()
    await ptb.shutdown()
    await ptb.bot.delete_webhook(drop_pending_updates=True)


# === FASTAPI ===
fastapi_app = FastAPI(title="AI Bot", lifespan=lifespan)


@fastapi_app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """Принимаем сообщения от Telegram"""
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret and secret != WEBHOOK_SECRET:
        return {"detail": "Unauthorized"}
    
    data = await request.json()
    ptb = _get_bot_app()
    update = Update.de_json(data, ptb.bot)
    await ptb.process_update(update)
    return {"ok": True}


@fastapi_app.get("/health")
async def health():
    return {"status": "ok", "webhook": WEBHOOK_URL or "not set"}


@fastapi_app.get("/")
async def root():
    return {"message": "AI Bot running", "health": "/health"}
