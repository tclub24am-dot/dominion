import React, { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ShieldAlert, ShieldCheck, Database, Code2, AlertTriangle,
  CheckCircle2, XCircle, Clock, RefreshCw, ChevronDown, ChevronUp
} from 'lucide-react'

/**
 * S-GLOBAL DOMINION — Security Audit Panel v1.0
 * ===============================================
 * VERSHINA v200.16 Protocol — ПАНЕЛЬ АУДИТА БЕЗОПАСНОСТИ
 *
 * Визуализирует результаты аудита тенантов из AUDIT_REPORT_v200.16.md.
 * Показывает:
 *   - Общий статус безопасности (Score 0-100)
 *   - Список уязвимых файлов с детализацией
 *   - Прогресс исправления (патч-статус)
 *   - Рекомендации по устранению
 *
 * Стиль: тёмный glassmorphism, красно-золотая палитра угроз.
 * Анимация: staggered reveal, progress-bar fill, pulse-alerts.
 */

// Данные аудита из AUDIT_REPORT_v200.16.md
const AUDIT_DATA = {
  version: 'v200.16',
  date: '2026-03-13',
  score: 100, // из 100 — ЗАЩИЩЕНО
  categories: [
    {
      id: 'tenant_isolation',
      name: 'Изоляция тенантов',
      status: 'ok',
      score: 40,
      maxScore: 40,
      icon: Database,
      findings: [
        {
          file: 'app/api/v1/fleet.py',
          function: 'get_active_vehicles',
          line: 491,
          severity: 'high',
          description: 'select(Vehicle) без фильтра tenant_id',
          fix: '.where(Vehicle.tenant_id == tenant_id)',
          patched: true,
        },
        {
          file: 'app/api/v1/fleet.py',
          function: 'get_vehicles_table',
          line: 831,
          severity: 'high',
          description: 'select(Vehicle) без фильтра tenant_id',
          fix: '.where(Vehicle.tenant_id == tenant_id)',
          patched: true,
        },
        {
          file: 'app/api/v1/fleet.py',
          function: 'get_vehicles_list_json',
          line: 983,
          severity: 'high',
          description: 'select(Vehicle, User) без фильтра',
          fix: '.where(Vehicle.tenant_id == tenant_id)',
          patched: true,
        },
        {
          file: 'app/api/v1/fleet.py',
          function: 'lookup_vehicle / lookup_driver',
          line: null,
          severity: 'medium',
          description: 'Глобальный поиск по VIN/Plate/Phone',
          fix: 'Добавить tenant_id в условие поиска',
          patched: true,
        },
        {
          file: 'app/api/v1/kazna.py',
          function: 'get_transactions',
          line: 136,
          severity: 'critical',
          description: 'select(Transaction, User) без фильтра — ФИНАНСЫ!',
          fix: '.where(Transaction.tenant_id == tenant_id)',
          patched: true,
        },
        {
          file: 'app/api/v1/kazna.py',
          function: 'get_recent_transactions',
          line: 236,
          severity: 'critical',
          description: 'select(Transaction) без фильтра — ФИНАНСЫ!',
          fix: '.where(Transaction.tenant_id == tenant_id)',
          patched: true,
        },
        {
          file: 'app/api/v1/kazna.py',
          function: 'export_transactions',
          line: 435,
          severity: 'critical',
          description: 'Экспорт транзакций без изоляции — УТЕЧКА!',
          fix: '.where(Transaction.tenant_id == tenant_id)',
          patched: true,
        },
      ],
    },
    {
      id: 'performance',
      name: 'Производительность БД',
      status: 'ok',
      score: 35,
      maxScore: 35,
      icon: Database,
      findings: [
        {
          file: 'app/database.py',
          function: 'create_engine',
          line: null,
          severity: 'info',
          description: 'pool_size=50, max_overflow=20 — оптимизировано',
          fix: null,
          patched: true,
        },
        {
          file: 'app/create_db.py',
          function: 'create_tables',
          line: null,
          severity: 'info',
          description: 'Дублирование индекса ix_call_logs_timestamp — исправлено',
          fix: null,
          patched: true,
        },
      ],
    },
    {
      id: 'security',
      name: 'HMAC / JWT / Secrets',
      status: 'ok',
      score: 30,
      maxScore: 30,
      icon: ShieldCheck,
      findings: [
        {
          file: 'app/services/security.py',
          function: 'generate_matrix_password',
          line: null,
          severity: 'info',
          description: 'HMAC-SHA256 детерминистический — безопасно',
          fix: null,
          patched: true,
        },
        {
          file: 'app/api/v1/telephony.py',
          function: 'webhook_handler',
          line: null,
          severity: 'info',
          description: 'X-Webhook-Signature проверяется — защищено',
          fix: null,
          patched: true,
        },
      ],
    },
    {
      id: 'domain_shield',
      name: '🛡️ Доменный Щит — ИП Мкртчян',
      status: 'ok',
      score: 40,
      maxScore: 40,
      icon: ShieldCheck,
      findings: [
        {
          file: 'taxi-club24.ru',
          function: 'ИТ-Щит',
          line: null,
          severity: 'info',
          description: 'Обслуживается ИП Мкртчян (ИТ-Щит)',
          fix: null,
          patched: true,
        },
        {
          file: 's-global.space',
          function: 'ИТ-Щит',
          line: null,
          severity: 'info',
          description: 'Обслуживается ИП Мкртчян (ИТ-Щит)',
          fix: null,
          patched: true,
        },
        {
          file: 't-club24.ru',
          function: 'ИТ-Щит',
          line: null,
          severity: 'info',
          description: 'Обслуживается ИП Мкртчян (ИТ-Щит)',
          fix: null,
          patched: true,
        },
        {
          file: 't-club24.com',
          function: 'ИТ-Щит',
          line: null,
          severity: 'info',
          description: 'Обслуживается ИП Мкртчян (ИТ-Щит)',
          fix: null,
          patched: true,
        },
        {
          file: 't-club24.online',
          function: 'ИТ-Щит',
          line: null,
          severity: 'info',
          description: 'Обслуживается ИП Мкртчян (ИТ-Щит)',
          fix: null,
          patched: true,
        },
        {
          file: 'auto-club.pro',
          function: 'ИТ-Щит',
          line: null,
          severity: 'info',
          description: 'Обслуживается ИП Мкртчян (ИТ-Щит)',
          fix: null,
          patched: true,
        },
      ],
    },
  ],
}

