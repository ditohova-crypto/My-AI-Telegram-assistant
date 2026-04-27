"""
Webhook-версия бота для облачных платформ (Render, Railway, AWS, etc.)
FastAPI + python-telegram-bot + APScheduler для фоновых задач (напоминания, брифы)
"""
import os
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from telegram import Update
from apscheduler.schedulers.asyncio import AsyncIOScheduler

_bot_module = None
_ptb_app = None
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-in-render-env")

RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOST:
    WEBHOOK_URL = f"https://{RENDER_HOST}{WEBHOOK_PATH}"
else:
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")


def _get_bot_app():
    global _bot_module, _ptb_app
    if _ptb_app is None:
        import bot as _bot_module
        _ptb_app = _bot_module.create_application()
    return _ptb_app


async def _check_reminders_job():
    try:
        import bot as _bot
        ptb = _get_bot_app()
        await _bot.check_and_send_reminders(ptb)
    except Exception as e:
        logger.error("Ошибка напоминаний: %s", e)


async def _check_briefs_job():
    try:
        import bot as _bot
        ptb = _get_bot_app()
        await _bot.check_and_send_briefs(ptb)
    except Exception as e:
        logger.error("Ошибка брифов: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Старт приложения ===")
    
    ptb = _get_bot_app()
    await ptb.initialize()
    await ptb.start()
    logger.info("PTB запущен.")
    
    if WEBHOOK_URL:
        try:
            await ptb.bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET, allowed_updates=Update.ALL_TYPES)
            logger.info("Webhook установлен: %s", WEBHOOK_URL)
        except Exception as e:
            logger.warning("Webhook авто: %s", e)
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_check_reminders_job, "cron", minute="*", id="reminders", replace_existing=True)
    scheduler.add_job(_check_briefs_job, "cron", minute="0,10,20,30,40,50", id="briefs", replace_existing=True)
    scheduler.start()
    logger.info("Планировщик запущен.")
    
    yield
    
    logger.info("=== Остановка ===")
    scheduler.shutdown(wait=False)
    try:
        await ptb.stop()
        await ptb.shutdown()
        await ptb.bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass


fastapi_app = FastAPI(title="AI Telegram Bot", lifespan=lifespan)


@fastapi_app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
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
    return {"status": "ok", "webhook_url": WEBHOOK_URL or "not configured"}


@fastapi_app.get("/")
async def root():
    return {"message": "AI Bot with reminders & briefs", "health": "/health", "setup_webhook": "/setup-webhook"}


@fastapi_app.get("/setup-webhook")
async def setup_webhook_manual():
    if not WEBHOOK_URL:
        return {"ok": False, "error": "WEBHOOK_URL не определён."}
    try:
        ptb = _get_bot_app()
        await ptb.bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET, allowed_updates=Update.ALL_TYPES)
        return {"ok": True, "message": "Webhook установлен!"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
