# === Билд-стадия ===
FROM python:3.11-slim

# Отключаем буферизацию вывода Python (логи сразу идут в консоль)
ENV PYTHONUNBUFFERED=1

# Рабочая директория
WORKDIR /app

# Устанавливаем зависимости системы (для сборки некоторых пакетов)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код
COPY . .

# Создаём папку для логов (если используется файловый лог)
RUN mkdir -p logs

# Render передаёт порт через переменную $PORT, поэтому используем её
# Если PORT не задан, fallback на 10000
ENV PORT=10000
EXPOSE $PORT

# Запуск webhook-версии бота
# --host 0.0.0.0 обязателен для Docker / облака (слушать все интерфейсы)
CMD ["sh", "-c", "uvicorn main_webhook:fastapi_app --host 0.0.0.0 --port ${PORT}"]
