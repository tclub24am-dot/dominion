import React, { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ShieldCheck, ShieldAlert, ShieldOff, Lock, Unlock } from 'lucide-react'
import api from '../../api/client'

/**
 * S-GLOBAL DOMINION — Tenant Security Badge v1.0
 * ================================================
 * VERSHINA v200.16 Protocol — АУДИТ БЕЗОПАСНОСТИ ТЕНАНТОВ
 *
 * Отображает статус изоляции данных тенанта в реальном времени.
 * Три состояния:
 *   🟢 SECURE   — все запросы фильтруются по tenant_id
 *   🟡 WARNING  — обнаружены незащищённые эндпоинты (fleet.py / kazna.py)
 *   🔴 CRITICAL — активная утечка данных между тенантами
 *
 * Анимация: пульсирующий щит + всплывающая панель деталей при клике.
 * Стиль: Ivory Luxe / The Void — адаптивный через CSS-переменные.
 */

const SECURITY_LEVELS = {
  secure: {
    label: 'ИЗОЛЯЦИЯ АКТИВНА',
    sublabel: 'Все тенанты защищены',
    icon: ShieldCheck,
    color: '#00ff88',
    colorRgb: '0, 255, 136',
    bgColor: 'rgba(0, 255, 136, 0.08)',
    borderColor: 'rgba(0, 255, 136, 0.25)',
    pulseColor: 'rgba(0, 255, 136, 0.4)',
  },
  warning: {
    label: 'УЯЗВИМОСТЬ',
    sublabel: 'fleet.py / kazna.py без фильтра',
    icon: ShieldAlert,
    color: '#f59e0b',
    colorRgb: '245, 158, 11',
    bgColor: 'rgba(245, 158, 11, 0.08)',
    borderColor: 'rgba(245, 158, 11, 0.3)',
    pulseColor: 'rgba(245, 158, 11, 0.5)',
  },
  critical: {
    label: 'КРИТИЧЕСКАЯ УТЕЧКА',
    sublabel: 'Данные тенантов смешаны!',
    icon: ShieldOff,
    color: '#ef4444',
    colorRgb: '239, 68, 68',
    bgColor: 'rgba(239, 68, 68, 0.1)',
    borderColor: 'rgba(239, 68, 68, 0.4)',
    pulseColor: 'rgba(239, 68, 68, 0.6)',
  },
}

// Список уязвимых эндпоинтов из аудита v200.16
const AUDIT_FINDINGS = [
  { file: 'fleet.py', fn: 'get_active_vehicles', line: 491, status: 'warning' },
  { file: 'fleet.py', fn: 'get_vehicles_table', line: 831, status: 'warning' },
  { file: 'fleet.py', fn: 'get_vehicles_list_json', line: 983, status: 'warning' },
  { file: 'fleet.py', fn: 'lookup_vehicle', line: null, status: 'warning' },
  { file: 'kazna.py', fn: 'get_transactions', line: 136, status: 'critical' },
  { file: 'kazna.py', fn: 'get_recent_transactions', line: 236, status: 'critical' },
  { file: 'kazna.py', fn: 'export_transactions', line: 435, status: 'critical' },
]

