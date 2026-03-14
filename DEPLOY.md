# 🏛️ S-GLOBAL DOMINION — ИНСТРУКЦИЯ ПО ДЕПЛОЮ
## Протокол VERSHINA v200.14 | Сервер: 89.169.39.111

---

## ⚡ БЫСТРЫЙ СТАРТ (одна команда)

```bash
docker-compose --env-file .env up -d --build
```

---

## 📋 ПОЛНАЯ ИНСТРУКЦИЯ (шаг за шагом)

### ШАГ 1 — Подключение к серверу

```bash
ssh root@89.169.39.111
```

### ШАГ 2 — Клонирование / обновление репозитория

```bash
# Первый деплой:
# © ООО «С-ГЛОБАЛ» — все права защищены
git clone https://git.s-global.space/dominion.git /root/dominion
cd /root/dominion

# Обновление (повторный деплой):
cd /root/dominion
git pull origin main
```

### ШАГ 3 — Подготовка .env файла

```bash
# Скопировать шаблон и заполнить реальными значениями:
cp .env.production .env
nano .env
```

**Обязательные поля для заполнения:**

| Переменная | Описание | Команда генерации |
|---|---|---|
| `SECRET_KEY` | JWT-секрет (128 символов) | `python3 -c "import secrets; print(secrets.token_hex(64))"` |
| `ATS_WEBHOOK_SECRET` | Секрет вебхука 1ATS | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `POSTGRES_PASSWORD` | Пароль БД | Придумать сильный пароль |
| `DATABASE_URL` | Строка подключения к БД | Обновить с новым паролем |
| `MASTER_BOOTSTRAP_PASSWORD` | Пароль мастер-пользователя | Придумать сильный пароль |
| `PRO_YANDEX_PARK_ID` | ID парка PRO (⭐ ПАРКОВЫЙ) | Из кабинета Яндекс.Флот |
| `PRO_YANDEX_CLIENT_ID` | Client ID парка PRO | Из кабинета Яндекс.Флот |
| `PRO_YANDEX_API_KEY` | API ключ парка PRO | Из кабинета Яндекс.Флот |

### ШАГ 4 — Сборка и запуск контейнеров

```bash
cd /root/dominion

# Сборка образов и запуск в фоне:
docker-compose --env-file .env up -d --build

# Проверка статуса:
docker-compose ps
```

**Ожидаемый результат:**
```
NAME              STATUS          PORTS
dominion_db       Up (healthy)    0.0.0.0:5432->5432/tcp
dominion_redis    Up (healthy)
dominion_app      Up              0.0.0.0:8001->8001/tcp
```

### ШАГ 5 — Сборка фронтенда (React SPA)

```bash
cd /root/dominion/frontend
npm install
npm run build
# Артефакты → /root/dominion/frontend/dist/
```

### ШАГ 6 — Настройка Nginx

```bash
# Скопировать конфиг:
cp /root/dominion/nginx/s-global.conf /etc/nginx/sites-available/s-global.conf
ln -sf /etc/nginx/sites-available/s-global.conf /etc/nginx/sites-enabled/

# Получить SSL-сертификат (Let's Encrypt):
certbot --nginx -d s-global.space -d www.s-global.space

# Перезапустить Nginx:
nginx -t && systemctl reload nginx
```

### ШАГ 7 — Проверка работоспособности

```bash
# Health check API:
curl -s http://localhost:8001/health

# Логи приложения:
docker-compose logs -f app

# Логи БД:
docker-compose logs -f db
```

---

## 🔄 ОБНОВЛЕНИЕ СИСТЕМЫ (повторный деплой)

```bash
cd /root/dominion
git pull origin main

# Пересборка только app-контейнера (БД не трогаем!):
docker-compose up -d --build app

# Проверка:
docker-compose ps
docker-compose logs -f app --tail=50
```

---

## 🛡️ БЕЗОПАСНОСТЬ

### Права доступа к .env:
```bash
chmod 600 /root/dominion/.env
chown root:root /root/dominion/.env
```

### Firewall (UFW):
```bash
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP → редирект на HTTPS
ufw allow 443/tcp   # HTTPS
ufw deny 8001/tcp   # FastAPI — только через Nginx!
ufw deny 5432/tcp   # PostgreSQL — только внутри Docker!
ufw enable
```

---

## 🗄️ РЕЗЕРВНОЕ КОПИРОВАНИЕ БД

```bash
# Создать бэкап:
docker exec dominion_db pg_dump -U dominion_master dominion > /root/backups/dominion_$(date +%Y%m%d_%H%M%S).sql

# Восстановить из бэкапа:
docker exec -i dominion_db psql -U dominion_master dominion < /root/backups/dominion_YYYYMMDD_HHMMSS.sql
```

---

## 🔧 ПОЛЕЗНЫЕ КОМАНДЫ

```bash
# Перезапуск всей системы:
docker-compose restart

# Остановка:
docker-compose down

# Остановка с удалением данных (ОСТОРОЖНО!):
docker-compose down -v

# Войти в контейнер приложения:
docker exec -it dominion_app bash

# Выполнить Python-команду в контейнере:
docker exec -e PYTHONPATH=/app dominion_app python -m app.create_master_user

# Просмотр логов в реальном времени:
docker-compose logs -f --tail=100

# Статус контейнеров:
docker-compose ps

# Использование ресурсов:
docker stats
```

---

## 📊 АРХИТЕКТУРА ДЕПЛОЯ

```
Internet
    │
    ▼
[Nginx :443 SSL]  ←── /etc/letsencrypt/live/s-global.space/
    │
    ├── /api/*  ──────────────────► [dominion_app :8001]
    │                                      │
    ├── /ws/*   ──────────────────►        │
    │                               [dominion_db :5432]
    ├── /static/* ─── /root/dominion/app/static/
    │                               [dominion_redis :6379]
    └── /* ─────────── /root/dominion/frontend/dist/
```

---

## ✅ ЧЕКЛИСТ ПЕРЕД ДЕПЛОЕМ

- [ ] `.env` заполнен всеми реальными значениями
- [ ] `SECRET_KEY` — случайный hex 128 символов (НЕ дефолтный!)
- [ ] `ATS_WEBHOOK_SECRET` — случайный urlsafe токен
- [ ] `POSTGRES_PASSWORD` — сильный пароль (не `postgres`)
- [ ] `MASTER_BOOTSTRAP_PASSWORD` — задан и сохранён в менеджере паролей
- [ ] Все `YANDEX_*` ключи для активных парков заполнены
- [ ] Firewall настроен (порты 8001, 5432 закрыты снаружи)
- [ ] SSL-сертификат получен через certbot
- [ ] Nginx конфиг проверен (`nginx -t`)
- [ ] Фронтенд собран (`npm run build`)
- [ ] Бэкап БД настроен (cron)

---

*S-GLOBAL DOMINION VERSHINA v200.14 — Total Autonomy. Total Control.*
