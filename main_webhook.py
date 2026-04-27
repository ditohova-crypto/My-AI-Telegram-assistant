"""
Webhook для Render.com — ленивая инициализация.
"""
import os
import logging
import sys

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
WEBHOOK_URL = f"https://{RENDER_HOST}{WEBHOOK_PATH}" if RENDER_HOST else os.getenv("WEBHOOK_URL", "")

logger.info("RENDER_HOST=%s WEBHOOK_URL=%s", RENDER_HOST, WEBHOOK_URL)

_ptb_app = None
_ptb_initialized = False

async def _lazy_get_bot():
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

fastapi_app = FastAPI()

@fastapi_app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        logger.info("WEBHOOK: update_id=%s", data.get("update_id", "?"))
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
    return {"message": "AI Bot", "health": "/health", "webhook": WEBHOOK_PATH}

@fastapi_app.get("/setup-webhook")
async def setup_webhook_manual():
    if not WEBHOOK_URL:
        return {"ok": False, "error": "WEBHOOK_URL не определён."}
    try:
        ptb = await _lazy_get_bot()
        await ptb.bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET, allowed_updates=Update.ALL_TYPES)
        return {"ok": True, "message": "Webhook установлен!"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# === Диагностика диска ===
@fastapi_app.get("/debug")
async def debug_db():
    from config import DB_PATH
    from pathlib import Path
    import sqlite3
    result = {
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "db_size": 0,
        "folder_exists": DB_PATH.parent.exists(),
        "folder_writable": False,
        "messages": 0,
        "users": 0,
        "reminders": 0,
        "error": None
    }
    try:
        test = DB_PATH.parent / ".write_test"
        test.write_text("ok")
        test.unlink()
        result["folder_writable"] = True
    except Exception as e:
        result["folder_writable"] = str(e)
    if DB_PATH.exists():
        result["db_size"] = DB_PATH.stat().st_size
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM chat_history")
            result["messages"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users")
            result["users"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM reminders")
            result["reminders"] = cur.fetchone()[0]
            conn.close()
        except Exception as e:
            result["error"] = str(e)
    return result

logger.info("=== FastAPI готов ===")