export default function TenantSecurityBadge({ compact = false }) {
  const [securityLevel, setSecurityLevel] = useState('warning') // По умолчанию — предупреждение из аудита
  const [isExpanded, setIsExpanded] = useState(false)
  const [lastCheck, setLastCheck] = useState(null)
  const [tenantId, setTenantId] = useState(null)

  // Проверка статуса безопасности через API
  const checkSecurity = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/auth/me')
      if (res.data) {
        setTenantId(res.data.tenant_id || res.data.park_name || 'PRO')
        // Если API отвечает — базовая изоляция работает
        // Но аудит v200.16 показал уязвимости — ставим warning
        setSecurityLevel('warning')
      }
    } catch {
      // Нет доступа — не меняем статус
    } finally {
      setLastCheck(new Date())
    }
  }, [])

  useEffect(() => {
    checkSecurity()
    const interval = setInterval(checkSecurity, 30000)
    return () => clearInterval(interval)
  }, [checkSecurity])

  const level = SECURITY_LEVELS[securityLevel]
  const Icon = level.icon

  const criticalCount = AUDIT_FINDINGS.filter(f => f.status === 'critical').length
  const warningCount = AUDIT_FINDINGS.filter(f => f.status === 'warning').length

  if (compact) {
    return (
      <motion.button
        onClick={() => setIsExpanded(prev => !prev)}
        className="relative flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer"
        style={{
          background: level.bgColor,
          border: `1px solid ${level.borderColor}`,
        }}
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        title={`Безопасность тенанта: ${level.label}`}
      >
        {/* Пульсирующий индикатор */}
        <span className="relative flex h-2 w-2">
          <span
            className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
            style={{ backgroundColor: level.color }}
          />
          <span
            className="relative inline-flex rounded-full h-2 w-2"
            style={{ backgroundColor: level.color }}
          />
        </span>
        <Icon size={14} style={{ color: level.color }} />
        <span
          className="text-[10px] font-orbitron font-bold tracking-wider hidden sm:block"
          style={{ color: level.color }}
        >
          {securityLevel === 'secure' ? 'SECURE' : securityLevel === 'warning' ? 'AUDIT' : 'BREACH'}
        </span>
      </motion.button>
    )
  }

  return (
    <div className="relative">
      {/* Основная кнопка-бейдж */}
      <motion.button
        onClick={() => setIsExpanded(prev => !prev)}
        className="relative flex items-center gap-3 px-4 py-2.5 rounded-xl cursor-pointer overflow-hidden"
        style={{
          background: level.bgColor,
          border: `1px solid ${level.borderColor}`,
          backdropFilter: 'blur(12px)',
        }}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
      >
        {/* Фоновый sweep-эффект при ховере */}
        <motion.div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `linear-gradient(90deg, transparent, rgba(${level.colorRgb}, 0.05), transparent)`,
          }}
          initial={{ x: '-100%' }}
          whileHover={{ x: '100%' }}
          transition={{ duration: 0.6 }}
        />

        {/* Иконка с пульсацией */}
        <motion.div
          className="relative"
          animate={{
            filter: securityLevel !== 'secure'
              ? [`drop-shadow(0 0 4px ${level.color})`, `drop-shadow(0 0 10px ${level.color})`, `drop-shadow(0 0 4px ${level.color})`]
              : `drop-shadow(0 0 4px ${level.color})`,
          }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Icon size={18} style={{ color: level.color }} />
        </motion.div>

        {/* Текст */}
        <div className="text-left">
          <div
            className="text-[11px] font-orbitron font-bold tracking-[0.15em] uppercase"
            style={{ color: level.color }}
          >
            {level.label}
          </div>
          <div className="text-[10px] font-montserrat opacity-70" style={{ color: level.color }}>
            {tenantId ? `Тенант: ${tenantId}` : level.sublabel}
          </div>
        </div>

        {/* Счётчик проблем */}
        {securityLevel !== 'secure' && (
          <div className="ml-auto flex items-center gap-1.5">
            {criticalCount > 0 && (
              <span
                className="text-[10px] font-orbitron font-bold px-1.5 py-0.5 rounded"
                style={{
                  background: 'rgba(239, 68, 68, 0.15)',
                  color: '#ef4444',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                }}
              >
                {criticalCount}C
              </span>
            )}
            {warningCount > 0 && (
              <span
                className="text-[10px] font-orbitron font-bold px-1.5 py-0.5 rounded"
                style={{
                  background: 'rgba(245, 158, 11, 0.15)',
                  color: '#f59e0b',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                }}
              >
                {warningCount}W
              </span>
            )}
          </div>
        )}
      </motion.button>

      {/* Развёрнутая панель деталей */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            className="absolute top-full mt-2 left-0 z-50 rounded-xl overflow-hidden"
            style={{
              width: '340px',
              background: 'rgba(8, 8, 16, 0.96)',
              border: `1px solid ${level.borderColor}`,
              backdropFilter: 'blur(24px)',
              boxShadow: `0 16px 48px rgba(0,0,0,0.8), 0 0 32px rgba(${level.colorRgb}, 0.1)`,
            }}
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          >
            {/* Заголовок панели */}
            <div
              className="px-4 py-3 flex items-center justify-between"
              style={{ borderBottom: `1px solid rgba(${level.colorRgb}, 0.15)` }}
            >
              <div className="flex items-center gap-2">
                <Lock size={12} style={{ color: level.color }} />
                <span
                  className="text-[11px] font-orbitron font-bold tracking-[0.2em] uppercase"
                  style={{ color: level.color }}
                >
                  АУДИТ ТЕНАНТОВ v200.16
                </span>
              </div>
              {lastCheck && (
                <span className="text-[9px] font-montserrat text-white/30">
                  {lastCheck.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
            </div>

            {/* Список уязвимостей */}
            <div className="p-3 space-y-1.5 max-h-[280px] overflow-y-auto">
              {AUDIT_FINDINGS.map((finding, i) => (
                <motion.div
                  key={i}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg"
                  style={{
                    background: finding.status === 'critical'
                      ? 'rgba(239, 68, 68, 0.06)'
                      : 'rgba(245, 158, 11, 0.06)',
                    border: `1px solid ${finding.status === 'critical' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)'}`,
                  }}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                >
                  {/* Статус-точка */}
                  <span
                    className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor: finding.status === 'critical' ? '#ef4444' : '#f59e0b',
                      boxShadow: `0 0 6px ${finding.status === 'critical' ? '#ef4444' : '#f59e0b'}`,
                    }}
                  />

                  {/* Файл + функция */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="text-[10px] font-orbitron font-bold"
                        style={{ color: finding.status === 'critical' ? '#ef4444' : '#f59e0b' }}
                      >
                        {finding.file}
                      </span>
                      {finding.line && (
                        <span className="text-[9px] font-montserrat text-white/30">
                          :{finding.line}
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] font-montserrat text-white/50 truncate">
                      {finding.fn}()
                    </div>
                  </div>

                  {/* Бейдж */}
                  <span
                    className="text-[9px] font-orbitron font-bold px-1.5 py-0.5 rounded flex-shrink-0"
                    style={{
                      background: finding.status === 'critical' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)',
                      color: finding.status === 'critical' ? '#ef4444' : '#f59e0b',
                    }}
                  >
                    {finding.status === 'critical' ? 'КРИТИЧНО' : 'РИСК'}
                  </span>
                </motion.div>
              ))}
            </div>

            {/* Рекомендация */}
            <div
              className="px-4 py-3 flex items-start gap-2"
              style={{ borderTop: `1px solid rgba(${level.colorRgb}, 0.1)` }}
            >
              <Unlock size={12} className="mt-0.5 flex-shrink-0" style={{ color: '#d4a843' }} />
              <p className="text-[10px] font-montserrat text-white/50 leading-relaxed">
                Добавить <code className="text-dominion-gold font-bold">.where(Model.tenant_id == tenant_id)</code> во все запросы через <code className="text-dominion-gold">request.state.tenant_id</code>
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
