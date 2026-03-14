import React, { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Car, Zap, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import api from '../../api/client'

/**
 * S-GLOBAL DOMINION — Live Fleet Counter v1.0
 * =============================================
 * VERSHINA v200.16 Protocol — ЖИВОЙ ФЛОТ
 *
 * Real-time счётчик активных машин на линии.
 * Подключается к /api/v1/fleet/live-stats каждые 15 секунд.
 * Анимирует изменение числа (flip-counter эффект).
 * Показывает тренд: ↑ больше машин, ↓ меньше, — стабильно.
 *
 * Стиль: золотой неон, glassmorphism, Orbitron-шрифт.
 */

// Анимированный цифровой счётчик (flip-эффект)
function FlipNumber({ value, color = '#d4a843' }) {
  const [displayValue, setDisplayValue] = useState(value)
  const [isFlipping, setIsFlipping] = useState(false)
  const prevValue = useRef(value)

  useEffect(() => {
    if (value !== prevValue.current) {
      setIsFlipping(true)
      const timer = setTimeout(() => {
        setDisplayValue(value)
        setIsFlipping(false)
        prevValue.current = value
      }, 150)
      return () => clearTimeout(timer)
    }
  }, [value])

  return (
    <motion.span
      className="font-orbitron font-bold tabular-nums"
      style={{ color }}
      animate={{
        opacity: isFlipping ? [1, 0, 1] : 1,
        y: isFlipping ? [0, -4, 0] : 0,
        filter: isFlipping
          ? [`drop-shadow(0 0 8px ${color})`, `drop-shadow(0 0 20px ${color})`, `drop-shadow(0 0 8px ${color})`]
          : `drop-shadow(0 0 6px ${color}60)`,
      }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
    >
      {displayValue}
    </motion.span>
  )
}

// Мини-спарклайн (последние 8 значений)
function SparkLine({ data, color = '#d4a843', width = 80, height = 24 }) {
  if (!data || data.length < 2) return null

  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((v - min) / range) * (height - 4) - 2
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={`spark-grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Заливка под линией */}
      <polyline
        points={`0,${height} ${points} ${width},${height}`}
        fill={`url(#spark-grad-${color.replace('#', '')})`}
        stroke="none"
      />
      {/* Линия */}
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ filter: `drop-shadow(0 0 3px ${color}80)` }}
      />
      {/* Последняя точка */}
      <circle
        cx={(data.length - 1) / (data.length - 1) * width}
        cy={height - ((data[data.length - 1] - min) / range) * (height - 4) - 2}
        r="2.5"
        fill={color}
        style={{ filter: `drop-shadow(0 0 4px ${color})` }}
      />
    </svg>
  )
}

export default function LiveFleetCounter({ parkName = 'PRO', compact = false }) {
  const [stats, setStats] = useState({
    active: 0,
    total: 41,
    on_trip: 0,
    idle: 0,
    offline: 0,
  })
  const [history, setHistory] = useState([0, 0, 0, 0, 0, 0, 0, 0])
  const [trend, setTrend] = useState('stable') // 'up' | 'down' | 'stable'
  const [isLoading, setIsLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState(null)
  const prevActive = useRef(0)

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get(`/api/v1/fleet/live-stats?park_name=${parkName}`)
      if (res.data) {
        const newActive = res.data.active ?? res.data.on_line ?? 0
        const newStats = {
          active: newActive,
          total: res.data.total ?? 41,
          on_trip: res.data.on_trip ?? 0,
          idle: res.data.idle ?? 0,
          offline: res.data.offline ?? 0,
        }
        setStats(newStats)
        setHistory(prev => [...prev.slice(-7), newActive])

        // Определяем тренд
        if (newActive > prevActive.current) setTrend('up')
        else if (newActive < prevActive.current) setTrend('down')
        else setTrend('stable')
        prevActive.current = newActive
      }
    } catch {
      // TODO: подключить к API /api/v1/fleet/active-vehicles
      // При недоступности API — сохраняем последнее известное значение (не генерируем mock)
      setHistory(prev => [...prev.slice(-7), prevActive.current])
    } finally {
      setIsLoading(false)
      setLastUpdate(new Date())
    }
  }, [parkName])

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 15000)
    return () => clearInterval(interval)
  }, [fetchStats])

  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus
  const trendColor = trend === 'up' ? '#00ff88' : trend === 'down' ? '#ef4444' : '#8888aa'
  const activePercent = stats.total > 0 ? Math.round((stats.active / stats.total) * 100) : 0

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <Car size={14} style={{ color: '#d4a843' }} />
        <FlipNumber value={stats.active} color="#d4a843" />
        <span className="text-[10px] font-montserrat text-white/40">/ {stats.total}</span>
        <TrendIcon size={12} style={{ color: trendColor }} />
      </div>
    )
  }

  return (
    <motion.div
      className="relative rounded-xl overflow-hidden"
      style={{
        background: 'rgba(10, 10, 20, 0.7)',
        border: '1px solid rgba(212, 168, 67, 0.2)',
        backdropFilter: 'blur(16px)',
      }}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      {/* Верхняя золотая линия */}
      <div
        className="absolute top-0 left-0 right-0 h-[1px]"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(212,168,67,0.6), transparent)' }}
      />

      <div className="p-4">
        {/* Заголовок */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <motion.div
              animate={{ rotate: [0, 5, -5, 0] }}
              transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Car size={16} style={{ color: '#d4a843' }} />
            </motion.div>
            <span className="text-[11px] font-orbitron font-bold tracking-[0.2em] text-dominion-gold uppercase">
              ФЛОТ {parkName}
            </span>
          </div>

          {/* Индикатор live */}
          <div className="flex items-center gap-1.5">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-400" />
            </span>
            <span className="text-[9px] font-orbitron text-green-400/70 tracking-wider">LIVE</span>
          </div>
        </div>

        {/* Главный счётчик */}
        <div className="flex items-end gap-3 mb-3">
          <div>
            <div className="flex items-baseline gap-1">
              <span className="text-4xl">
                <FlipNumber value={stats.active} color="#d4a843" />
              </span>
              <span className="text-lg font-orbitron text-white/30">/{stats.total}</span>
            </div>
            <div className="text-[10px] font-montserrat text-white/40 mt-0.5">
              машин на линии
            </div>
          </div>

          {/* Спарклайн */}
          <div className="ml-auto mb-1">
            <SparkLine data={history} color="#d4a843" width={72} height={28} />
          </div>
        </div>

        {/* Прогресс-бар загрузки флота */}
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[9px] font-montserrat text-white/40">Загрузка флота</span>
            <div className="flex items-center gap-1">
              <TrendIcon size={10} style={{ color: trendColor }} />
              <span className="text-[10px] font-orbitron font-bold" style={{ color: trendColor }}>
                {activePercent}%
              </span>
            </div>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <motion.div
              className="h-full rounded-full"
              style={{
                background: activePercent > 70
                  ? 'linear-gradient(90deg, #00ff88, #00cc66)'
                  : activePercent > 40
                    ? 'linear-gradient(90deg, #d4a843, #f0c060)'
                    : 'linear-gradient(90deg, #ef4444, #ff6b6b)',
                boxShadow: `0 0 8px ${activePercent > 70 ? '#00ff88' : activePercent > 40 ? '#d4a843' : '#ef4444'}60`,
              }}
              initial={{ width: 0 }}
              animate={{ width: `${activePercent}%` }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
            />
          </div>
        </div>

        {/* Детальная разбивка */}
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: 'В ПОЕЗДКЕ', value: stats.on_trip, color: '#00ff88' },
            { label: 'ОЖИДАНИЕ', value: stats.idle, color: '#f59e0b' },
            { label: 'ОФЛАЙН', value: stats.offline, color: '#8888aa' },
          ].map(({ label, value, color }) => (
            <div
              key={label}
              className="text-center py-1.5 rounded-lg"
              style={{ background: `rgba(${color === '#00ff88' ? '0,255,136' : color === '#f59e0b' ? '245,158,11' : '136,136,170'}, 0.06)` }}
            >
              <div className="text-[13px] font-orbitron font-bold" style={{ color }}>
                {value}
              </div>
              <div className="text-[8px] font-montserrat tracking-wider" style={{ color: `${color}80` }}>
                {label}
              </div>
            </div>
          ))}
        </div>

        {/* Время последнего обновления */}
        {lastUpdate && (
          <div className="mt-2 text-center">
            <span className="text-[9px] font-montserrat text-white/20">
              обновлено {lastUpdate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          </div>
        )}
      </div>
    </motion.div>
  )
}
