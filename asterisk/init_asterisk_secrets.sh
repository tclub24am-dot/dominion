#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — asterisk/init_asterisk_secrets.sh
# Протокол: VERSHINA v200.14
# Скрипт инициализации секретов Asterisk при старте контейнера.
#
# Заменяет плейсхолдеры %%VAR%% в конфигах на реальные значения
# из переменных окружения. Если переменная не задана — АВАРИЙНЫЙ СТОП.
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
sed \
    -e "s|%%SYSTEM_PASS%%|${ASTERISK_SYSTEM_PASS}|g" \
    -e "s|%%SIP_PRO_001_PASS%%|${SIP_PRO_001_PASS}|g" \
    -e "s|%%SIP_GO_001_PASS%%|${SIP_GO_001_PASS}|g" \
    -e "s|%%SIP_PLUS_001_PASS%%|${SIP_PLUS_001_PASS}|g" \
    -e "s|%%SIP_EXPRESS_001_PASS%%|${SIP_EXPRESS_001_PASS}|g" \
    /etc/asterisk/pjsip.conf > /tmp/pjsip.conf.rendered
cp /tmp/pjsip.conf.rendered /etc/asterisk/pjsip.conf

# Очищаем временные файлы с секретами
rm -f /tmp/manager.conf.rendered /tmp/pjsip.conf.rendered

echo "✅ [Asterisk Init] Конфиги сгенерированы. Запуск Asterisk..."
