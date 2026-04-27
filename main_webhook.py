"""
Webhook-версия бота для Render
"""
import os
import logging
import sys

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Импортируем наши модули
sys.path.insert(0, os.path.dirname(__file__))
import config
import database
import bot

logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")
RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")

if RENDER_HOST:
    WEBHOOK_URL = f"https://{RENDER_HOST}/telegram-webhook"
else:
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

_ptb_app = None

def get_ptb_app():
    global _ptb_app
    if _ptb_app is None:
        _ptb_app = bot.create_application()
    return _ptb_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Старт ===")
    ptb = get_ptb_app()
    await ptb.initialize()
    await ptb.start()
    
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

# === FASTAPI ===
fastapi_app = FastAPI(title="AI Bot", lifespan=lifespan)

@fastapi_app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """Принимаем сообщения от Telegram"""
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret and secret != WEBHOOK_SECRET:
        return {"detail": "Unauthorized"}, status.HTTP_401_UNAUTHORIZED
    
    try:
        data = await request.json()
        ptb = get_ptb_app()
        update = Update.de_json(data, ptb.bot)
        await ptb.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error("Webhook error: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}

@fastapi_app.get("/health")
async def health():
    return {"status": "ok", "webhook": WEBHOOK_URL or "not set"}

@fastapi_app.get("/")
async def root():
    return {"message": "AI Bot running", "health": "/health", "setup": "/setup-webhook"}

@fastapi_app.get("/setup-webhook")
async def setup_webhook_manual():
    if not WEBHOOK_URL:
        return {"ok": False, "error": "WEBHOOK_URL not set"}
    try:
        ptb = get_ptb_app()
        await ptb.bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET, allowed_updates=Update.ALL_TYPES)
        return {"ok": True, "message": "Webhook set", "url": WEBHOOK_URL}
    except Exception as e:
        return {"ok": False, "error": str(e)}
