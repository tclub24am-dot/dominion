import React, { useEffect, useState, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowLeft, RefreshCw, AlertCircle, Loader2,
  TrendingUp, DollarSign, Building2, User,
  Truck, ChevronLeft, ChevronRight, Calculator,
  Database, CheckCircle2, XCircle, Clock
} from 'lucide-react'
import api from '../api/client'
import MIKSTerminal from '../components/miks/MIKSTerminal'

/**
 * S-GLOBAL DOMINION — Logistics Page v200.29.2
 * =============================================
 * Сектор LG — Логистика ВКУСВИЛЛ
 * Партнёрство 50/50: ООО С-ГЛОБАЛ + ИП МКРТЧЯН
 */

// ─── Утилиты ──────────────────────────────────────────────────────────────────

const fmt = (num) =>
  num !== null && num !== undefined
    ? new Intl.NumberFormat('ru-RU').format(Number(num)) + ' ₽'
    : '— ₽'

const fmtNum = (num) =>
  num !== null && num !== undefined
    ? new Intl.NumberFormat('ru-RU').format(Number(num))
    : '—'

// ─── Цветовая кодировка типов рейсов ──────────────────────────────────────────

const ROUTE_TYPE_CONFIG = {
  darkstore: {
    label: 'ДС',
    fullLabel: 'Даркстор',
    color: '#3b82f6',
    bg: 'rgba(59,130,246,0.15)',
    border: 'rgba(59,130,246,0.4)',
  },
  store: {
    label: 'МГ',
    fullLabel: 'Магазин',
    color: '#22c55e',
    bg: 'rgba(34,197,94,0.15)',
    border: 'rgba(34,197,94,0.4)',
  },
  shmel: {
    label: 'ШМ',
    fullLabel: 'Шмель',
    color: '#eab308',
    bg: 'rgba(234,179,8,0.15)',
    border: 'rgba(234,179,8,0.4)',
  },
  zhuk: {
    label: 'ЖУК',
    fullLabel: 'Жук',
    color: '#ef4444',
    bg: 'rgba(239,68,68,0.15)',
    border: 'rgba(239,68,68,0.4)',
  },
}

const getRouteType = (type) =>
  ROUTE_TYPE_CONFIG[type] || {
    label: type?.toUpperCase() || '?',
    fullLabel: type || 'Неизвестно',
    color: '#ffffff60',
    bg: 'rgba(255,255,255,0.06)',
    border: 'rgba(255,255,255,0.15)',
  }

const STATUS_CONFIG = {
  completed: { label: 'Выполнен', color: '#22c55e', icon: CheckCircle2 },
  in_progress: { label: 'В пути', color: '#d4a843', icon: Clock },
  cancelled: { label: 'Отменён', color: '#ef4444', icon: XCircle },
}

const getStatus = (status) =>
  STATUS_CONFIG[status] || { label: status || '—', color: '#ffffff40', icon: Clock }

// ─── KPI Карточка ─────────────────────────────────────────────────────────────

function KpiCard({ icon: Icon, label, value, color, delay = 0 }) {
  return (
    <motion.div
      className="flex-1 min-w-[200px] p-5 rounded-xl border"
      style={{
        background: 'rgba(255,255,255,0.03)',
        borderColor: `${color}30`,
        boxShadow: `0 0 20px ${color}08`,
      }}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
    >
      <div className="flex items-center gap-3 mb-3">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center"
          style={{ background: `${color}15`, border: `1px solid ${color}30` }}
        >
          <Icon size={18} style={{ color }} />
        </div>
        <span
          className="text-[10px] font-orbitron tracking-[0.2em] uppercase"
          style={{ color: `${color}80` }}
        >
          {label}
        </span>
      </div>
      <div
        className="text-[22px] font-orbitron font-bold tracking-wider"
        style={{ color }}
      >
        {value}
      </div>
    </motion.div>
  )
}

// ─── Бейдж типа рейса ─────────────────────────────────────────────────────────