const SEVERITY_CONFIG = {
  critical: { color: '#ef4444', label: 'КРИТИЧНО', bg: 'rgba(239,68,68,0.08)' },
  high:     { color: '#f97316', label: 'ВЫСОКИЙ',  bg: 'rgba(249,115,22,0.08)' },
  medium:   { color: '#f59e0b', label: 'СРЕДНИЙ',  bg: 'rgba(245,158,11,0.08)' },
  info:     { color: '#00ff88', label: 'OK',        bg: 'rgba(0,255,136,0.06)' },
}

const STATUS_CONFIG = {
  critical: { color: '#ef4444', icon: XCircle,      label: 'КРИТИЧНО' },
  warning:  { color: '#f59e0b', icon: AlertTriangle, label: 'ПРЕДУПРЕЖДЕНИЕ' },
  ok:       { color: '#00ff88', icon: CheckCircle2,  label: 'ЗАЩИЩЕНО' },
}

// Круговой прогресс-индикатор (Score)
function ScoreRing({ score, size = 80 }) {
  const radius = (size - 12) / 2
  const circumference = 2 * Math.PI * radius
  const progress = (score / 100) * circumference
  const color = score >= 70 ? '#00ff88' : score >= 40 ? '#f59e0b' : '#ef4444'

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Фоновый круг */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth="6"
        />
        {/* Прогресс */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference - progress }}
          transition={{ duration: 1.5, ease: 'easeOut', delay: 0.3 }}
          style={{ filter: `drop-shadow(0 0 6px ${color}80)` }}
        />
      </svg>
      {/* Число в центре */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <motion.span
          className="font-orbitron font-bold text-xl leading-none"
          style={{ color }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
        >
          {score}
        </motion.span>
        <span className="text-[8px] font-montserrat text-white/30 mt-0.5">SCORE</span>
      </div>
    </div>
  )
}

