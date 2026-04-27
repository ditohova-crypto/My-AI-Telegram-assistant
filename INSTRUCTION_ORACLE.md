# 🏛️ Oracle Cloud Free Tier — Полная инструкция

> Это единственный бесплатный VPS, который не спит и не теряет данные.
> 4 CPU, 24 GB RAM, 200 GB диск — навсегда бесплатно.

---

## 📋 Что понадобится

| Что | Где взять |
|-----|-----------|
| Email | У вас есть |
| Телефон | У вас есть |
| Банковская карта | Visa/MasterCard (можно виртуальную, например Тинькофф) |
| 30 минут времени | Сейчас |

> ⚠️ Карта нужна ТОЛЬКО для верификации. Oracle НЕ списывает деньги (проверяют $1 и сразу возвращают).

---

## 🐾 Шаг 1. Регистрация на Oracle Cloud

1. Откройте [signup.oraclecloud.com](https://signup.oraclecloud.com)
2. Введите:
   - **Email**: ваш
   - **Password**: придумайте сложный
   - **Account Name**: `anastasia-ai-bot` (или любое)
   - **Country**: Russia (или вашу)
3. Нажмите **"Next"**
4. Введите **Mobile Number** (ваш телефон)
5. Получите SMS-код, введите
6. Нажмите **"Verify My Email"**
7. Перейдите по ссылке из письма Oracle

---

## 💳 Шаг 2. Подтверждение личности (Payment Verification)

Oracle требует карту для защиты от ботов.

1. Введите данные карты (Visa/MasterCard)
2. Oracle может заморозить $1 для проверки (вернут через 1-7 дней)
3. **НЕТ ежемесячной платы, НЕТ автосписаний**
4. Нажмите **"Complete Sign-Up"**

> 💡 Если карта не проходит — попробуйте виртуальную карту Тинькофф/ЮMoney. Дебетовые карты Сбер/ВТБ обычно работают.

---

## 🖥️ Шаг 3. Создание сервера (VM)

После входа в [cloud.oracle.com](https://cloud.oracle.com):

### 3.1 Создать Compartment (если нет)
1. Меню (гамбургер) → **Identity & Security** → **Compartments**
2. **Create Compartment**
3. Name: `telegram-bot`
4. Description: `AI bot`
5. **Create**

### 3.2 Создать виртуальную машину
1. Меню → **Compute** → **Instances**
2. **Create Instance**
3. Настройки:

| Поле | Значение |
|------|----------|
| **Name** | `telegram-bot` |
| **Compartment** | `telegram-bot` |
| **Placement** | Оставьте как есть |
| **Image and shape** | **Change image** → **Canonical Ubuntu** → **Ubuntu 22.04** |
| **Shape** | **Change shape** → **VM.Standard.A1.Flex** (ARM, Always Free) |
| **OCPU** | 4 |
| **Memory** | 24 GB |
| **Boot volume** | 200 GB |

4. **Add SSH keys** → **Generate SSH key pair** → **Save Private Key** (скачайте файл `.key`!)
5. **Create** — ждите 2-3 минуты

> ⚠️ Обязательно скачайте приватный SSH-ключ! Без него не зайдёте на сервер.

---

## 🌐 Шаг 4. Открыть порт для SSH

Oracle по умолчанию блокирует всё кроме SSH. Нужно открыть порт (хотя для бота достаточно исходящих).

1. **Compute** → **Instances** → кликните на ваш сервер
2. Внизу найдите **Subnet** → кликните на ссылку
3. **Security Lists** (слева) → кликните на список
4. **Add Ingress Rules**
5. Добавьте правило:
   - **Source CIDR**: `0.0.0.0/0`
   - **IP Protocol**: `TCP`
   - **Destination Port Range**: `22`
   - Description: `SSH access`

Для бота порт не нужен — он работает через исходящие соединения к Telegram.

---

## 🔑 Шаг 5. Подключение к серверу по SSH

### Windows:
1. Скачайте **PuTTY** или используйте **Windows Terminal**
2. Откройте терминал, перейдите в папку с ключом:
```bash
cd Downloads
ssh -i ВАШ_КЛЮЧ.key ubuntu@ВАШ_IP
```

### Mac/Linux:
```bash
chmod 600 ~/Downloads/ВАШ_КЛЮЧ.key
ssh -i ~/Downloads/ВАШ_КЛЮЧ.key ubuntu@ВАШ_IP
```

**ВАШ_IP** — публичный IP вашего сервера (виден в Oracle → Instances → Public IP).

---

## 🤖 Шаг 6. Установка бота (автоматически)

После подключения по SSH вы увидите `ubuntu@telegram-bot:~$`

### Вариант А: Автоустановка (рекомендуется)

```bash
curl -sL https://raw.githubusercontent.com/ВАШ_НИК/telegram-ai-bot/main/install.sh | bash
```

> Замените `ВАШ_НИК` на ваш GitHub username.

### Вариант Б: Ручная установка

```bash
# 1. Обновление
sudo apt update && sudo apt upgrade -y

# 2. Python
sudo apt install -y python3.11 python3.11-venv python3-pip git

# 3. Клонирование
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/ВАШ_НИК/telegram-ai-bot.git
cd telegram-ai-bot

# 4. Виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Настройка .env
nano .env
# Вставьте свои ключи, сохраните (Ctrl+O, Enter, Ctrl+X)

# 6. Создание сервиса
sudo nano /etc/systemd/system/telegram-bot.service
```

Вставьте в файл:
```ini
[Unit]
Description=AI Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/projects/telegram-ai-bot
Environment=PATH=/home/ubuntu/projects/telegram-ai-bot/venv/bin
EnvironmentFile=/home/ubuntu/projects/telegram-ai-bot/.env
ExecStart=/home/ubuntu/projects/telegram-ai-bot/venv/bin/python bot_vps.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохраните и запустите:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

---

## 🚀 Шаг 7. Запуск и проверка

### Проверить статус:
```bash
sudo systemctl status telegram-bot
```

Должно быть зелёное **"active (running)"**.

### Смотреть логи в реальном времени:
```bash
sudo journalctl -u telegram-bot -f
```

### Команды управления:
```bash
sudo systemctl start telegram-bot    # запуск
sudo systemctl stop telegram-bot     # остановка
sudo systemctl restart telegram-bot  # перезапуск
sudo systemctl status telegram-bot     # статус
```

---

## 🔍 Шаг 8. Проверить бота в Telegram

1. Откройте Telegram
2. Найдите своего бота
3. Напишите `/start`
4. Бот должен ответить

Поболтайте минут 5, потом напишите `/brief` — должен сгенерировать бриф.

---

## 🆘 Если что-то не работает

### Сервис не запускается
```bash
sudo journalctl -u telegram-bot -n 50
```
Смотрите ошибку — скорее всего неверный `.env`.

### Ошибка в .env
```bash
nano /home/ubuntu/projects/telegram-ai-bot/.env
```
Проверьте что ключи правильные, без лишних пробелов.

### Нет прав на папку
```bash
sudo chown -R ubuntu:ubuntu /home/ubuntu/projects/telegram-ai-bot
```

### Перезагрузка сервера
```bash
sudo reboot
```
После перезагрузки бот запустится автоматически (systemd).

---

## 📊 Что получилось

| Характеристика | Oracle Free |
|----------------|-------------|
| **Цена** | $0 навсегда |
| **CPU** | 4 ядра (ARM) |
| **RAM** | 24 GB |
| **Диск** | 200 GB (постоянный) |
| **Сон** | Никогда |
| **Память бота** | SQLite на диске, не теряется |
| **Напоминания** | Работают 24/7 |
| **Брифы** | Работают 24/7 |
| **Поиск** | Через Brave API |
| **Автозапуск** | Через systemd |

---

## 💰 Что платное (опционально)

| Услуга | Цена | Нужна ли |
|--------|------|----------|
| Oracle Free Tier | $0 | ✅ Да, бесплатно |
| Moonshot AI API | ~$0.003/запрос | ✅ Да, минимум $1 |
| Brave Search API | 2000 бесплатно/мес | ✅ Да |
| Домен (опционально) | $10/год | ❌ Нет |

---

## 🎉 Поздравляю!

Теперь у вас настоящий AI-ассистент:
- ✅ Работает 24/7
- ✅ Помнит всё навсегда
- ✅ Присылает напоминания
- ✅ Утренний бриф каждый день
- ✅ Поиск в интернете
- ✅ Не требует вашего вмешательства

---

Если застрянете на любом шаге — скопируйте ошибку сюда, я помогу.
