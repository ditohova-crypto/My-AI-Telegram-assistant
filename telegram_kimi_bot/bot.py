"""
Telegram-бот: AI-ассистент с сохранением истории диалога.
Поддерживает любой OpenAI-compatible API (Groq, OpenRouter, OpenAI, и др.)
"""
import asyncio
import logging
import sys
import traceback
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
