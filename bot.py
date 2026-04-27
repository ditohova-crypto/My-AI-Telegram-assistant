"""
Telegram-бот: AI-ассистент с сохранением истории диалога.
Поддерживает любой OpenAI-compatible API (Groq, OpenRouter, OpenAI, и др.)
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

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# === КЛИЕНТ AI ===
client: Optional[AsyncOpenAI] = None


def init_openai_client() -> None:
    """Инициализирует клиент OpenAI для работы с выбранным AI API."""
    global client
    client = AsyncOpenAI(
        api_key=AI_API_KEY,
        base_url=AI_BASE_URL,
    )
    logger.info("AI клиент инициализирован | base_url=%s | model=%s", AI_BASE_URL, AI_MODEL)


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMIN_USER_IDS


def split_long_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Разбивает длинное сообщение на части, стараясь не резать посреди слов."""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        
        # Ищем последний перенос строки или пробел в пределах лимита
        cut_at = text.rfind('\n', 0, max_length)
        if cut_at == -1:
            cut_at = text.rfind(' ', 0, max_length)
        if cut_at == -1:
            cut_at = max_length  # Аварийный вариант — ровно по лимиту
        
        parts.append(text[:cut_at])
        text = text[cut_at:].lstrip()
    
    return parts


# === ОБРАБОТЧИКИ КОМАНД ===

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start — приветствие нового пользователя."""
    user = update.effective_user
    logger.info("Новый пользователь: id=%s, username=%s, name=%s", user.id, user.username, user.full_name)
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я — AI-ассистент с поддержкой контекста и долгой памяти.\n"
        f"Я умею:\n"
        f"• Отвечать на вопросы и помогать с задачами\n"
        f"• Помнить контекст разговора\n"
        f"• Работать с длинными текстами\n\n"
        f"📌 **Доступные команды:**\n"
        f"/start — запуск бота\n"
        f"/clear — очистить историю диалога\n"
        f"/newtopic — начать новую тему (аналог /clear)\n"
        f"/status — моя статистика использования\n"
        f"/help — справка\n\n"
        f"Просто напишите мне — и я постараюсь помочь! 🤖"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help — справка."""
    help_text = (
        "📖 **Справка по боту**\n\n"
        "Это AI-ассистент с памятью контекста и поддержкой длинных диалогов.\n\n"
        "**Основные команды:**\n"
        "• /start — начать работу с ботом\n"
        "• /clear или /newtopic — очистить историю текущего разговора\n"
        "• /status — посмотреть статистику (количество сообщений)\n"
        "• /help — показать эту справку\n\n"
        "**Как пользоваться:**\n"
        "Просто отправляйте текстовые сообщения. Бот помнит контекст, поэтому можно вести разговор в несколько шагов.\n\n"
        "**Советы:**\n"
        "• Используйте /clear, если бот начал путать контекст\n"
        "• Для сложных тем формулируйте вопросы конкретнее\n"
        "• Бот поддерживает Markdown-разметку в ответах\n\n"
        "**Техническая поддержка:**\n"
        "Если бот не отвечает или ошибается — напишите @ваш_тг (или проверьте статус API)."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /clear — очистка истории диалога."""
    user_id = update.effective_user.id
    deleted = clear_user_history(user_id)
    
    msg = "🧹 История диалога очищена! Можем начать с чистого листа."
    if deleted > 0:
        msg += f"\n(Удалено сообщений: {deleted})"
    
    logger.info("Пользователь %s очистил историю, удалено: %d", user_id, deleted)
    await update.message.reply_text(msg)


async def newtopic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /newtopic — алиас для /clear."""
    await clear_command(update, context)
    await update.message.reply_text("✨ Начинаем новую тему!")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /status — статистика пользователя."""
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
    if stats:
        text = (
            f"📊 **Ваша статистика:**\n\n"
            f"• Сообщений отправлено: *{stats['message_count']}*\n"
            f"• Токенов использовано: *{stats['total_tokens_used']}*\n"
            f"• Первое обращение: `{stats['created_at']}`\n"
            f"• Последняя активность: `{stats['last_active']}`\n\n"
            f"Модель: `{AI_MODEL}`"
        )
    else:
        text = (
            "📊 Пока нет статистики — вы только начали пользоваться ботом!\n\n"
            f"Модель: `{AI_MODEL}`"
        )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# === АДМИН-КОМАНДЫ ===

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ-команда /admin_stats — общая статистика бота."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав для этой команды.")
        return
    
    total_users = get_all_users_count()
    await update.message.reply_text(
        f"🔐 **Админ-панель**\n\n"
        f"• Всего пользователей: *{total_users}*\n"
        f"• Модель: `{AI_MODEL}`\n"
        f"• API URL: `{AI_BASE_URL}`",
        parse_mode=ParseMode.MARKDOWN
    )


async def admin_cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ-команда /admin_cleanup — очистка старой истории."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав для этой команды.")
        return
    
    days = 30
    if context.args and context.args[0].isdigit():
        days = int(context.args[0])
    
    deleted = cleanup_old_history(days)
    await update.message.reply_text(
        f"🗑️ Очистка выполнена.\nУдалено сообщений старше {days} дней: *{deleted}*",
        parse_mode=ParseMode.MARKDOWN
    )


# === НАПОМИНАНИЯ И БРИФ ===

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /remind ЧЧ:ММ Текст напоминания
    Пример: /remind 14:30 Позвонить маме
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⏰ Использование: `/remind ЧЧ:ММ Текст напоминания`\n"
            "Пример: `/remind 14:30 Позвонить маме`\n"
            "Доступно время в формате 24ч (например 09:00, 23:45)",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    time_str = context.args[0]
    text = " ".join(context.args[1:])
    
    try:
        hour, minute = map(int, time_str.split(":"))
        now = datetime.now()
        remind_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Если время уже прошло сегодня — на завтра
        if remind_at <= now:
            remind_at += timedelta(days=1)
        
        reminder_id = add_reminder(user_id, chat_id, text, remind_at)
        
        if reminder_id > 0:
            await update.message.reply_text(
                f"✅ Напоминание установлено!\n"
                f"📅 Когда: *{remind_at.strftime('%d.%m.%Y %H:%M')}*\n"
                f"📝 Что: {text}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ Ошибка при создании напоминания.")
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат времени. Используйте `ЧЧ:ММ` (например `14:30`)."
        )


async def list_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает активные напоминания пользователя."""
    user_id = update.effective_user.id
    reminders = get_user_reminders(user_id)
    
    if not reminders:
        await update.message.reply_text("📭 У вас нет активных напоминаний.")
        return
    
    text = "📋 *Ваши напоминания:*\n\n"
    for r in reminders:
        dt = datetime.fromisoformat(r["remind_at"])
        text += f"`{r['id']}` • {dt.strftime('%d.%m %H:%M')} — {r['text']}\n"
    
    text += "\nОтменить: `/cancelreminder ID`"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cancel_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cancelreminder ID — отменяет напоминание."""
    user_id = update.effective_user.id
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Укажите ID напоминания: `/cancelreminder 1`")
        return
    
    reminder_id = int(context.args[0])
    if cancel_reminder(user_id, reminder_id):
        await update.message.reply_text("✅ Напоминание отменено.")
    else:
        await update.message.reply_text("❌ Напоминание не найдено или уже отправлено.")


async def set_brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /setbrief ВКЛ/ВЫКЛ [ВРЕМЯ]
    Примеры:
      /setbrief вкл 09:00
      /setbrief выкл
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not context.args:
        settings = get_user_brief_settings(user_id)
        if settings and settings["is_enabled"]:
            time_str = settings["brief_time"]
            status = "✅ Включён"
        else:
            time_str = "09:00"
            status = "❌ Выключен"
        
        await update.message.reply_text(
            f"📰 *Ежедневный бриф*\n"
            f"Статус: {status}\n"
            f"Время: `{time_str}`\n\n"
            f"Команды:\n"
            f"`/setbrief вкл 09:00` — включить\n"
            f"`/setbrief выкл` — выключить\n"
            f"`/brief` — получить бриф сейчас",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    arg = context.args[0].lower()
    time_str = "09:00"
    
    if len(context.args) >= 2:
        time_str = context.args[1]
    
    if arg in ("вкл", "on", "1", "true", "yes"):
        set_daily_brief(user_id, chat_id, True, time_str)
        await update.message.reply_text(
            f"📰 *Ежедневный бриф включён!*\n"
            f"⏰ Время отправки: `{time_str}`\n"
            f"Каждое утро я буду присылать сводку ваших дел и планов.",
            parse_mode=ParseMode.MARKDOWN
        )
    elif arg in ("выкл", "off", "0", "false", "no"):
        set_daily_brief(user_id, chat_id, False, time_str)
        await update.message.reply_text("📰 Ежедневный бриф выключён.")
    else:
        await update.message.reply_text("❌ Не понял. Используйте: `/setbrief вкл 09:00` или `/setbrief выкл`")


async def brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/brief — получить бриф прямо сейчас."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    
    history = get_full_user_history(user_id, limit=50)
    
    if not history:
        await update.message.reply_text(
            "📭 Пока нет истории для брифа.\n"
            "Пообщайтесь со мной — и утром я соберу сводку!"
        )
        return
    
    # Формируем контекст для AI
    history_text = "\n".join([
        f"[{h['created_at']}] {h['role']}: {h['content'][:200]}"
        for h in history[:30]
    ])
    
    messages = [
        {"role": "system", "content": BRIEF_PROMPT},
        {"role": "user", "content": f"Вот моя история сообщений:\n{history_text}\n\nСоставь утренний бриф."}
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
        logger.error("Ошибка генерации брифа: %s", e, exc_info=True)
        await update.message.reply_text("😔 Не удалось сгенерировать бриф. Попробуйте позже.")


# === ФОНОВЫЕ ЗАДАЧИ (CRON) ===

async def check_and_send_reminders(app: Application) -> None:
    """Проверяет напоминания и отправляет их."""
    now = datetime.now()
    reminders = get_pending_reminders(now)
    
    for r in reminders:
        try:
            text = f"⏰ *Напоминание!*\n\n{r['text']}"
            await app.bot.send_message(chat_id=r["chat_id"], text=text, parse_mode=ParseMode.MARKDOWN)
            mark_reminder_sent(r["id"])
            logger.info("Напоминание отправлено user_id=%s", r["user_id"])
        except Exception as e:
            logger.error("Ошибка отправки напоминания: %s", e, exc_info=True)


async def check_and_send_briefs(app: Application) -> None:
    """Проверяет и отправляет ежедневные брифы."""
    now = datetime.now()
    briefs = get_daily_briefs_due(now)
    
    for b in briefs:
        try:
            user_id = b["user_id"]
            chat_id = b["chat_id"]
            
            history = get_full_user_history(user_id, limit=50)
            if not history:
                continue
            
            history_text = "\n".join([
                f"[{h['created_at']}] {h['role']}: {h['content'][:200]}"
                for h in history[:30]
            ])
            
            messages = [
                {"role": "system", "content": BRIEF_PROMPT},
                {"role": "user", "content": f"История:\n{history_text}\n\nСоставь бриф."}
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
                text=f"📰 *Утренний бриф*\n\n{brief}",
                parse_mode=ParseMode.MARKDOWN
            )
            mark_brief_sent(user_id)
            logger.info("Бриф отправлен user_id=%s", user_id)
        except Exception as e:
            logger.error("Ошибка отправки брифа: %s", e, exc_info=True)


# === ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ===

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает входящие текстовые сообщения и отправляет их в AI API."""
    if not update.message or not update.message.text:
        return
    
    user = update.effective_user
    user_message = update.message.text.strip()
    user_id = user.id
    
    # Логируем входящее сообщение
    logger.info("Сообщение от id=%s (@%s): %s...", user_id, user.username, user_message[:50])
    
    # Сохраняем сообщение пользователя
    save_message(user_id, "user", user_message)
    
    # Показываем индикатор "печатает..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        # Получаем историю диалога
        history = get_user_history(user_id)
        
        # Формируем сообщения для API
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        
        # Отправляем запрос к Moonshot AI
        logger.debug("Запрос к API: %d сообщений (включая системное)", len(messages))
        
        response = await client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS,
        )
        
        # Извлекаем ответ
        assistant_message = response.choices[0].message.content.strip()
        usage = response.usage
        
        # Сохраняем ответ ассистента
        save_message(user_id, "assistant", assistant_message)
        
        # Обновляем статистику пользователя
        tokens_used = usage.total_tokens if usage else 0
        update_user_info(
            user_id=user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            tokens_used=tokens_used
        )
        
        logger.info("Ответ API для id=%s | токенов: %s | длина: %d", user_id, tokens_used, len(assistant_message))
        
        # Отправляем ответ пользователю (с разбивкой если нужно)
        parts = split_long_message(assistant_message)
        for idx, part in enumerate(parts):
            if idx > 0:
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id, action=ChatAction.TYPING
                )
                await asyncio.sleep(0.5)
            
            await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN)
    
    except RateLimitError:
        logger.warning("Превышен лимит запросов к API для user_id=%s", user_id)
        await update.message.reply_text(
            "⚠️ Слишком много запросов. Пожалуйста, подождите несколько секунд и попробуйте снова."
        )
    
    except APIError as e:
        logger.error("Ошибка AI API: %s", e, exc_info=True)
        error_msg = str(e)
        if "insufficient_quota" in error_msg or "billing" in error_msg.lower() or "credit" in error_msg.lower():
            await update.message.reply_text(
                "💳 Ошибка API: закончился баланс или квота. Пожалуйста, пополните счёт или смените API-ключ в настройках бота."
            )
        elif "invalid_api_key" in error_msg.lower():
            await update.message.reply_text(
                "🔑 Ошибка API: неверный API-ключ. Проверьте настройки AI_API_KEY в панели управления ботом."
            )
        else:
            await update.message.reply_text(
                f"⚠️ Ошибка при обработке запроса к AI.\nПопробуйте повторить позже.\n\n`{error_msg[:200]}`",
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as e:
        logger.error("Непредвиденная ошибка: %s", e, exc_info=True)
        await update.message.reply_text(
            "😔 Произошла непредвиденная ошибка. Мы уже работаем над её устранением.\n"
            "Попробуйте повторить запрос через минуту."
        )


# === ОБРАБОТКА ОШИБОК ===

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик ошибок Telegram."""
    logger.error("Обработка ошибки Telegram: %s", context.error, exc_info=context.error)
    
    if isinstance(update, Update) and update.effective_message:
        error_msg = "😔 Произошла техническая ошибка. Попробуйте ещё раз позже."
        try:
            await update.effective_message.reply_text(error_msg)
        except Exception:
            pass


# === ЗАПУСК БОТА ===

async def post_init(application: Application) -> None:
    """Действия после инициализации бота."""
    logger.info("Бот инициализирован. Запуск polling...")


def create_application() -> Application:
    """Создаёт и настраивает Application Telegram без запуска."""
    logger.info("=== Создание AI Telegram Bot ===")
    
    # Проверка конфигурации
    try:
        validate_config()
    except ValueError as e:
        logger.error("Ошибка конфигурации:\n%s", e)
        raise RuntimeError(f"Конфигурация неверна: {e}") from e
    
    # Инициализация базы данных
    init_db()
    
    # Инициализация клиента AI
    init_openai_client()
    
    # Создание приложения Telegram
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("newtopic", newtopic_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Админ-команды
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(CommandHandler("admin_cleanup", admin_cleanup_command))
    
    # Напоминания
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("listreminders", list_reminders_command))
    application.add_handler(CommandHandler("cancelreminder", cancel_reminder_command))
    
    # Ежедневный бриф
    application.add_handler(CommandHandler("setbrief", set_brief_command))
    application.add_handler(CommandHandler("brief", brief_command))
    
    # Обработка текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)
    
    return application


def main() -> None:
    """Главная точка входа для локального запуска (polling)."""
    application = create_application()
    
    # Запуск бота в режиме polling
    logger.info("Запуск polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
