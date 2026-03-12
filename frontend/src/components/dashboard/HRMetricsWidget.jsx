import React, { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Users, AlertTriangle, Package, TrendingUp } from 'lucide-react'
import api from '../../api/client'

/**
 * S-GLOBAL DOMINION — HR-Метрики Widget
 * =======================================
 * Протокол: LOGIST-PAY v200.16.6
 * Аудит: ИП Мкртчян (IT Service Fee Controller)
 *
 * Показывает Мастеру:
 * - Текущая ЗП логиста (онлайн)
 * - Счётчик штрафов М4 за сегодня
 * - Статус возврата тары
 */

export default function HRMetricsWidget() {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchMetrics()
    // Обновляем каждые 60 секунд
    const interval = setInterval(fetchMetrics, 60000)
    return () => clearInterval(interval)
  }, [])

  async function fetchMetrics() {
    try {
      const res = await api.get('/api/v1/hr/logist-pay/dashboard')
      if (res.data?.status === 'success') {
        setMetrics(res.data.data)
        setError(null)
      }
    } catch (err) {
      // Если API недоступен — показываем mock-данные
      setMetrics({
        salary: { current_month: 130000, base: 130000, bonus: 0, fines_deducted: 0 },
        m4_fines: { today: 0, month_total: 0 },
        tara: { total_issued: 0, returned: 0, pending: 0, status: 'ok' },
        audit_entity: 'ИП Мкртчян',
        period: new Date().toISOString().slice(0, 7),
      })
      setError('offline')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 backdrop-blur-xl">
        <div className="flex items-center gap-2 animate-pulse">
          <div className="w-4 h-4 rounded bg-white/10" />
          <div className="h-3 w-32 rounded bg-white/10" />
        </div>
      </div>
    )
  }

  if (!metrics) return null

  const { salary, m4_fines, tara, audit_entity } = metrics

  // Цвет штрафов: зелёный если 0, жёлтый если 1-2, красный если 3+
  const finesColor = m4_fines.today === 0
    ? '#00ff88'
    : m4_fines.today <= 2
      ? '#f59e0b'
      : '#ef4444'

  // Цвет тары
  const taraColor = tara.status === 'ok'
    ? '#00ff88'
    : tara.status === 'warning'
      ? '#f59e0b'
      : '#ef4444'

  const taraLabel = tara.status === 'ok'
    ? 'НОРМА'
    : tara.status === 'warning'
      ? 'ВНИМАНИЕ'
      : 'КРИТИЧНО'

  return (
    <motion.div
      className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl overflow-hidden"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 1.4 }}
      style={{
        boxShadow: '0 4px 24px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.03)',
      }}
    >
      {/* Заголовок */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <Users size={14} className="text-[#d4a843]" />
          <span className="font-orbitron text-[10px] tracking-[0.3em] uppercase text-[#d4a843]">
            HR-МЕТРИКИ
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {error === 'offline' && (
            <span className="text-[9px] font-montserrat text-amber-400/60 tracking-wider">
              OFFLINE
            </span>
          )}
          <span className="text-[9px] font-montserrat text-white/30 tracking-wider">
            {audit_entity}
          </span>
        </div>
      </div>

      {/* Метрики */}
      <div className="grid grid-cols-3 divide-x divide-white/[0.06]">
        {/* ЗП Логиста */}
        <div className="p-4 flex flex-col items-center gap-2">
          <div className="flex items-center gap-1">
            <TrendingUp size={12} className="text-[#00f5ff]/60" />
            <span className="text-[9px] font-orbitron tracking-[0.2em] uppercase text-white/40">
              ЗП ЛОГИСТА
            </span>
          </div>
          <span
            className="text-xl font-orbitron font-bold"
            style={{
              color: '#00f5ff',
              textShadow: '0 0 12px rgba(0,245,255,0.3)',
            }}
          >
            {(salary.current_month / 1000).toFixed(0)}K
          </span>
          <div className="flex flex-col items-center gap-0.5">
            <span className="text-[8px] font-montserrat text-white/30">
              База: {(salary.base / 1000).toFixed(0)}K
              {salary.bonus > 0 && ` + ${(salary.bonus / 1000).toFixed(0)}K`}
            </span>
            {salary.fines_deducted > 0 && (
              <span className="text-[8px] font-montserrat text-red-400/70">
                − {salary.fines_deducted.toLocaleString()}₽ штрафы
              </span>
            )}
          </div>
        </div>

        {/* Штрафы М4 */}
        <div className="p-4 flex flex-col items-center gap-2">
          <div className="flex items-center gap-1">
            <AlertTriangle size={12} style={{ color: `${finesColor}80` }} />
            <span className="text-[9px] font-orbitron tracking-[0.2em] uppercase text-white/40">
              ШТРАФЫ М4
            </span>
          </div>
          <span
            className="text-xl font-orbitron font-bold"
            style={{
              color: finesColor,
              textShadow: `0 0 12px ${finesColor}40`,
            }}
          >
            {m4_fines.today}
          </span>
          <span className="text-[8px] font-montserrat text-white/30">
            Сегодня · Месяц: {m4_fines.month_total}
          </span>
        </div>

        {/* Возврат тары */}
        <div className="p-4 flex flex-col items-center gap-2">
          <div className="flex items-center gap-1">
            <Package size={12} style={{ color: `${taraColor}80` }} />
            <span className="text-[9px] font-orbitron tracking-[0.2em] uppercase text-white/40">
              ТАРА
            </span>
          </div>
          <span
            className="text-xl font-orbitron font-bold"
            style={{
              color: taraColor,
              textShadow: `0 0 12px ${taraColor}40`,
            }}
          >
            {taraLabel}
          </span>
          <span className="text-[8px] font-montserrat text-white/30">
            Выдано: {tara.total_issued} · Возврат: {tara.returned}
          </span>
        </div>
      </div>
    </motion.div>
  )
}
