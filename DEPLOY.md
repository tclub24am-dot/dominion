# 🏛️ S-GLOBAL DOMINION — ИНСТРУКЦИЯ ПО ДЕПЛОЮ
## Протокол VERSHINA v200.20 | Сервер: 89.169.39.111 / s-global.space

---

## ⚡ ЗАПУСК «ОДНОЙ КНОПКОЙ» (4 команды на сервере)

```bash
# 1. Подключиться к серверу
ssh root@89.169.39.111

# 2. Клонировать репозиторий и перейти в директорию
git clone https://git.s-global.space/dominion.git /root/dominion && cd /root/dominion

# 3. Заполнить конфигурацию (заменить все REPLACE_WITH_* реальными значениями)
cp .env.production .env && nano .env

# 4. Запустить деплой (SSL + Docker + БД + пользователи + данные)
bash scripts/deploy_server.sh
```

> Скрипт автоматически: проверит зависимости, настроит firewall, получит SSL, соберёт и запустит все контейнеры, инициализирует БД, создаст всех пользователей и загрузит данные логистики за 10 марта.

---

## 🤖 AI-СОВЕТНИК MIX — ПЕРЕКЛЮЧЕНИЕ GEMINI / OLLAMA

В файле `.env` управляется переменной `AI_BACKEND`:

| Значение | Режим | Когда использовать |
|---|---|---|
| `AI_BACKEND=gemini` | Прямой Gemini API | **Сервер s-global.space** (нет GPU) |
| `AI_BACKEND=ollama` | Локальный Ollama | Локальная разработка (есть GPU) |

**Для сервера (без GPU):**
```bash
AI_BACKEND=gemini
GEMINI_API_KEY=ваш_ключ_из_aistudio.google.com
GEMINI_MODEL=gemini-2.0-flash
```

**Для локальной разработки (с GPU):**
```bash
AI_BACKEND=ollama
OLLAMA_BASE_URL=http://ollama:11434/v1
GEMINI_MODEL=gemini-3-flash-preview:cloud
```

---

## 📋 ПОЛНАЯ ИНСТРУКЦИЯ (шаг за шагом)

### ШАГ 1 — Подключение к серверу

```bash
ssh root@89.169.39.111
```

### ШАГ 2 — Установка зависимостей (если не установлены)

```bash
# Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker

# Docker Compose v2
apt-get install -y docker-compose-plugin

# Certbot (SSL)
apt-get install -y certbot

# Утилиты
apt-get install -y git ufw curl
```

### ШАГ 3 — Клонирование репозитория

```bash
# Первый деплой:
git clone https://git.s-global.space/dominion.git /root/dominion
cd /root/dominion

# Обновление (повторный деплой):
cd /root/dominion && git pull origin main
```

### ШАГ 4 — Подготовка .env файла

```bash
cp .env.production .env
nano .env
chmod 600 .env
```

**Обязательные поля для заполнения:**

| Переменная | Описание | Команда генерации |
|---|---|---|
| `SECRET_KEY` | JWT-секрет (128 символов) | `python3 -c "import secrets; print(secrets.token_hex(64))"` |
| `POSTGRES_PASSWORD` | Пароль БД | Придумать сильный пароль |
| `REDIS_PASSWORD` | Пароль Redis | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `MASTER_BOOTSTRAP_PASSWORD` | Пароль мастер-пользователя | Придумать сильный пароль |
| `ATS_WEBHOOK_SECRET` | Секрет вебхука Asterisk | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `AMI_SECRET` | Пароль AMI Asterisk | `python3 -c "import secrets; print(secrets.token_urlsafe(24))"` |
| `EXTERNAL_IP` | Внешний IP сервера | `89.169.39.111` |
| `PRO_YANDEX_*` | Ключи Яндекс.Флот (парк PRO) | Из кабинета Яндекс.Флот |

### ШАГ 5 — Получение SSL-сертификата

```bash
# Убедитесь что DNS s-global.space → 89.169.39.111 уже настроен!
certbot certonly --standalone -d s-global.space -d www.s-global.space \
    --non-interactive --agree-tos --email admin@s-global.space

# Проверка:
ls /etc/letsencrypt/live/s-global.space/
```

### ШАГ 6 — Настройка Firewall

```bash
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP → редирект на HTTPS
ufw allow 443/tcp   # HTTPS
ufw allow 5060/udp  # SIP UDP (Asterisk)
ufw allow 5061/tcp  # SIP TCP (Asterisk)
ufw allow 8089/tcp  # Asterisk WebRTC WSS
ufw allow 10000:20000/udp  # RTP Media
ufw deny 8001/tcp   # FastAPI — только через Nginx!
ufw deny 5432/tcp   # PostgreSQL — только Docker!
ufw deny 6379/tcp   # Redis — только Docker!
ufw --force enable
```

### ШАГ 7 — Сборка и запуск контейнеров

```bash
cd /root/dominion

# Продакшн-деплой:
docker compose -f docker-compose.prod.yml --env-file .env up -d --build

# Проверка статуса:
docker compose -f docker-compose.prod.yml ps
```

**Ожидаемый результат:**
```
NAME                  STATUS          PORTS
dominion_db           Up (healthy)
dominion_redis        Up (healthy)
dominion_app          Up
dominion_asterisk     Up
dominion_ollama       Up
dominion_synapse      Up (healthy)
dominion_frontend     Up
dominion_nginx        Up              0.0.0.0:80->80, 0.0.0.0:443->443
```

### ШАГ 8 — Инициализация БД (первый деплой)

```bash
# Создание таблиц:
docker exec -e PYTHONPATH=/app dominion_app python -m app.create_db

# Создание мастер-пользователя:
docker exec -e PYTHONPATH=/app dominion_app python -m app.create_master_user
```

