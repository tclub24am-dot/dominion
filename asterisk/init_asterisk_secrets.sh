#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — asterisk/init_asterisk_secrets.sh
# Протокол: VERSHINA v200.16.5
# Скрипт инициализации секретов Asterisk при старте контейнера.
#
# Заменяет плейсхолдеры %%VAR%% в конфигах на реальные значения
# из переменных окружения. Если переменная не задана — АВАРИЙНЫЙ СТОП.
#
# NAT-TRAVERSAL:
#   Если задана переменная EXTERNAL_IP (например, 89.169.39.111),
#   в pjsip.conf будут подставлены external_media_address и
#   external_signaling_address для всех транспортов.
#   Если EXTERNAL_IP не задана — плейсхолдеры заменяются пустыми строками
#   (локальная разработка, Asterisk использует локальный IP).
# ============================================================
set -euo pipefail

echo "🔐 [Asterisk Init] Проверка обязательных секретов..."

# ============================================================
# ПРОВЕРКА ОБЯЗАТЕЛЬНЫХ ПЕРЕМЕННЫХ (fail-fast)
# ============================================================
REQUIRED_VARS=(
    "AMI_SECRET"
    "F2B_SECRET"
    "ASTERISK_SYSTEM_PASS"
    "SIP_PRO_001_PASS"
    "SIP_GO_001_PASS"
    "SIP_PLUS_001_PASS"
    "SIP_EXPRESS_001_PASS"
)

MISSING=0
for VAR in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!VAR:-}" ]; then
        echo "❌ FATAL: Переменная окружения '${VAR}' не задана!" >&2
        MISSING=1
    fi
done

if [ "$MISSING" -eq 1 ]; then
    echo "❌ FATAL: Asterisk не может стартовать без обязательных секретов." >&2
    echo "   Задайте все переменные в файле .env и перезапустите контейнер." >&2
    exit 1
fi

echo "✅ [Asterisk Init] Все секреты присутствуют. Генерация конфигов..."

log_replacement() {
    echo "🔄 [Asterisk Init] Замена плейсхолдера '$1' в '$2'"
}

# ============================================================
# ГЕНЕРАЦИЯ КОНФИГОВ ИЗ ШАБЛОНОВ
# Шаблоны: /etc/asterisk/*.conf (смонтированы из ./asterisk/)
# Результат: /etc/asterisk/*.conf (перезаписываем на месте)
# ============================================================

# manager.conf
log_replacement "%%AMI_SECRET%%" "/etc/asterisk/manager.conf"
log_replacement "%%F2B_SECRET%%" "/etc/asterisk/manager.conf"
sed \
    -e "s|%%AMI_SECRET%%|${AMI_SECRET}|g" \
    -e "s|%%F2B_SECRET%%|${F2B_SECRET}|g" \
    /etc/asterisk/manager.conf > /tmp/manager.conf.rendered
cp /tmp/manager.conf.rendered /etc/asterisk/manager.conf

# pjsip.conf
log_replacement "%%SYSTEM_PASS%%" "/etc/asterisk/pjsip.conf"
log_replacement "%%SIP_PRO_001_PASS%%" "/etc/asterisk/pjsip.conf"
log_replacement "%%SIP_GO_001_PASS%%" "/etc/asterisk/pjsip.conf"
log_replacement "%%SIP_PLUS_001_PASS%%" "/etc/asterisk/pjsip.conf"
log_replacement "%%SIP_EXPRESS_001_PASS%%" "/etc/asterisk/pjsip.conf"

# NAT-traversal: подставляем EXTERNAL_IP если задан, иначе убираем плейсхолдеры
if [ -n "${EXTERNAL_IP:-}" ]; then
    echo "🌐 [Asterisk Init] EXTERNAL_IP=${EXTERNAL_IP} — включаем NAT-traversal для всех транспортов"
    EXT_MEDIA_UDP="external_media_address=${EXTERNAL_IP}"
    EXT_SIGNAL_UDP="external_signaling_address=${EXTERNAL_IP}"
    EXT_MEDIA_TCP="external_media_address=${EXTERNAL_IP}"
    EXT_SIGNAL_TCP="external_signaling_address=${EXTERNAL_IP}"
    EXT_MEDIA_WSS="external_media_address=${EXTERNAL_IP}"
    EXT_SIGNAL_WSS="external_signaling_address=${EXTERNAL_IP}"
else
    echo "🏠 [Asterisk Init] EXTERNAL_IP не задан — локальный режим, NAT-traversal отключён"
    EXT_MEDIA_UDP=""
    EXT_SIGNAL_UDP=""
    EXT_MEDIA_TCP=""
    EXT_SIGNAL_TCP=""
    EXT_MEDIA_WSS=""
    EXT_SIGNAL_WSS=""
fi

sed \
    -e "s|%%SYSTEM_PASS%%|${ASTERISK_SYSTEM_PASS}|g" \
    -e "s|%%SIP_PRO_001_PASS%%|${SIP_PRO_001_PASS}|g" \
    -e "s|%%SIP_GO_001_PASS%%|${SIP_GO_001_PASS}|g" \
    -e "s|%%SIP_PLUS_001_PASS%%|${SIP_PLUS_001_PASS}|g" \
    -e "s|%%SIP_EXPRESS_001_PASS%%|${SIP_EXPRESS_001_PASS}|g" \
    -e "s|%%EXTERNAL_MEDIA_UDP%%|${EXT_MEDIA_UDP}|g" \
    -e "s|%%EXTERNAL_SIGNALING_UDP%%|${EXT_SIGNAL_UDP}|g" \
    -e "s|%%EXTERNAL_MEDIA_TCP%%|${EXT_MEDIA_TCP}|g" \
    -e "s|%%EXTERNAL_SIGNALING_TCP%%|${EXT_SIGNAL_TCP}|g" \
    -e "s|%%EXTERNAL_MEDIA_WSS%%|${EXT_MEDIA_WSS}|g" \
    -e "s|%%EXTERNAL_SIGNALING_WSS%%|${EXT_SIGNAL_WSS}|g" \
    /etc/asterisk/pjsip.conf > /tmp/pjsip.conf.rendered
cp /tmp/pjsip.conf.rendered /etc/asterisk/pjsip.conf

# Очищаем временные файлы с секретами
rm -f /tmp/manager.conf.rendered /tmp/pjsip.conf.rendered

echo "✅ [Asterisk Init] Конфиги сгенерированы. Запуск Asterisk..."