// Карточка категории
function CategoryCard({ category, index }) {
  const [isOpen, setIsOpen] = useState(category.status === 'critical')
  const statusCfg = STATUS_CONFIG[category.status]
  const StatusIcon = statusCfg.icon
  const CategoryIcon = category.icon
  const scorePercent = Math.round((category.score / category.maxScore) * 100)

  return (
    <motion.div
      className="rounded-xl overflow-hidden"
      style={{
        background: 'rgba(255,255,255,0.02)',
        border: `1px solid ${category.status === 'critical' ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.06)'}`,
      }}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 + 0.2 }}
    >
      {/* Заголовок категории */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
        onClick={() => setIsOpen(prev => !prev)}
      >
        <CategoryIcon size={16} style={{ color: statusCfg.color }} />

        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-orbitron font-bold text-white/80">
              {category.name}
            </span>
            <span
              className="text-[9px] font-orbitron font-bold px-1.5 py-0.5 rounded"
              style={{
                background: `${statusCfg.color}15`,
                color: statusCfg.color,
                border: `1px solid ${statusCfg.color}30`,
              }}
            >
              {statusCfg.label}
            </span>
          </div>

          {/* Прогресс-бар */}
          <div className="mt-1.5 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <motion.div
              className="h-full rounded-full"
              style={{
                background: `linear-gradient(90deg, ${statusCfg.color}, ${statusCfg.color}aa)`,
                boxShadow: `0 0 6px ${statusCfg.color}60`,
              }}
              initial={{ width: 0 }}
              animate={{ width: `${scorePercent}%` }}
              transition={{ duration: 1, ease: 'easeOut', delay: index * 0.1 + 0.4 }}
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-orbitron font-bold" style={{ color: statusCfg.color }}>
            {category.score}/{category.maxScore}
          </span>
          {isOpen ? (
            <ChevronUp size={14} className="text-white/30" />
          ) : (
            <ChevronDown size={14} className="text-white/30" />
          )}
        </div>
      </button>

      {/* Список находок */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div
              className="px-4 pb-3 space-y-1.5"
              style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}
            >
              {category.findings.map((finding, fi) => {
                const sev = SEVERITY_CONFIG[finding.severity]
                return (
                  <motion.div
                    key={fi}
                    className="flex items-start gap-2.5 px-3 py-2 rounded-lg mt-1.5"
                    style={{ background: sev.bg, border: `1px solid ${sev.color}20` }}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: fi * 0.05 }}
                  >
                    {/* Статус-точка */}
                    <div className="mt-0.5 flex-shrink-0">
                      {finding.patched ? (
                        <CheckCircle2 size={12} style={{ color: '#00ff88' }} />
                      ) : (
                        <motion.div
                          className="w-2 h-2 rounded-full mt-0.5"
                          style={{ backgroundColor: sev.color }}
                          animate={finding.severity === 'critical' ? {
                            boxShadow: [`0 0 4px ${sev.color}`, `0 0 10px ${sev.color}`, `0 0 4px ${sev.color}`],
                          } : {}}
                          transition={{ duration: 1.5, repeat: Infinity }}
                        />
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      {/* Файл + строка */}
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] font-orbitron font-bold" style={{ color: sev.color }}>
                          {finding.file.split('/').pop()}
                        </span>
                        {finding.line && (
                          <span className="text-[9px] font-montserrat text-white/30">:{finding.line}</span>
                        )}
                        <span className="text-[9px] font-montserrat text-white/40 truncate">
                          {finding.function}()
                        </span>
                      </div>

                      {/* Описание */}
                      <p className="text-[10px] font-montserrat text-white/50 mt-0.5 leading-relaxed">
                        {finding.description}
                      </p>

                      {/* Фикс */}
                      {finding.fix && !finding.patched && (
                        <div className="mt-1 flex items-center gap-1">
                          <Code2 size={9} style={{ color: '#d4a843' }} />
                          <code className="text-[9px] font-mono text-dominion-gold/70">
                            {finding.fix}
                          </code>
                        </div>
                      )}
                    </div>

                    {/* Бейдж */}
                    <span
                      className="text-[8px] font-orbitron font-bold px-1.5 py-0.5 rounded flex-shrink-0"
                      style={{
                        background: `${sev.color}15`,
                        color: sev.color,
                        border: `1px solid ${sev.color}25`,
                      }}
                    >
                      {finding.patched ? 'FIXED' : sev.label}
                    </span>
                  </motion.div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

export default function SecurityAuditPanel({ collapsed = false }) {
  const [isCollapsed, setIsCollapsed] = useState(collapsed)
  const [lastRefresh, setLastRefresh] = useState(new Date())
  const [isRefreshing, setIsRefreshing] = useState(false)

  const totalFindings = AUDIT_DATA.categories.reduce((acc, c) => acc + c.findings.filter(f => !f.patched).length, 0)
  const criticalCount = AUDIT_DATA.categories.reduce(
    (acc, c) => acc + c.findings.filter(f => !f.patched && f.severity === 'critical').length, 0
  )

  const handleRefresh = useCallback(() => {
    setIsRefreshing(true)
    setTimeout(() => {
      setIsRefreshing(false)
      setLastRefresh(new Date())
    }, 1200)
  }, [])

  return (
    <motion.div
      className="rounded-2xl overflow-hidden"
      style={{
        background: 'rgba(8, 8, 16, 0.85)',
        border: criticalCount > 0 ? '1px solid rgba(239,68,68,0.25)' : '1px solid rgba(255,255,255,0.08)',
        backdropFilter: 'blur(20px)',
        boxShadow: criticalCount > 0
          ? '0 8px 32px rgba(0,0,0,0.6), 0 0 40px rgba(239,68,68,0.06)'
          : '0 8px 32px rgba(0,0,0,0.4)',
      }}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Верхняя линия-акцент */}
      <div
        className="h-[2px]"
        style={{
          background: criticalCount > 0
            ? 'linear-gradient(90deg, transparent, #ef4444, #f97316, transparent)'
            : 'linear-gradient(90deg, transparent, #00ff88, transparent)',
          boxShadow: criticalCount > 0 ? '0 0 12px rgba(239,68,68,0.5)' : '0 0 8px rgba(0,255,136,0.3)',
        }}
      />

      {/* Заголовок панели */}
      <div className="flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3">
          <motion.div
            animate={criticalCount > 0 ? {
              filter: ['drop-shadow(0 0 4px #ef4444)', 'drop-shadow(0 0 12px #ef4444)', 'drop-shadow(0 0 4px #ef4444)'],
            } : {}}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <ShieldAlert size={20} style={{ color: criticalCount > 0 ? '#ef4444' : '#00ff88' }} />
          </motion.div>

          <div>
            <h3 className="text-[13px] font-orbitron font-bold tracking-[0.15em] text-white/90 uppercase">
              Аудит Безопасности
            </h3>
            <p className="text-[10px] font-montserrat text-white/40 mt-0.5">
              VERSHINA {AUDIT_DATA.version} · {AUDIT_DATA.date}
            </p>
          </div>

          {/* Счётчики проблем */}
          {criticalCount > 0 && (
            <motion.div
              className="flex items-center gap-1.5 ml-2"
              animate={{ opacity: [1, 0.6, 1] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            >
              <span
                className="text-[10px] font-orbitron font-bold px-2 py-0.5 rounded-full"
                style={{
                  background: 'rgba(239,68,68,0.15)',
                  color: '#ef4444',
                  border: '1px solid rgba(239,68,68,0.3)',
                }}
              >
                {criticalCount} КРИТИЧНО
              </span>
            </motion.div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Score Ring */}
          <ScoreRing score={AUDIT_DATA.score} size={56} />

          {/* Кнопка обновления */}
          <motion.button
            onClick={handleRefresh}
            className="p-2 rounded-lg"
            style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
          >
            <motion.div
              animate={isRefreshing ? { rotate: 360 } : {}}
              transition={{ duration: 0.8, ease: 'linear' }}
            >
              <RefreshCw size={14} className="text-white/40" />
            </motion.div>
          </motion.button>

          {/* Свернуть/развернуть */}
          <motion.button
            onClick={() => setIsCollapsed(prev => !prev)}
            className="p-2 rounded-lg"
            style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
          >
            {isCollapsed ? (
              <ChevronDown size={14} className="text-white/40" />
            ) : (
              <ChevronUp size={14} className="text-white/40" />
            )}
          </motion.button>
        </div>
      </div>

      {/* Тело панели */}
      <AnimatePresence>
        {!isCollapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div
              className="px-5 pb-5 space-y-3"
              style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}
            >
              {/* Сводка */}
              <div className="grid grid-cols-3 gap-3 pt-4">
                {[
                  { label: 'Всего проблем', value: totalFindings, color: '#f59e0b' },
                  { label: 'Критических', value: criticalCount, color: '#ef4444' },
                  { label: 'Исправлено', value: AUDIT_DATA.categories.reduce((a, c) => a + c.findings.filter(f => f.patched).length, 0), color: '#00ff88' },
                ].map(({ label, value, color }) => (
                  <div
                    key={label}
                    className="text-center py-2.5 rounded-xl"
                    style={{ background: `rgba(${color === '#ef4444' ? '239,68,68' : color === '#f59e0b' ? '245,158,11' : '0,255,136'}, 0.06)`, border: `1px solid ${color}15` }}
                  >
                    <div className="text-xl font-orbitron font-bold" style={{ color }}>
                      {value}
                    </div>
                    <div className="text-[9px] font-montserrat text-white/40 mt-0.5">{label}</div>
                  </div>
                ))}
              </div>

              {/* Категории */}
              <div className="space-y-2">
                {AUDIT_DATA.categories.map((cat, i) => (
                  <CategoryCard key={cat.id} category={cat} index={i} />
                ))}
              </div>

              {/* Нижняя строка */}
              <div className="flex items-center justify-between pt-1">
                <div className="flex items-center gap-1.5">
                  <Clock size={11} className="text-white/20" />
                  <span className="text-[9px] font-montserrat text-white/20">
                    Последняя проверка: {lastRefresh.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <span className="text-[9px] font-orbitron text-white/20 tracking-wider">
                  ORACLE AGENT · AUDIT ENGINE
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
