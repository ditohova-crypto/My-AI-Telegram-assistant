# 🚀 Деплой на Render.com (бесплатный хостинг 24/7)

Пошаговая инструкция по развёртыванию бота на облаке.

---

## 📋 Что понадобится

| Ресурс | Зачем |
|--------|-------|
| GitHub аккаунт | Хранить код (без секретов!) |
| Render аккаунт | Хостинг сервера |
| Ваш `.env` | Значения для Environment Variables |

> 💡 **Время:** ~15 минут.

---

## ⚠️ Важно: безопасность перед публикацией

Убедитесь, что **секреты не попадут на GitHub**:

1. Проверьте `.gitignore` — в нём должна быть строка `.env`
2. **Не редактируйте** `config.py` — там нет ключей, только чтение из `.env`
3. **Не создавайте** файлы типа `keys.txt`, `secrets.json` без добавления в `.gitignore`

Проверка перед публикацией:
```bash
# Посмотрите, какие файлы Git готовит к публикации
git status
# .env должен быть НЕ в списке (игнорируется)
# .env.example — может быть в списке (это нормально)
```

---

## Шаг 1. Загрузите код на GitHub

Код загружается **без `.env`** — он остаётся только у вас на компьютере.

### Если Git ещё не инициализирован:
```bash
cd папка-с-ботом
git init
git add .
git commit -m "Initial commit"
git branch -M main
# Создайте репозиторий на github.com и скопируйте ссылку
git remote add origin https://github.com/ВАШ_НИК/НАЗВАНИЕ.git
git push -u origin main
```

### Если уже есть репозиторий:
```bash
git add .
git commit -m "Update bot configuration"
git push origin main
```

> ⚠️ После пуша зайдите на GitHub и убедитесь, что файла `.env` там **нет**.

---

## Шаг 2. Зарегистрируйтесь на Render

1. [render.com](https://render.com) → **"Get Started for Free"**
2. Зарегистрируйтесь через **GitHub**
3. Подтвердите доступ к репозиториям

---

## Шаг 3. Создайте Web Service

1. В Dashboard нажмите **"New +"** → **"Web Service"**
2. Найдите ваш репозиторий → **"Connect"**
3. Заполните поля:

| Поле | Значение |
|------|----------|
| **Name** | `kimi-telegram-bot` (или любое) |
| **Region** | `Frankfurt (EU Central)` |
| **Runtime** | `Docker` |
| **Branch** | `main` |
| **Plan** | **Free** (внизу страницы) |

4. Нажмите **"Advanced"** → добавьте **Environment Variables**:

| Variable | Value |
|----------|-------|
| `TELEGRAM_BOT_TOKEN` | `8793906279:AAF6i3PeOxBmGC2fbw3Xu9WuDnbr8wpHNe8` |
| `AI_API_KEY` | `sk-viUUKlwRVJb9Esmz73cK7DlhikPqXlRtbwl3fCOZC3goODGx` |
| `AI_BASE_URL` | `https://api.moonshot.ai/v1` |
| `AI_MODEL` | `kimi-k2.5` |
| `AI_TEMPERATURE` | `1` |
| `AI_MAX_TOKENS` | `2048` |
| `WEBHOOK_SECRET` | `придумайте-любую-строку` |

> 💡 `WEBHOOK_SECRET` — защитный пароль. Например: `my-secret-2024-x7k9`

5. Нажмите **"Create Web Service"**

Render начнёт сборку. Ждите 2–4 минуты.

---

## Шаг 4. Установите Webhook в Telegram

После зелёной галочки **"Live"** скопируйте URL бота (например `https://kimi-telegram-bot-abc12.onrender.com`).

Откройте в браузере (вставьте свой URL и секрет):

```
https://api.telegram.org/bot8793906279:AAF6i3PeOxBmGC2fbw3Xu9WuDnbr8wpHNe8/setWebhook?url=https://ВАШ_URL.onrender.com/telegram-webhook&secret_token=ВАШ_WEBHOOK_SECRET
```

Пример готовой ссылки:
```
https://api.telegram.org/bot8793906279:AAF6i3PeOxBmGC2fbw3Xu9WuDnbr8wpHNe8/setWebhook?url=https://kimi-telegram-bot-abc12.onrender.com/telegram-webhook&secret_token=my-secret-2024-x7k9
```

Ожидаемый ответ:
```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

---

## Шаг 5. Проверка

1. **Health check:**
   ```
   https://kimi-telegram-bot-xxx.onrender.com/health
   ```
   Должно показать: `{"status":"ok"}`

2. **Пишем боту в Telegram:** `/start`
   Должен прийти ответ сразу.

---

## ⚠️ Особенности бесплатного тарифа Render

| Ограничение | Что это значит |
|-------------|----------------|
| **Sleep** | После 15 мин без сообщений сервер "засыпает". Следующее сообщение разбудит его за 10–30 секунд. |
| **Лимит часов** | 750 часов/месяц (~31 день) — хватает на 1 бот |
| **SQLite** | База внутри контейнера. При пересборке данные сбрасываются (если нет Disk). |

---

## 🔄 Обновление кода

Если что-то поменяли в коде:
```bash
git add .
git commit -m "Fix something"
git push origin main
```
Render автоматически пересоберёт сервер.

---

## 🆘 Решение проблем

### Бот молчит
- Render → ваш сервис → вкладка **"Logs"** — ищите ошибку
- Проверьте `AI_API_KEY` — может закончиться баланс
- Проверьте webhook: `https://api.telegram.org/botВАШ_ТОКЕН/getWebhookInfo`

### Сервер падает при старте
- В логах Render ищите ошибку конфигурации
- Проверьте, что все Environment Variables заполнены (нет пустых полей)

### "Unauthorized"
- `WEBHOOK_SECRET` в Render и в URL установки webhook должны совпадать

### Webhook не устанавливается
- Убедитесь, что URL начинается с `https://`
- Удалите старый webhook: `https://api.telegram.org/botВАШ_ТОКЕН/deleteWebhook`

---

**Готово! Ваш бот работает 24/7 🎉**
