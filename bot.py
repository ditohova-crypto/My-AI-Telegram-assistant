"""
Telegram-бот: AI-ассистент с сохранением истории диалога.
"""
import asyncio
import logging
import sys
import traceback
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from openai import AsyncOpenAI, APIError, RateLimitError

from config import (
    TELEGRAM_BOT_TOKEN,
    AI_API_KEY,
    AI_BASE_URL,
    AI_MODEL,
    AI_TEMPERATURE,
    AI_MAX_TOKENS,
    MAX_MESSAGE_LENGTH,
    ADMIN_USER_IDS,
    SYSTEM_PROMPT,
    BRIEF_PROMPT,
    LOGS_DIR,
    validate_config,
)
from database import (
    init_db,
    save_message,
    get_user_history,
    clear_user_history,
    update_user_info,
    get_user_stats,
    get_all_users_count,
    cleanup_old_history,
    add_reminder,
    get_pending_reminders,
    mark_reminder_sent,
    get_user_reminders,
    cancel_reminder,
    set_daily_brief,
    get_daily_briefs_due,
    mark_brief_sent,
    get_user_brief_settings,
    get_full_user_history,
)

# === НАСТРОЙКА ЛОГИРОВАНИЯ (безопасная для Render) ===
handlers = [logging.StreamHandler(sys.stdout)]
try:
    LOGS_DIR.mkdir(exist_ok=True)
    handlers.append(logging.FileHandler(LOGS_DIR / "bot.log", encoding="utf-8"))
except OSError:
    pass  # На Render может не быть прав на запись в BASE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=handlers,
)
logger = logging.getLogger(__name__)

# === КЛИЕНТ AI ===
client: Optional[AsyncOpenAI] = None

def init_openai_client() -> None:
    global client
    client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)
    logger.info("AI клиент инициализирован | base_url=%s | model=%s", AI_BASE_URL, AI_MODEL)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