### ШАГ 9 — Проверка работоспособности

```bash
# Health check API:
curl -s https://s-global.space/health

# Логи приложения:
docker compose -f docker-compose.prod.yml logs -f app --tail=50

# Логи Nginx:
docker compose -f docker-compose.prod.yml logs -f nginx --tail=50
```

---

## 🗄️ ПЕРЕНОС БАЗЫ ДАННЫХ (с локальной машины на сервер)

```bash
# На локальной машине — экспорт:
./scripts/dump_db.sh export
# Файл: /root/backups/dominion_YYYYMMDD_HHMMSS.sql.gz

# Полный цикл (экспорт + загрузка + импорт на сервере):
./scripts/dump_db.sh deploy 89.169.39.111

# На сервере — импорт вручную:
./scripts/dump_db.sh import /root/dominion/backups/dominion_YYYYMMDD_HHMMSS.sql.gz
```

**Настройка автобэкапа (cron):**
```bash
# Бэкап каждый день в 03:00:
(crontab -l; echo "0 3 * * * cd /root/dominion && bash scripts/dump_db.sh cron >> /var/log/dominion_backup.log 2>&1") | crontab -
```

---

## 📞 ТЕЛЕФОНИЯ ASTERISK (NAT-конфигурация)

Для работы звонков из браузера через `wss://s-global.space/ws-sip/`:

1. **EXTERNAL_IP** в `.env` должен быть `89.169.39.111`
2. Nginx проксирует `wss://s-global.space/ws-sip/` → `asterisk:8089`
3. В `pjsip.conf` плейсхолдеры `%%EXTERNAL_SIGNALING_UDP%%` и `%%EXTERNAL_MEDIA_UDP%%` автоматически заменяются скриптом `init_asterisk_secrets.sh`
4. Порты RTP `10000-20000/udp` должны быть открыты в firewall

**Проверка Asterisk:**
```bash
docker exec -it dominion_asterisk asterisk -rx "pjsip show transports"
docker exec -it dominion_asterisk asterisk -rx "pjsip show endpoints"
```

---

## 🔄 ОБНОВЛЕНИЕ СИСТЕМЫ (повторный деплой)

```bash
cd /root/dominion
git pull origin main

# Пересборка только app и frontend (БД не трогаем!):
docker compose -f docker-compose.prod.yml --env-file .env up -d --build app frontend

# Проверка:
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f app --tail=50
```

---

## 🛡️ БЕЗОПАСНОСТЬ

```bash
# Права доступа к .env:
chmod 600 /root/dominion/.env
chown root:root /root/dominion/.env

# Проверка открытых портов:
ss -tlnp | grep -E '80|443|5060|8089'

# Автообновление SSL (certbot):
certbot renew --dry-run
```

---

## 🔧 ПОЛЕЗНЫЕ КОМАНДЫ

```bash
# Перезапуск всей системы:
docker compose -f docker-compose.prod.yml restart

# Остановка:
docker compose -f docker-compose.prod.yml down

# Войти в контейнер приложения:
docker exec -it dominion_app bash

# Просмотр логов в реальном времени:
docker compose -f docker-compose.prod.yml logs -f --tail=100

# Статус контейнеров:
docker compose -f docker-compose.prod.yml ps

# Использование ресурсов:
docker stats

# Ручной бэкап БД:
./scripts/dump_db.sh export
```

---

## 📊 АРХИТЕКТУРА ДЕПЛОЯ

```
Internet (HTTPS/WSS)
        │
        ▼
[dominion_nginx :443 SSL]  ←── /etc/letsencrypt/live/s-global.space/
        │
        ├── /api/*  ──────────────────► [dominion_app :8001]
        │                                      │
        ├── /ws/*   ──────────────────►        ├── [dominion_db :5432]
        │                                      └── [dominion_redis :6379]
        ├── /ws-sip/* ─────────────────► [dominion_asterisk :8089 WSS]
        │
        ├── /_matrix/* ────────────────► [dominion_synapse :8008]
        │
        ├── /static/* ─── app_static volume
        ├── /storage/* ── dominion_storage volume
        │
        └── /* ─────────────────────────► [dominion_frontend :80]
                                                (React SPA dist/)

SIP/RTP (UDP/TCP):
[Internet] → 89.169.39.111:5060/udp → [dominion_asterisk]
[Internet] → 89.169.39.111:5061/tcp → [dominion_asterisk]
[Internet] → 89.169.39.111:10000-20000/udp → [dominion_asterisk RTP]
```

---

## ✅ ЧЕКЛИСТ ПЕРЕД ДЕПЛОЕМ

- [ ] DNS `s-global.space` → `89.169.39.111` настроен
- [ ] `.env` заполнен всеми реальными значениями
- [ ] `SECRET_KEY` — случайный hex 128 символов (НЕ дефолтный!)
- [ ] `POSTGRES_PASSWORD` — сильный пароль (не `postgres`)
- [ ] `REDIS_PASSWORD` — задан
- [ ] `MASTER_BOOTSTRAP_PASSWORD` — задан и сохранён в менеджере паролей
- [ ] `EXTERNAL_IP=89.169.39.111` — задан для Asterisk NAT
- [ ] Все `YANDEX_*` ключи для активных парков заполнены
- [ ] SSL-сертификат получен через certbot
- [ ] Firewall настроен (UFW)
- [ ] Бэкап локальной БД создан (`./scripts/dump_db.sh export`)
- [ ] БД перенесена на сервер (`./scripts/dump_db.sh deploy 89.169.39.111`)
- [ ] Автобэкап настроен (cron)

---

*S-GLOBAL DOMINION VERSHINA v200.17 — Total Autonomy. Total Control. s-global.space*
