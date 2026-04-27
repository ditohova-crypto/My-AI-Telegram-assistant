"""
Webhook-версия для Render.com
"""
import os
import logging
import sys
from contextlib import asynccontextmanager

# Настройка логирования ДО всех импортов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Ленивые импорты — только когда нужно
_ptb_app = None

WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-in-render-env")

RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOST:
    WEBHOOK_URL = f"https://{RENDER_HOST}{WEBHOOK_PATH}"
else:
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

logger.info("ENV: RENDER_HOST=%s, WEBHOOK_URL=%s", RENDER_HOST, WEBHOOK_URL)


def _get_bot_app():
    """Ленивая инициализация PTB приложения."""
    global _ptb_app
    if _ptb_app is None:
        logger.info("Инициализация bot.py...")
        import bot as bot_module
        _ptb_app = bot_module.create_application()
        logger.info("bot.py инициализирован.")
    return _ptb_app


# === APScheduler для напоминаний и брифов ===
async def _check_reminders_job():
    try:
        import bot as bot_module
        ptb = _get_bot_app()
        await bot_module.check_and_send_reminders(ptb)
    except Exception as e:
        logger.error("Ошибка напоминаний: %s", e)


async def _check_briefs_job():
    try:
        import bot as bot_module
        ptb = _get_bot_app()
        await bot_module.check_and_send_briefs(ptb)
    except Exception as e:
        logger.error("Ошибка брифов: %s", e)


# === Lifespan: старт/стоп приложения ===
@asynccontextmanager
async def lifespan(app):
    logger.info("=== СТАРТ приложения ===")
    
    # Инициализация PTB
    ptb = _get_bot_app()
    await ptb.initialize()
    await ptb.start()
    logger.info("PTB запущен.")
    
    # Установка webhook
    if WEBHOOK_URL:
        try:
            from telegram import Update
            await ptb.bot.set_webhook(
                url=WEBHOOK_URL,
                secret_token=WEBHOOK_SECRET,
                allowed_updates=Update.ALL_TYPES
            )
            logger.info("Webhook установлен: %s", WEBHOOK_URL)
        except Exception as e:
            logger.warning("Webhook авто: %s", e)
    
    # APScheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_check_reminders_job, "cron", minute="*", id="reminders", replace_existing=True)
    scheduler.add_job(_check_briefs_job, "cron", minute="0,10,20,30,40,50", id="briefs", replace_existing=True)
    scheduler.start()
    logger.info("Планировщик запущен.")
    
    yield
    
    # Остановка
    logger.info("=== ОСТАНОВКА ===")
    scheduler.shutdown(wait=False)
    try:
        await ptb.stop()
        await ptb.shutdown()
        await ptb.bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass


# === FastAPI приложение ===
from fastapi import FastAPI, Request, status
from telegram import Update

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
    return {
        "message": "AI Bot",
        "health": "/health",
        "setup_webhook": "/setup-webhook",
        "webhook_path": WEBHOOK_PATH
    }


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