def split_long_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    if len(text) <= max_length:
        return [text]
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        cut_at = text.rfind('\\n', 0, max_length)
        if cut_at == -1:
            cut_at = text.rfind(' ', 0, max_length)
        if cut_at == -1:
            cut_at = max_length
        parts.append(text[:cut_at])
        text = text[cut_at:].lstrip()
    return parts

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_text = (
        f"👋 Привет, {user.first_name}!\\n\\n"
        f"Я — AI-ассистент с долгой памятью.\\n"
        f"• Отвечаю на вопросы\\n"
        f"• Помню контекст разговора\\n"
        f"• Умею напоминания и утренние брифы\\n\\n"
        f"📌 **Команды:**\\n"
        f"/start — запуск\\n"
        f"/clear — очистить историю\\n"
        f"/remind 14:30 Позвонить маме\\n"
        f"/listreminders — мои напоминания\\n"
        f"/setbrief вкл 09:00 — утренний бриф\\n"
        f"/brief — бриф сейчас\\n"
        f"/status — статистика\\n"
        f"/help — справка"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "📖 **Справка**\\n\\n"
        "**Команды:**\\n"
        "• /start — начать\\n"
        "• /clear или /newtopic — очистить историю\\n"
        "• /status — статистика\\n"
        "• /remind ЧЧ:ММ Текст — напоминание\\n"
        "• /listreminders — список напоминаний\\n"
        "• /cancelreminder ID — отменить\\n"
        "• /setbrief вкл 09:00 — ежедневный бриф\\n"
        "• /brief — получить бриф сейчас\\n"
        "• /help — справка\\n\\n"
        "Просто пишите — я помню контекст!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    deleted = clear_user_history(user_id)
    msg = "🧹 История очищена!"
    if deleted > 0:
        msg += f"\\n(Удалено: {deleted})"
    await update.message.reply_text(msg)

async def newtopic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await clear_command(update, context)
    await update.message.reply_text("✨ Новая тема!")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    if stats:
        text = (
            f"📊 **Статистика:**\\n\\n"
            f"• Сообщений: *{stats['message_count']}*\\n"
            f"• Токенов: *{stats['total_tokens_used']}*\\n"
            f"• Первое обращение: `{stats['created_at']}`\\n"
            f"• Последняя активность: `{stats['last_active']}`\\n\\n"
            f"Модель: `{AI_MODEL}`"
        )
    else:
        text = "📊 Пока нет статистики.\\n\\nМодель: `" + AI_MODEL + "`"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Нет прав.")
        return
    total_users = get_all_users_count()
    await update.message.reply_text(
        f"🔐 **Админ**\\n• Пользователей: *{total_users}*\\n• Модель: `{AI_MODEL}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def admin_cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Нет прав.")
        return
    days = 30
    if context.args and context.args[0].isdigit():
        days = int(context.args[0])
    deleted = cleanup_old_history(days)
    await update.message.reply_text(
        f"🗑️ Удалено сообщений старше {days} дней: *{deleted}*",
        parse_mode=ParseMode.MARKDOWN
    )

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⏰ `/remind ЧЧ:ММ Текст`\\nПример: `/remind 14:30 Позвонить маме`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    time_str = context.args[0]
    text = " ".join(context.args[1:])
    try:
        hour, minute = map(int, time_str.split(":"))
        now = datetime.now()
        remind_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if remind_at <= now:
            remind_at += timedelta(days=1)
        reminder_id = add_reminder(user_id, chat_id, text, remind_at)
        if reminder_id > 0:
            await update.message.reply_text(
                f"✅ Напоминание!\\n📅 *{remind_at.strftime('%d.%m.%Y %H:%M')}*\\n📝 {text}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ Ошибка.")
    except ValueError:
        await update.message.reply_text("❌ Формат: `ЧЧ:ММ`")

async def list_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    reminders = get_user_reminders(user_id)
    if not reminders:
        await update.message.reply_text("📭 Нет напоминаний.")
        return
    text = "📋 *Напоминания:*\\n\\n"
    for r in reminders:
        dt = datetime.fromisoformat(r["remind_at"])
        text += f"`{r['id']}` • {dt.strftime('%d.%m %H:%M')} — {r['text']}\\n"
    text += "\\nОтменить: `/cancelreminder ID`"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cancel_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ `/cancelreminder ID`")
        return
    reminder_id = int(context.args[0])
    if cancel_reminder(user_id, reminder_id):
        await update.message.reply_text("✅ Отменено.")
    else:
        await update.message.reply_text("❌ Не найдено.")

async def set_brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not context.args:
        settings = get_user_brief_settings(user_id)
        status = "✅ Включён" if settings and settings["is_enabled"] else "❌ Выключен"
        time_str = settings["brief_time"] if settings else "09:00"
        await update.message.reply_text(
            f"📰 *Бриф*\\nСтатус: {status}\\nВремя: `{time_str}`\\n\\n"
            f"`/setbrief вкл 09:00` — включить\\n"
            f"`/setbrief выкл` — выключить\\n"
            f"`/brief` — получить сейчас",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    arg = context.args[0].lower()
    time_str = context.args[1] if len(context.args) >= 2 else "09:00"
    if arg in ("вкл", "on", "1", "true", "yes"):
        set_daily_brief(user_id, chat_id, True, time_str)
        await update.message.reply_text(
            f"📰 *Бриф включён!*\\n⏰ `{time_str}`",
            parse_mode=ParseMode.MARKDOWN
        )
    elif arg in ("выкл", "off", "0", "false", "no"):
        set_daily_brief(user_id, chat_id, False, time_str)
        await update.message.reply_text("📰 Бриф выключён.")
    else:
        await update.message.reply_text("❌ `/setbrief вкл 09:00` или `/setbrief выкл`")

async def brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    history = get_full_user_history(user_id, limit=50)
    if not history:
        await update.message.reply_text("📭 Нет истории для брифа.")
        return
    history_text = "\\n".join([
        f"[{h['created_at']}] {h['role']}: {h['content'][:200]}"
        for h in history[:30]
    ])
    messages = [
        {"role": "system", "content": BRIEF_PROMPT},
        {"role": "user", "content": f"История:\\n{history_text}\\n\\nСоставь бриф."}
    ]
    try:
        response = await client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS,
        )
        brief = response.choices[0].message.content.strip()
        parts = split_long_message(brief)
        for part in parts:
            await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error("Ошибка брифа: %s", e, exc_info=True)
        await update.message.reply_text("😔 Не удалось сгенерировать бриф.")

async def check_and_send_reminders(app: Application) -> None:
    now = datetime.now()
    reminders = get_pending_reminders(now)
    for r in reminders:
        try:
            text = f"⏰ *Напоминание!*\\n\\n{r['text']}"
            await app.bot.send_message(chat_id=r["chat_id"], text=text, parse_mode=ParseMode.MARKDOWN)
            mark_reminder_sent(r["id"])
        except Exception as e:
            logger.error("Ошибка напоминания: %s", e)

async def check_and_send_briefs(app: Application) -> None:
    now = datetime.now()
    briefs = get_daily_briefs_due(now)
    for b in briefs:
        try:
            user_id = b["user_id"]
            chat_id = b["chat_id"]
            history = get_full_user_history(user_id, limit=50)
            if not history:
                continue
            history_text = "\\n".join([
                f"[{h['created_at']}] {h['role']}: {h['content'][:200]}"
                for h in history[:30]
            ])
            messages = [
                {"role": "system", "content": BRIEF_PROMPT},
                {"role": "user", "content": f"История:\\n{history_text}\\n\\nСоставь бриф."}
            ]
            response = await client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS,
            )
            brief = response.choices[0].message.content.strip()
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"📰 *Утренний бриф*\\n\\n{brief}",
                parse_mode=ParseMode.MARKDOWN
            )
            mark_brief_sent(user_id)
        except Exception as e:
            logger.error("Ошибка брифа: %s", e)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    user_message = update.message.text.strip()
    user_id = user.id
    logger.info("Сообщение от id=%s: %s...", user_id, user_message[:50])
    save_message(user_id, "user", user_message)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        history = get_user_history(user_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        response = await client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS,
        )
        assistant_message = response.choices[0].message.content.strip()
        save_message(user_id, "assistant", assistant_message)
        tokens_used = response.usage.total_tokens if response.usage else 0
        update_user_info(
            user_id=user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            tokens_used=tokens_used
        )
        parts = split_long_message(assistant_message)
        for idx, part in enumerate(parts):
            if idx > 0:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
                await asyncio.sleep(0.5)
            await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN)
    except RateLimitError:
        await update.message.reply_text("⚠️ Слишком много запросов. Подождите.")
    except APIError as e:
        error_msg = str(e)
        if "insufficient_quota" in error_msg or "billing" in error_msg.lower() or "credit" in error_msg.lower():
            await update.message.reply_text("💳 Закончился баланс API. Пополните счёт.")
        elif "invalid_api_key" in error_msg.lower():
            await update.message.reply_text("🔑 Неверный API-ключ.")
        else:
            await update.message.reply_text(f"⚠️ Ошибка API.\\n\\n`{error_msg[:200]}`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        await update.message.reply_text("😔 Ошибка. Попробуйте позже.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Ошибка Telegram: %s", context.error, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("😔 Техническая ошибка. Попробуйте позже.")
        except Exception:
            pass

async def post_init(application: Application) -> None:
    logger.info("Бот инициализирован.")

def create_application() -> Application:
    logger.info("=== Создание AI Telegram Bot ===")
    try:
        validate_config()
    except ValueError as e:
        logger.error("Ошибка конфигурации: %s", e)
        raise RuntimeError(f"Конфигурация неверна: {e}") from e
    init_db()
    init_openai_client()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("newtopic", newtopic_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(CommandHandler("admin_cleanup", admin_cleanup_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("listreminders", list_reminders_command))
    application.add_handler(CommandHandler("cancelreminder", cancel_reminder_command))
    application.add_handler(CommandHandler("setbrief", set_brief_command))
    application.add_handler(CommandHandler("brief", brief_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    return application

def main() -> None:
    application = create_application()
    logger.info("Запуск polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
