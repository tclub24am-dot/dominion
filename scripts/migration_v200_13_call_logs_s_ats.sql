-- ============================================================
-- S-GLOBAL DOMINION — Migration v200.13
-- S-АТС: Расширение таблицы call_logs для собственной телефонии
-- 
-- Автор: S-GLOBAL DOMINION Chief AI Architect
-- Дата: 2026-03-08
-- Протокол: VERSHINA v200.13
--
-- СТРАТЕГИЯ: Только ALTER TABLE — данные НЕ удаляются!
-- БЕЗОПАСНОСТЬ: Используй IF NOT EXISTS / IF EXISTS везде.
-- SAAS READY: Каждый звонок жёстко привязан к tenant_id.
-- ============================================================

BEGIN;

-- ============================================================
-- ШАГ 1: Переименование phone_number → caller_phone
-- (Обратная совместимость: старые данные сохраняются)
-- ============================================================
DO $$
BEGIN
    -- Проверяем: если phone_number ещё существует — переименовываем
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'call_logs' AND column_name = 'phone_number'
    ) THEN
        ALTER TABLE call_logs RENAME COLUMN phone_number TO caller_phone;
        RAISE NOTICE 'MIGRATION v200.13: phone_number → caller_phone [OK]';
    ELSE
        RAISE NOTICE 'MIGRATION v200.13: caller_phone уже существует, пропускаем переименование';
    END IF;
END $$;

-- ============================================================
-- ШАГ 2: Добавление новых полей S-АТС
-- ============================================================

-- tenant_id: SaaS-изоляция (КРИТИЧНО — должна быть добавлена ДО создания индексов!)
ALTER TABLE call_logs
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) NOT NULL DEFAULT 's-global';

-- Обновляем существующие записи (на случай если колонка была добавлена без значения)
UPDATE call_logs SET tenant_id = 's-global' WHERE tenant_id IS NULL OR tenant_id = '';

-- callee_phone: Номер принимающего (S-АТС)
ALTER TABLE call_logs
    ADD COLUMN IF NOT EXISTS callee_phone VARCHAR(20) DEFAULT NULL;

-- call_status: Статус звонка (answered/missed/ended/new/unknown)
ALTER TABLE call_logs
    ADD COLUMN IF NOT EXISTS call_status VARCHAR(20) NOT NULL DEFAULT 'unknown';

-- duration: Длительность звонка в секундах
ALTER TABLE call_logs
    ADD COLUMN IF NOT EXISTS duration INTEGER NOT NULL DEFAULT 0;

-- recording_url: URL записи разговора (S-АТС)
ALTER TABLE call_logs
    ADD COLUMN IF NOT EXISTS recording_url TEXT DEFAULT NULL;

-- ============================================================
-- ШАГ 3: Создание индексов для высокой производительности
-- ============================================================

-- КРИТИЧНЫЙ составной индекс: мгновенный поиск водителя при входящем звонке
-- Используется в find_driver_by_phone() при каждом звонке
CREATE INDEX IF NOT EXISTS ix_call_logs_tenant_caller
    ON call_logs (tenant_id, caller_phone);

-- Индекс для сортировки истории звонков (DESC — последние первыми)
CREATE INDEX IF NOT EXISTS ix_call_logs_timestamp
    ON call_logs (timestamp DESC);

-- Одиночный индекс на tenant_id (для фильтрации по тенанту)
-- Примечание: уже должен существовать из предыдущей версии
CREATE INDEX IF NOT EXISTS ix_call_logs_tenant_id
    ON call_logs (tenant_id);

-- ============================================================
-- ШАГ 4: Верификация результата
-- ============================================================

-- Проверка структуры таблицы
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'call_logs'
ORDER BY ordinal_position;

-- Проверка индексов
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'call_logs'
ORDER BY indexname;

COMMIT;

-- ============================================================
-- ROLLBACK SCRIPT (если нужно откатить v200.13)
-- ВНИМАНИЕ: Данные в новых полях будут потеряны!
-- ============================================================
-- BEGIN;
-- DROP INDEX IF EXISTS ix_call_logs_tenant_caller;
-- DROP INDEX IF EXISTS ix_call_logs_timestamp;
-- ALTER TABLE call_logs DROP COLUMN IF EXISTS recording_url;
-- ALTER TABLE call_logs DROP COLUMN IF EXISTS duration;
-- ALTER TABLE call_logs DROP COLUMN IF EXISTS call_status;
-- ALTER TABLE call_logs DROP COLUMN IF EXISTS callee_phone;
-- ALTER TABLE call_logs RENAME COLUMN caller_phone TO phone_number;
-- COMMIT;
