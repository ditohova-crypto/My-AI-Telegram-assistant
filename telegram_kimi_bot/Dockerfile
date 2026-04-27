FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p logs
ENV PORT=10000
EXPOSE $PORT
CMD uvicorn main_webhook:fastapi_app --host 0.0.0.0 --port ${PORT}