function RouteTypeBadge({ type }) {
  const cfg = getRouteType(type)
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-orbitron font-bold tracking-wider"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.color }}
    >
      {cfg.label}
    </span>
  )
}

// ─── Бейдж статуса ────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const cfg = getStatus(status)
  const Icon = cfg.icon
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-montserrat"
      style={{ color: cfg.color }}
    >
      <Icon size={10} />
      {cfg.label}
    </span>
  )
}

// ─── Таблица рейсов ───────────────────────────────────────────────────────────

const PAGE_SIZE = 20

function RoutesTable({ routes, loading }) {
  const [page, setPage] = useState(1)
  const [filterDate, setFilterDate] = useState('')
  const [filterDriver, setFilterDriver] = useState('')
  const [filterType, setFilterType] = useState('')

  // Уникальные водители для фильтра
  const drivers = [...new Set(routes.map((r) => r.driver_name).filter(Boolean))].sort()

  // Фильтрация
  const filtered = routes.filter((r) => {
    if (filterDate && r.date !== filterDate) return false
    if (filterDriver && r.driver_name !== filterDriver) return false
    if (filterType && r.route_type !== filterType) return false
    return true
  })

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageData = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  const handleFilterChange = (setter) => (e) => {
    setter(e.target.value)
    setPage(1)
  }

  const inputStyle = {
    background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(212,168,67,0.2)',
    borderRadius: '6px',
    color: '#f5f0e8',
    padding: '6px 10px',
    fontSize: '11px',
    fontFamily: 'Montserrat, sans-serif',
    outline: 'none',
  }

  const selectStyle = {
    ...inputStyle,
    cursor: 'pointer',
  }

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{
        background: 'rgba(255,255,255,0.02)',
        borderColor: 'rgba(212,168,67,0.15)',
      }}
    >
      {/* Заголовок + фильтры */}
      <div
        className="px-5 py-4 border-b flex flex-wrap items-center gap-3"
        style={{ borderColor: 'rgba(212,168,67,0.1)' }}
      >
        <div className="flex items-center gap-2 mr-auto">
          <Truck size={14} style={{ color: '#00ff88' }} />
          <span className="text-[11px] font-orbitron tracking-wider" style={{ color: '#00ff88' }}>
            РЕЙСЫ · {filtered.length} записей
          </span>
        </div>

        {/* Фильтр по дате */}
        <input
          type="date"
          value={filterDate}
          onChange={handleFilterChange(setFilterDate)}
          style={inputStyle}
          title="Фильтр по дате"
        />

        {/* Фильтр по водителю */}
        <select
          value={filterDriver}
          onChange={handleFilterChange(setFilterDriver)}
          style={selectStyle}
        >
          <option value="">Все водители</option>
          {drivers.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        {/* Фильтр по типу */}
        <select
          value={filterType}
          onChange={handleFilterChange(setFilterType)}
          style={selectStyle}
        >
          <option value="">Все типы</option>
          <option value="darkstore">Даркстор</option>
          <option value="store">Магазин</option>
          <option value="shmel">Шмель</option>
          <option value="zhuk">Жук</option>
        </select>
      </div>

      {/* Таблица */}
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr style={{ background: 'rgba(212,168,67,0.08)' }}>
              {['Дата', 'Маршрут', 'Тип', 'Водитель', 'Выручка', 'Выплата', 'Маржа', 'Статус'].map((h) => (
                <th
                  key={h}
                  className="px-4 py-3 text-left font-orbitron tracking-wider text-[10px] uppercase whitespace-nowrap"
                  style={{ color: '#d4a843', borderBottom: '1px solid rgba(212,168,67,0.15)' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="text-center py-12">
                  <div className="flex items-center justify-center gap-3">
                    <motion.div
                      className="w-6 h-6 rounded-full border-2"
                      style={{ borderColor: 'rgba(0,255,136,0.2)', borderTopColor: '#00ff88' }}
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    />
                    <span className="text-[11px] font-orbitron" style={{ color: '#00ff8860' }}>
                      ЗАГРУЗКА...
                    </span>
                  </div>
                </td>
              </tr>
            ) : pageData.length === 0 ? (
              <tr>
                <td colSpan={8} className="text-center py-12">
                  <span className="text-[12px] font-montserrat" style={{ color: '#ffffff30' }}>
                    Рейсы не найдены
                  </span>
                </td>
              </tr>
            ) : (
              pageData.map((route, i) => (
                <motion.tr
                  key={route.id}
                  className="border-b transition-colors"
                  style={{ borderColor: 'rgba(255,255,255,0.04)' }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.02 }}
                  whileHover={{ backgroundColor: 'rgba(212,168,67,0.04)' }}
                >
                  <td className="px-4 py-3 font-montserrat whitespace-nowrap" style={{ color: '#ffffff60' }}>
                    {route.date || '—'}
                  </td>
                  <td className="px-4 py-3 font-montserrat max-w-[200px]" style={{ color: '#f5f0e8' }}>
                    <span className="truncate block" title={route.route_code}>
                      {route.route_code || '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <RouteTypeBadge type={route.route_type} />
                  </td>
                  <td className="px-4 py-3 font-montserrat whitespace-nowrap" style={{ color: '#f5f0e8' }}>
                    <div>{route.driver_name || '—'}</div>
                    {route.driver_group && (
                      <div className="text-[10px]" style={{ color: '#ffffff40' }}>{route.driver_group}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 font-orbitron whitespace-nowrap" style={{ color: '#d4a843' }}>
                    {fmt(route.revenue)}
                  </td>
                  <td className="px-4 py-3 font-montserrat whitespace-nowrap" style={{ color: '#ffffff70' }}>
                    {fmt(route.driver_payment)}
                  </td>
                  <td
                    className="px-4 py-3 font-orbitron whitespace-nowrap"
                    style={{ color: route.margin >= 0 ? '#22c55e' : '#ef4444' }}
                  >
                    {fmt(route.margin)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={route.status} />
                  </td>
                </motion.tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Пагинация */}
      {totalPages > 1 && (
        <div
          className="px-5 py-3 flex items-center justify-between border-t"
          style={{ borderColor: 'rgba(212,168,67,0.1)' }}
        >
          <span className="text-[10px] font-montserrat" style={{ color: '#ffffff30' }}>
            Стр. {currentPage} из {totalPages} · {filtered.length} записей
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="w-7 h-7 rounded flex items-center justify-center transition-all disabled:opacity-30"
              style={{ border: '1px solid rgba(212,168,67,0.2)', color: '#d4a843' }}
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="w-7 h-7 rounded flex items-center justify-center transition-all disabled:opacity-30"
              style={{ border: '1px solid rgba(212,168,67,0.2)', color: '#d4a843' }}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Калькулятор рейса ────────────────────────────────────────────────────────

function RouteCalculator() {
  const [form, setForm] = useState({
    route_type: 'darkstore',
    driver_group: 'BNYAN',
    delivery_points: '',
    fuel_cost: '',
    maintenance_cost: '',
  })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }))
    setResult(null)
    setError(null)
  }

  const handleCalculate = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const payload = {
        route_type: form.route_type,
        driver_group: form.driver_group,
        fuel_cost: parseFloat(form.fuel_cost) || 0,
        maintenance_cost: parseFloat(form.maintenance_cost) || 0,
      }
      if (form.delivery_points) {
        payload.delivery_points = parseInt(form.delivery_points, 10)
      }
      const { data } = await api.post('/api/v1/logistics/calculate', payload)
      setResult(data)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Ошибка расчёта')
    } finally {
      setLoading(false)
    }
  }

  const inputCls = {
    width: '100%',
    background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(212,168,67,0.2)',
    borderRadius: '6px',
    color: '#f5f0e8',
    padding: '8px 12px',
    fontSize: '12px',
    fontFamily: 'Montserrat, sans-serif',
    outline: 'none',
  }

  const labelCls = {
    display: 'block',
    fontSize: '10px',
    fontFamily: 'Orbitron, sans-serif',
    letterSpacing: '0.15em',
    textTransform: 'uppercase',
    color: 'rgba(212,168,67,0.7)',
    marginBottom: '6px',
  }

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{
        background: 'rgba(255,255,255,0.02)',
        borderColor: 'rgba(212,168,67,0.15)',
      }}
    >
      {/* Заголовок */}
      <div
        className="px-5 py-4 border-b flex items-center gap-2"
        style={{ borderColor: 'rgba(212,168,67,0.1)' }}
      >
        <Calculator size={14} style={{ color: '#d4a843' }} />
        <span className="text-[11px] font-orbitron tracking-wider" style={{ color: '#d4a843' }}>
          КАЛЬКУЛЯТОР РЕЙСА
        </span>
      </div>

      <div className="p-5 space-y-4">
        {/* Тип рейса */}
        <div>
          <label style={labelCls}>Тип рейса</label>
          <select name="route_type" value={form.route_type} onChange={handleChange} style={inputCls}>
            <option value="darkstore">Даркстор (ДС)</option>
            <option value="store">Магазин (МГ)</option>
            <option value="shmel">Шмель (ШМ)</option>
            <option value="zhuk">Жук (ЖУК)</option>
          </select>
        </div>

        {/* Группа водителя */}
        <div>
          <label style={labelCls}>Группа водителя</label>
          <select name="driver_group" value={form.driver_group} onChange={handleChange} style={inputCls}>
            <option value="BNYAN">БНЯН (BNYAN)</option>
            <option value="AZAT">АЗАТ (AZAT)</option>
          </select>
        </div>

        {/* Точки доставки (для Азата) */}
        {form.driver_group === 'AZAT' && (
          <div>
            <label style={labelCls}>Кол-во точек доставки</label>
            <input
              type="number"
              name="delivery_points"
              value={form.delivery_points}
              onChange={handleChange}
              placeholder="0"
              min="0"
              style={inputCls}
            />
          </div>
        )}

        {/* ГСМ */}
        <div>
          <label style={labelCls}>ГСМ (топливо), ₽</label>
          <input
            type="number"
            name="fuel_cost"
            value={form.fuel_cost}
            onChange={handleChange}
            placeholder="0"
            min="0"
            style={inputCls}
          />
        </div>

        {/* ТО */}
        <div>
          <label style={labelCls}>ТО (обслуживание), ₽</label>
          <input
            type="number"
            name="maintenance_cost"
            value={form.maintenance_cost}
            onChange={handleChange}
            placeholder="0"
            min="0"
            style={inputCls}
          />
        </div>

        {/* Кнопка */}
        <motion.button
          onClick={handleCalculate}
          disabled={loading}
          className="w-full py-3 rounded-lg font-orbitron text-[11px] tracking-[0.2em] uppercase transition-all disabled:opacity-50"
          style={{
            background: loading
              ? 'rgba(212,168,67,0.1)'
              : 'linear-gradient(135deg, rgba(212,168,67,0.2), rgba(212,168,67,0.1))',
            border: '1px solid rgba(212,168,67,0.4)',
            color: '#d4a843',
          }}
          whileHover={{ scale: loading ? 1 : 1.01 }}
          whileTap={{ scale: loading ? 1 : 0.99 }}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <motion.div
                className="w-4 h-4 rounded-full border-2"
                style={{ borderColor: 'rgba(212,168,67,0.2)', borderTopColor: '#d4a843' }}
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              />
              РАСЧЁТ...
            </span>
          ) : (
            'РАССЧИТАТЬ'
          )}
        </motion.button>

        {/* Ошибка */}
        {error && (
          <div
            className="p-3 rounded-lg text-[11px] font-montserrat"
            style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', color: '#fca5a5' }}
          >
            {error}
          </div>
        )}

        {/* Результат */}
        <AnimatePresence>
          {result && (
            <motion.div
              className="rounded-lg border overflow-hidden"
              style={{
                background: 'rgba(0,255,136,0.04)',
                borderColor: 'rgba(0,255,136,0.2)',
              }}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
            >
              <div
                className="px-4 py-2 border-b text-[10px] font-orbitron tracking-wider"
                style={{ borderColor: 'rgba(0,255,136,0.15)', color: '#00ff88' }}
              >
                РЕЗУЛЬТАТ РАСЧЁТА
              </div>
              <div className="p-4 space-y-2">
                {[
                  { label: 'Выручка ВВ', value: fmt(result.revenue), color: '#d4a843' },
                  { label: 'Выплата водителю', value: fmt(result.driver_payment), color: '#ffffff70' },
                  { label: 'Маржа', value: fmt(result.margin), color: result.margin >= 0 ? '#22c55e' : '#ef4444' },
                  { label: 'Доля С-ГЛОБАЛ (50%)', value: fmt(result.sglobal_share), color: '#d4a843' },
                  { label: 'Доля МКРТЧЯНА (50%)', value: fmt(result.mkrtchan_share), color: '#94a3b8' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="text-[11px] font-montserrat" style={{ color: '#ffffff50' }}>
                      {label}
                    </span>
                    <span className="text-[12px] font-orbitron font-bold" style={{ color }}>
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

// ─── Главная страница ─────────────────────────────────────────────────────────

export default function LogisticsPage({ onLogout }) {
  const navigate = useNavigate()

  const [stats, setStats] = useState(null)
  const [routes, setRoutes] = useState([])
  const [statsLoading, setStatsLoading] = useState(true)
  const [routesLoading, setRoutesLoading] = useState(true)
  const [statsError, setStatsError] = useState(null)
  const [seedLoading, setSeedLoading] = useState(false)
  const [seedMsg, setSeedMsg] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  // Загрузка статистики
  useEffect(() => {
    setStatsLoading(true)
    setStatsError(null)
    api.get('/api/v1/logistics/stats')
      .then(({ data }) => setStats(data))
      .catch((err) => {
        const status = err?.response?.status
        if (status === 401 || status === 403) {
          navigate('/')
        } else {
          setStatsError(`Статистика недоступна (${status || 'нет связи'})`)
        }
      })
      .finally(() => setStatsLoading(false))
  }, [refreshKey])

  // Загрузка рейсов
  useEffect(() => {
    setRoutesLoading(true)
    api.get('/api/v1/logistics/routes')
      .then(({ data }) => setRoutes(Array.isArray(data) ? data : []))
      .catch((err) => {
        const status = err?.response?.status
        if (status === 401 || status === 403) navigate('/')
        else setRoutes([])
      })
      .finally(() => setRoutesLoading(false))
  }, [refreshKey])

  // Загрузка тестовых данных
  const handleSeedMarch10 = useCallback(async () => {
    setSeedLoading(true)
    setSeedMsg(null)
    try {
      const { data } = await api.post('/api/v1/logistics/seed-march-10')
      setSeedMsg({ type: 'success', text: data?.message || 'Данные 10 марта загружены' })
      setRefreshKey((k) => k + 1)
    } catch (err) {
      setSeedMsg({
        type: 'error',
        text: err?.response?.data?.detail || 'Ошибка загрузки данных',
      })
    } finally {
      setSeedLoading(false)
      setTimeout(() => setSeedMsg(null), 4000)
    }
  }, [])

  const totals = stats?.totals || {}

  return (
    <div
      className="min-h-screen relative"
      style={{ backgroundColor: '#0D0C0B', color: '#f5f0e8' }}
    >
      {/* Фоновый градиент LG */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at top left, rgba(0,255,136,0.04) 0%, transparent 60%)',
          zIndex: 0,
        }}
      />

      {/* ═══════════════════════════════════════════════════════════════════════
          ШАПКА
      ═══════════════════════════════════════════════════════════════════════ */}
      <header
        className="relative z-10 flex flex-wrap items-center justify-between gap-4 px-6 py-4 border-b"
        style={{
          borderColor: 'rgba(0,255,136,0.15)',
          background: 'rgba(0,0,0,0.5)',
          backdropFilter: 'blur(20px)',
        }}
      >
        {/* Назад */}
        <Link
          to="/"
          className="flex items-center gap-2 px-3 py-2 rounded-xl transition-all hover:bg-white/5"
          style={{ color: '#ffffff50', textDecoration: 'none' }}
        >
          <ArrowLeft size={16} />
          <span className="text-[11px] font-orbitron tracking-wider">ДАШБОРД</span>
        </Link>

        {/* Заголовок */}
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center text-xl"
            style={{
              background: 'linear-gradient(135deg, rgba(0,255,136,0.15), rgba(0,255,136,0.05))',
              border: '1px solid rgba(0,255,136,0.3)',
              boxShadow: '0 0 20px rgba(0,255,136,0.1)',
            }}
          >
            🚚
          </div>
          <div>
            <div
              className="text-[11px] font-orbitron font-bold tracking-[0.3em] uppercase"
              style={{ color: '#00ff88' }}
            >
              СЕКТОР LG — ЛОГИСТИКА ВКУСВИЛЛ
            </div>
            <div
              className="text-[10px] font-montserrat mt-0.5"
              style={{ color: 'rgba(212,168,67,0.7)' }}
            >
              ПАРТНЁРСТВО 50/50 · ООО С-ГЛОБАЛ + ИП МКРТЧЯН
            </div>
          </div>
        </div>

        {/* Кнопки */}
        <div className="flex items-center gap-3">
          {/* Статус-бейдж */}
          <div
            className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full"
            style={{
              background: 'rgba(212,168,67,0.08)',
              border: '1px solid rgba(212,168,67,0.25)',
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full animate-pulse"
              style={{ backgroundColor: '#d4a843', boxShadow: '0 0 6px #d4a843' }}
            />
            <span className="text-[9px] font-orbitron tracking-wider" style={{ color: '#d4a843' }}>
              АКТИВЕН
            </span>
          </div>

          {/* Загрузить данные */}
          <motion.button
            onClick={handleSeedMarch10}
            disabled={seedLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-orbitron tracking-wider transition-all disabled:opacity-50"
            style={{
              background: 'rgba(0,255,136,0.08)',
              border: '1px solid rgba(0,255,136,0.25)',
              color: '#00ff88',
            }}
            whileHover={{ scale: seedLoading ? 1 : 1.02 }}
            whileTap={{ scale: seedLoading ? 1 : 0.98 }}
          >
            {seedLoading ? (
              <motion.div
                className="w-3 h-3 rounded-full border"
                style={{ borderColor: 'rgba(0,255,136,0.2)', borderTopColor: '#00ff88' }}
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              />
            ) : (
              <Database size={12} />
            )}
            ЗАГРУЗИТЬ ДАННЫЕ 10 МАРТА
          </motion.button>

          {/* Обновить */}
          <button
            onClick={() => setRefreshKey((k) => k + 1)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-[10px] font-orbitron tracking-wider transition-all hover:bg-white/5"
            style={{ color: '#ffffff40', border: '1px solid rgba(255,255,255,0.06)' }}
          >
            <RefreshCw size={12} />
            ОБНОВИТЬ
          </button>
        </div>
      </header>

      {/* Уведомление seed */}
      <AnimatePresence>
        {seedMsg && (
          <motion.div
            className="relative z-20 mx-6 mt-4 px-4 py-3 rounded-xl text-[12px] font-montserrat flex items-center gap-2"
            style={{
              background: seedMsg.type === 'success'
                ? 'rgba(34,197,94,0.1)'
                : 'rgba(239,68,68,0.1)',
              border: `1px solid ${seedMsg.type === 'success' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
              color: seedMsg.type === 'success' ? '#22c55e' : '#fca5a5',
            }}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            {seedMsg.type === 'success' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
            {seedMsg.text}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ═══════════════════════════════════════════════════════════════════════
          ОСНОВНОЙ КОНТЕНТ
      ═══════════════════════════════════════════════════════════════════════ */}
      <main className="relative z-10 px-6 py-6 max-w-[1600px] mx-auto space-y-6">

        {/* ── KPI ВИДЖЕТЫ ─────────────────────────────────────────────────── */}
        {statsLoading ? (
          <div className="flex items-center justify-center py-10 gap-3">
            <motion.div
              className="w-8 h-8 rounded-full border-2"
              style={{ borderColor: 'rgba(0,255,136,0.15)', borderTopColor: '#00ff88' }}
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            />
            <span className="text-[11px] font-orbitron" style={{ color: '#00ff8860' }}>
              ЗАГРУЗКА СТАТИСТИКИ...
            </span>
          </div>
        ) : statsError ? (
          <div
            className="p-4 rounded-xl flex items-center gap-3 text-[12px] font-montserrat"
            style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#fca5a5' }}
          >
            <AlertCircle size={16} />
            {statsError}
          </div>
        ) : (
          <motion.div
            className="flex flex-wrap gap-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4 }}
          >
            <KpiCard
              icon={DollarSign}
              label="Выручка ВВ"
              value={fmt(totals.revenue)}
              color="#d4a843"
              delay={0}
            />
            <KpiCard
              icon={TrendingUp}
              label="Маржа"
              value={fmt(totals.margin)}
              color="#22c55e"
              delay={0.08}
            />
            <KpiCard
              icon={Building2}
              label="Доля С-ГЛОБАЛ"
              value={fmt(totals.sglobal_share)}
              color="#d4a843"
              delay={0.16}
            />
            <KpiCard
              icon={User}
              label="Доля МКРТЧЯНА"
              value={fmt(totals.mkrtchan_share)}
              color="#94a3b8"
              delay={0.24}
            />
          </motion.div>
        )}

        {/* Дополнительная статистика: рейсы + выплаты */}
        {!statsLoading && !statsError && stats && (
          <motion.div
            className="flex flex-wrap gap-3"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.3 }}
          >
            {[
              { label: 'Рейсов всего', value: fmtNum(totals.routes_count), color: '#00ff88' },
              { label: 'Выплаты водителям', value: fmt(totals.driver_payments), color: '#ffffff60' },
              { label: 'ГСМ', value: fmt(totals.fuel_cost), color: '#f97316' },
              { label: 'ТО', value: fmt(totals.maintenance_cost), color: '#f97316' },
            ].map(({ label, value, color }) => (
              <div
                key={label}
                className="px-4 py-2.5 rounded-lg border flex items-center gap-3"
                style={{
                  background: 'rgba(255,255,255,0.02)',
                  borderColor: 'rgba(255,255,255,0.08)',
                }}
              >
                <span className="text-[10px] font-orbitron tracking-wider" style={{ color: '#ffffff30' }}>
                  {label}
                </span>
                <span className="text-[13px] font-orbitron font-bold" style={{ color }}>
                  {value}
                </span>
              </div>
            ))}
          </motion.div>
        )}

        {/* ── ДВУХКОЛОНОЧНАЯ СЕТКА ────────────────────────────────────────── */}
        <div className="grid grid-cols-1 xl:grid-cols-[3fr_2fr] gap-6">

          {/* Левая колонка — Таблица рейсов */}
          <motion.div
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
          >
            <RoutesTable routes={routes} loading={routesLoading} />
          </motion.div>

          {/* Правая колонка — Калькулятор */}
          <motion.div
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            <RouteCalculator />

            {/* Статистика по типам рейсов */}
            {!statsLoading && stats?.by_type && stats.by_type.length > 0 && (
              <motion.div
                className="mt-4 rounded-xl border overflow-hidden"
                style={{
                  background: 'rgba(255,255,255,0.02)',
                  borderColor: 'rgba(212,168,67,0.15)',
                }}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
              >
                <div
                  className="px-5 py-3 border-b flex items-center gap-2"
                  style={{ borderColor: 'rgba(212,168,67,0.1)' }}
                >
                  <TrendingUp size={13} style={{ color: '#d4a843' }} />
                  <span className="text-[10px] font-orbitron tracking-wider" style={{ color: '#d4a843' }}>
                    ПО ТИПАМ РЕЙСОВ
                  </span>
                </div>
                <div className="p-4 space-y-2">
                  {stats.by_type.map((item) => {
                    const cfg = getRouteType(item.route_type)
                    return (
                      <div
                        key={item.route_type}
                        className="flex items-center justify-between py-2 border-b last:border-0"
                        style={{ borderColor: 'rgba(255,255,255,0.04)' }}
                      >
                        <div className="flex items-center gap-2">
                          <RouteTypeBadge type={item.route_type} />
                          <span className="text-[11px] font-montserrat" style={{ color: '#ffffff50' }}>
                            {item.count} рейс.
                          </span>
                        </div>
                        <div className="text-right">
                          <div className="text-[11px] font-orbitron" style={{ color: '#d4a843' }}>
                            {fmt(item.revenue)}
                          </div>
                          <div className="text-[10px] font-montserrat" style={{ color: '#22c55e' }}>
                            {fmt(item.margin)}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </motion.div>
            )}

            {/* Статистика по водителям */}
            {!statsLoading && stats?.by_driver && stats.by_driver.length > 0 && (
              <motion.div
                className="mt-4 rounded-xl border overflow-hidden"
                style={{
                  background: 'rgba(255,255,255,0.02)',
                  borderColor: 'rgba(212,168,67,0.15)',
                }}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
              >
                <div
                  className="px-5 py-3 border-b flex items-center gap-2"
                  style={{ borderColor: 'rgba(212,168,67,0.1)' }}
                >
                  <User size={13} style={{ color: '#d4a843' }} />
                  <span className="text-[10px] font-orbitron tracking-wider" style={{ color: '#d4a843' }}>
                    ПО ВОДИТЕЛЯМ
                  </span>
                </div>
                <div className="p-4 space-y-2">
                  {stats.by_driver.map((item) => (
                    <div
                      key={item.driver_name}
                      className="flex items-center justify-between py-2 border-b last:border-0"
                      style={{ borderColor: 'rgba(255,255,255,0.04)' }}
                    >
                      <div>
                        <div className="text-[12px] font-montserrat font-semibold" style={{ color: '#f5f0e8' }}>
                          {item.driver_name}
                        </div>
                        <div className="text-[10px] font-montserrat" style={{ color: '#ffffff40' }}>
                          {item.driver_group} · {item.count} рейс.
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-[11px] font-orbitron" style={{ color: '#d4a843' }}>
                          {fmt(item.revenue)}
                        </div>
                        <div className="text-[10px] font-montserrat" style={{ color: '#22c55e' }}>
                          {fmt(item.margin)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </motion.div>
        </div>

        {/* ── MIKS ТЕРМИНАЛ ───────────────────────────────────────────────── */}
        <motion.div
          className="rounded-xl border overflow-hidden"
          style={{
            borderColor: 'rgba(212,168,67,0.15)',
            background: 'rgba(0,0,0,0.3)',
          }}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          {/* Заголовок MIKS */}
          <div
            className="px-5 py-3 border-b flex items-center gap-3"
            style={{ borderColor: 'rgba(212,168,67,0.1)', background: 'rgba(0,0,0,0.2)' }}
          >
            <div
              className="w-2 h-2 rounded-full animate-pulse"
              style={{ backgroundColor: '#d4a843', boxShadow: '0 0 8px #d4a843' }}
            />
            <span className="text-[11px] font-orbitron tracking-[0.25em] uppercase" style={{ color: '#d4a843' }}>
              СВЯЗЬ С ЛОГИСТОМ · MIKS TERMINAL
            </span>
            <span
              className="ml-auto text-[9px] font-orbitron tracking-wider px-2 py-0.5 rounded-full"
              style={{
                background: 'rgba(0,255,136,0.08)',
                border: '1px solid rgba(0,255,136,0.2)',
                color: '#00ff88',
              }}
            >
              КАНАЛ: ЛОГИСТИКА
            </span>
          </div>

          {/* MIKS Terminal — самодостаточный компонент */}
          <div style={{ height: '420px', overflow: 'hidden' }}>
            <MIKSTerminal />
          </div>
        </motion.div>

      </main>
    </div>
  )
}
