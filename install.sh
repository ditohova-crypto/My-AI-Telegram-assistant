#!/bin/bash
# ============================================================================
# Скрипт автоматической установки бота на Ubuntu VPS
# Работает на: Timeweb Cloud, Oracle Cloud, Hetzner, DigitalOcean, и др.
# ============================================================================
# Запуск: bash install.sh

set -e

echo "========================================"
echo "  Установка AI Telegram Bot на VPS"
echo "========================================"

# Определение папки установки
if [ "$EUID" -eq 0 ]; then
    BOT_DIR="/opt/telegram-bot"
    SERVICE_USER="root"
else
    BOT_DIR="$HOME/telegram-bot"
    SERVICE_USER="$USER"
fi

SERVICE_NAME="telegram-bot"

echo ""
echo "Папка установки: $BOT_DIR"
echo "Пользователь: $SERVICE_USER"
echo ""

# === 1. Обновление системы ===
echo "[1/7] Обновление пакетов..."
sudo apt-get update -y
sudo apt-get upgrade -y

# === 2. Установка Python и зависимостей ===
echo "[2/7] Установка Python..."
sudo apt-get install -y python3.11 python3.11-venv python3-pip git curl nano

# === 3. Создание папки ===
echo "[3/7] Создание папки бота..."
sudo mkdir -p "$BOT_DIR"
sudo chown "$SERVICE_USER:$SERVICE_USER" "$BOT_DIR"

# === 4. Создание виртуального окружения ===
echo "[4/7] Создание виртуального окружения..."
cd "$BOT_DIR"
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# === 5. Создание .env ===
echo "[5/7] Создание .env..."
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
AI_API_KEY=your-moonshot-api-key
AI_BASE_URL=https://api.moonshot.ai/v1
AI_MODEL=kimi-k2.5
AI_TEMPERATURE=1
AI_MAX_TOKENS=2048
BRAVE_API_KEY=
EOF
    echo "⚠️  ВАЖНО: Отредактируйте файл $BOT_DIR/.env"
fi

# === 6. Создание файлов бота (если нет) ===
echo "[6/7] Создание файлов бота..."

if [ ! -f "bot_vps.py" ]; then
    echo "⚠️  Файлы бота не найдены. Создаём заглушки..."
    echo "Вам нужно загрузить файлы bot_vps.py, config.py, database.py, search.py"
    echo "Положите их в папку $BOT_DIR"
fi

# === 7. Создание systemd сервиса ===
echo "[7/7] Создание системного сервиса..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=AI Telegram Bot
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$BOT_DIR
Environment=PATH=$BOT_DIR/venv/bin
EnvironmentFile=$BOT_DIR/.env
ExecStart=$BOT_DIR/venv/bin/python $BOT_DIR/bot_vps.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}

echo ""
echo "========================================"
echo "  УСТАНОВКА ЗАВЕРШЕНА!"
echo "========================================"
echo ""
echo "Следующие шаги:"
echo ""
echo "1. Загрузите файлы бота в папку:"
echo "   $BOT_DIR"
echo "   (bot_vps.py, config.py, database.py, search.py)"
echo ""
echo "2. Установите зависимости:"
echo "   cd $BOT_DIR"
echo "   source venv/bin/activate"
echo "   pip install -r requirements.txt"
echo ""
echo "3. Отредактируйте .env:"
echo "   nano $BOT_DIR/.env"
echo ""
echo "4. Запустите бота:"
echo "   sudo systemctl start $SERVICE_NAME"
echo ""
echo "5. Проверьте статус:"
echo "   sudo systemctl status $SERVICE_NAME"
echo ""
echo "6. Смотрите логи:"
echo "   sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Команды управления:"
echo "   sudo systemctl start $SERVICE_NAME    -- запуск"
echo "   sudo systemctl stop $SERVICE_NAME     -- остановка"
echo "   sudo systemctl restart $SERVICE_NAME  -- перезапуск"
echo "   sudo systemctl status $SERVICE_NAME   -- статус"
echo "========================================"
