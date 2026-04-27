"""
Webhook для Render.com — ленивая инициализация, гарантированный старт.
"""
import os
import logging
import sys

# Логирование первым делом
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

logger.info("=== main_webhook.py ЗАГРУЖЕН ===")

from fastapi import FastAPI, Request, status
from telegram import Update

WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-in-render-env")

RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOST:
    WEBHOOK_URL = f"https://{RENDER_HOST}{WEBHOOK_PATH}"
else:
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

logger.info("RENDER_HOST=%s", RENDER_HOST)
logger.info("WEBHOOK_URL=%s", WEBHOOK_URL)

_ptb_app = None
_ptb_initialized = False

async def _lazy_get_bot():
    """Ленивая инициализация бота — только при первом запросе."""
    global _ptb_app, _ptb_initialized
    if _ptb_app is None:
        logger.info("LAZY: import bot...")
        import bot as bot_module
        logger.info("LAZY: create_application()...")
        _ptb_app = bot_module.create_application()
        logger.info("LAZY: app создан")
    if not _ptb_initialized:
        logger.info("LAZY: initialize()...")
        await _ptb_app.initialize()
        logger.info("LAZY: start()...")
        await _ptb_app.start()
        _ptb_initialized = True
        logger.info("LAZY: БОТ ГОТОВ")
    return _ptb_app

# FastAPI приложение — тут точно ничего не падает при старте
fastapi_app = FastAPI()

@fastapi_app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update_id = data.get("update_id", "?")
        logger.info("WEBHOOK: update_id=%s", update_id)
        ptb = await _lazy_get_bot()
        update = Update.de_json(data, ptb.bot)
        await ptb.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error("WEBHOOK ERROR: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}

@fastapi_app.get("/health")
async def health_check():
    return {"status": "ok", "webhook_url": WEBHOOK_URL or "not configured"}

@fastapi_app.get("/")
async def root():
    return {
        "message": "AI Bot webhook server",
        "health": "/health",
        "webhook": WEBHOOK_PATH,
        "status": "running"
    }

@fastapi_app.get("/setup-webhook")
async def setup_webhook_manual():
    if not WEBHOOK_URL:
        return {"ok": False, "error": "WEBHOOK_URL не определён."}
    try:
        ptb = await _lazy_get_bot()
        await ptb.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=Update.ALL_TYPES
        )
        return {"ok": True, "message": "Webhook установлен!"}
    except Exception as e:
        logger.error("Setup webhook error: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}

logger.info("=== FastAPI app создан, старт готов ===")
