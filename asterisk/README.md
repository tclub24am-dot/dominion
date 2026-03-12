# S-АТС — Asterisk 20 Integration Guide
## S-GLOBAL DOMINION | VERSHINA v200.14

---

## 🏗️ Архитектура

```
[SIP-клиент Парка PRO]  ──┐
[SIP-клиент Парка GO]   ──┤
[SIP-клиент Парка PLUS] ──┤──► [Asterisk 20] ──► CURL ──► [FastAPI /api/v1/telephony/webhook/asterisk]
[SIP-клиент Парка EXP]  ──┘         │                              │
                                     │                              ▼
                                     │                    [PostgreSQL: CallLog]
                                     │                    [Telegram уведомления]
                                     ▼
                              [AMI: dominion-backend]
                                     │
                                     ▼
                              [FastAPI Click-to-Call]
```

---

## 🔐 Безопасность (VERSHINA v200.14)

### 1. Обязательные действия перед запуском

**Заменить все пароли в конфигах:**

```bash
# pjsip.conf — SIP-пароли для каждого парка
grep -n "CHANGE_ME" asterisk/pjsip.conf

# manager.conf — AMI пароли
grep -n "CHANGE_ME" asterisk/manager.conf
```

**Установить секрет webhook в `.env`:**
```env
ATS_WEBHOOK_SECRET=<сгенерировать: openssl rand -hex 32>
```

### 2. Защита от брутфорса (fail2ban)

Установить fail2ban на хосте и добавить jail для Asterisk:

```ini
# /etc/fail2ban/jail.d/asterisk.conf
[asterisk]
enabled = true
filter = asterisk
logpath = /var/lib/docker/volumes/dominion_asterisk_logs/_data/security
maxretry = 5
findtime = 30
bantime = 3600
action = iptables-allports[name=asterisk]
```

### 3. Изоляция tenant_id

Каждый парк работает в **изолированном dialplan-контексте**:
- `park_pro` → tenant_id = `pro`
- `park_go` → tenant_id = `go`
- `park_plus` → tenant_id = `plus`
- `park_express` → tenant_id = `express`

Webhook всегда передаёт `tenant_id` в payload → FastAPI фильтрует данные по парку.

---

## 🚀 Запуск

```bash
# Запуск всего стека включая Asterisk
docker-compose up -d asterisk

# Проверка логов
docker logs dominion_asterisk -f

# Перезагрузка dialplan без рестарта
docker exec dominion_asterisk asterisk -rx "dialplan reload"

# Перезагрузка PJSIP без рестарта
docker exec dominion_asterisk asterisk -rx "module reload res_pjsip.so"

# Статус каналов
docker exec dominion_asterisk asterisk -rx "core show channels"

# Статус PJSIP endpoints
docker exec dominion_asterisk asterisk -rx "pjsip show endpoints"
```

---

## 📡 Webhook Payload

Asterisk отправляет POST на `http://app:8001/api/v1/telephony/webhook/asterisk`:

```json
{
  "Event": "new_call | call_answered | call_ended | call_missed",
  "CallerIDNum": "+79161234567",
  "Channel": "100",
  "Duration": 0,
  "tenant_id": "pro",
  "timestamp": "2026-03-08T22:00:00Z",
  "uniqueid": "1709935200.42"
}
```

**Заголовки:**
```
Content-Type: application/json
X-Webhook-Token: <ATS_WEBHOOK_SECRET>
X-Asterisk-UniqueID: <uniqueid>
```

---

## 🔧 Добавление нового SIP-аккаунта

1. Добавить в `pjsip.conf` секции `[endpoint]`, `[auth]`, `[aors]`
2. Указать правильный `context=park_<tenant_id>`
3. Перезагрузить: `docker exec dominion_asterisk asterisk -rx "module reload res_pjsip.so"`

---

## 📊 Мониторинг

```bash
# CDR (Call Detail Records)
docker exec dominion_asterisk asterisk -rx "cdr show status"

# Активные звонки
docker exec dominion_asterisk asterisk -rx "core show channels verbose"

# Статистика по tenant
# Через FastAPI: GET /api/v1/telephony/stats?tenant_id=pro
```
