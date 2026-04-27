"""
Модуль поиска в интернете через Brave Search API.
Бесплатный tier: 2000 запросов/месяц.
Регистрация: https://api.search.brave.com
"""
import logging
import requests
from config import BRAVE_API_KEY

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def search_web(query: str, count: int = 5) -> str:
    """
    Выполняет поиск в интернете через Brave Search API.
    Возвращает отформатированный текст с результатами.
    """
    if not BRAVE_API_KEY or BRAVE_API_KEY == "your-brave-api-key":
        logger.warning("Brave API ключ не настроен. Поиск недоступен.")
        return "🔍 Поиск в интернете не настроен. Получите ключ на api.search.brave.com"
    
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": count,
        "offset": 0,
        "mkt": "ru",
        "safesearch": "moderate",
    }
    
    try:
        resp = requests.get(BRAVE_SEARCH_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        results = data.get("web", {}).get("results", [])
        if not results:
            return "🔍 По запросу ничего не найдено."
        
        text = "🔍 *Результаты поиска:*\n\n"
        for idx, r in enumerate(results[:count], 1):
            title = r.get("title", "Без названия")
            url = r.get("url", "")
            desc = r.get("description", "")[:150]
            text += f"{idx}. *{title}*\n{desc}...\n[Ссылка]({url})\n\n"
        
        return text
    except requests.HTTPError as e:
        if resp.status_code == 403:
            logger.error("Brave API: неверный ключ или исчерпан лимит")
            return "⚠️ Ошибка поиска: неверный API-ключ или закончился лимит."
        logger.error("Brave HTTP ошибка: %s", e)
        return f"⚠️ Ошибка поиска: {e}"
    except Exception as e:
        logger.error("Ошибка поиска: %s", e, exc_info=True)
        return "⚠️ Не удалось выполнить поиск. Попробуйте позже."
