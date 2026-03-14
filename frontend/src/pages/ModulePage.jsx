import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, RefreshCw, ExternalLink, AlertCircle, Loader2 } from 'lucide-react'
import { SECTOR_COLORS } from '../components/dashboard/sectorColors'
import api from '../api/client'

/**
 * S-GLOBAL DOMINION — Universal Module Page v200.30
 * =====================================================
 * Универсальная страница для каждого из 12 секторов.
 * Загружает данные из apiPath, отображает в стиле Dominion.
 * При клике на карточку сектора — переход сюда через react-router-dom.
 */

const SECTOR_LABELS = {
  FL: { emoji: '🚗', desc: 'Управление флотом, водителями и транзакциями таксопарка T-CLUB24' },
  LG: { emoji: '🚚', desc: 'Маршруты ВКУСВИЛЛ, логистические операции и трекинг доставок' },
  IT: { emoji: '💻', desc: 'Консалтинговые проекты, IT-инфраструктура и клиентская база' },
  WH: { emoji: '🔧', desc: 'Автосервис, страхование, склад запчастей и ТО' },
  AI: { emoji: '🤖', desc: 'AI-аналитика, прогнозы, скоринг водителей и Oracle Intelligence' },
  FN: { emoji: '💰', desc: 'Финансовые потоки, казна, транзакции и P&L отчёты' },
  GP: { emoji: '📍', desc: 'GPS-мониторинг флота в реальном времени' },
  TS: { emoji: '📋', desc: 'Задачи, AI-отчёты и автоматизация процессов' },
  MR: { emoji: '🏆', desc: 'Рейтинг водителей, Золотые Звёзды и система поощрений' },
  IV: { emoji: '📈', desc: 'Инвестиционный портфель и благотворительные программы' },
  FP: { emoji: '🤝', desc: 'Партнёрские соглашения, выплаты и CRM' },
  AC: { emoji: '🎓', desc: 'Обучение персонала, юридическая база и академия S-GLOBAL' },
}

// Словарь русификации ключей API
const KEY_TRANSLATIONS = {
  // Финансы
  total_revenue: 'Выручка',
  total_income: 'Доход',
  revenue: 'Выручка',
  income: 'Доход',
  total_expense: 'Расход',
  total_expenses: 'Расходы',
  expense: 'Расход',
  expenses: 'Расходы',
  fuel: 'ГСМ (Топливо)',
  salary: 'Зарплата',
  vkusvill: 'ВкусВилл',
  VkusVill: 'ВкусВилл',
  top_categories: 'ТОП КАТЕГОРИЙ',
  category: 'Категория',
  amount: 'Сумма',
  balance: 'Баланс',
  profit: 'Прибыль',
  margin: 'Маржа',
  net_profit: 'Чистая прибыль',
  gross_profit: 'Валовая прибыль',
  total_balance: 'Общий баланс',
  transactions_count: 'Кол-во транзакций',
  // Общие
  name: 'Название',
  title: 'Заголовок',
  status: 'Статус',
  date: 'Дата',
  created_at: 'Создано',
  updated_at: 'Обновлено',
  description: 'Описание',
  type: 'Тип',
  count: 'Количество',
  total: 'Итого',
  id: 'ID',
  park_name: 'Парк',
  tenant_id: 'Тенант',
  driver_name: 'Водитель',
  vehicle: 'Автомобиль',
  phone: 'Телефон',
  full_name: 'ФИО',
  license_plate: 'Гос. номер',
  brand: 'Марка',
  model: 'Модель',
}

function translateKey(key) {
  return KEY_TRANSLATIONS[key] || KEY_TRANSLATIONS[key.toLowerCase()] || key
}

function formatValue(key, value) {
  if (value === null || value === undefined) return '—'
  const k = key.toLowerCase()
  // Форматируем суммы
  if (['amount', 'revenue', 'income', 'expense', 'expenses', 'salary', 'fuel', 'balance', 'profit', 'margin',
       'total_revenue', 'total_income', 'total_expense', 'total_expenses', 'net_profit', 'gross_profit', 'total_balance'].includes(k)) {
    const num = parseFloat(value)
    if (!isNaN(num)) {
      return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(num)
    }
  }
  return String(value).slice(0, 60)
}

function isNegativeKey(key) {
  const k = key.toLowerCase()
  return ['expense', 'expenses', 'total_expense', 'total_expenses', 'fuel', 'salary'].includes(k)
}

export default function ModulePage({ code, title, apiPath, onLogout }) {
  const navigate = useNavigate()
  const colors = SECTOR_COLORS[code] || SECTOR_COLORS.FL
  const meta = SECTOR_LABELS[code] || { emoji: '⚡', desc: 'Модуль Империи S-GLOBAL' }

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.get(apiPath)
      .then(({ data: res }) => {
        setData(res)
      })
      .catch((err) => {
        const status = err?.response?.status
        if (status === 401 || status === 403) {
          navigate('/')
        } else {
          setError(`Модуль временно недоступен (${status || 'нет связи'})`)
        }
      })
      .finally(() => setLoading(false))
  }, [apiPath, refreshKey])

  return (
    <div
      className="min-h-screen relative"
      style={{ backgroundColor: '#0a0d14', color: '#e2e8f0' }}
    >
      {/* Фоновый градиент сектора */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          background: `radial-gradient(ellipse at top left, ${colors.glow}08 0%, transparent 60%)`,
          zIndex: 0,
        }}
      />

      {/* Верхняя панель */}
      <header
        className="relative z-10 flex items-center justify-between px-6 py-4 border-b"
        style={{
          borderColor: `${colors.glow}20`,
          background: 'rgba(0,0,0,0.4)',
          backdropFilter: 'blur(20px)',
        }}
      >
        {/* Назад */}
        <Link
          to="/"
          className="flex items-center gap-2 px-3 py-2 rounded-xl transition-all hover:bg-white/5"
          style={{ color: '#ffffff60', textDecoration: 'none' }}
        >
          <ArrowLeft size={16} />
          <span className="text-[12px] font-orbitron tracking-wider">ДАШБОРД</span>
        </Link>

        {/* Заголовок */}
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center text-lg"
            style={{
              background: `linear-gradient(135deg, ${colors.glow}20, ${colors.glow}05)`,
              border: `1px solid ${colors.glow}40`,
              boxShadow: `0 0 16px ${colors.glow}20`,
            }}
          >
            {meta.emoji}
          </div>
          <div>
            <div
              className="text-[11px] font-orbitron font-bold tracking-[0.3em] uppercase"
              style={{ color: colors.accent }}
            >
              {code} · СЕКТОР
            </div>
            <div className="text-[14px] font-montserrat font-semibold text-white/90">
              {title}
            </div>
          </div>
        </div>

        {/* Кнопки */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setRefreshKey((k) => k + 1)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-[11px] font-orbitron tracking-wider transition-all hover:bg-white/5"
            style={{ color: '#ffffff40', border: '1px solid rgba(255,255,255,0.06)' }}
          >
            <RefreshCw size={12} />
            ОБНОВИТЬ
          </button>
        </div>
      </header>

      {/* Основной контент */}
      <main className="relative z-10 px-6 py-8 max-w-[1440px] mx-auto">
        {/* Описание модуля */}
        <motion.div
          className="mb-8 p-5 rounded-2xl border"
          style={{
            borderColor: `${colors.glow}20`,
            background: `linear-gradient(135deg, ${colors.glow}06, transparent)`,
          }}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <p className="text-[13px] font-montserrat text-white/60 leading-relaxed">
            {meta.desc}
          </p>
          <div className="flex items-center gap-2 mt-3">
            <span
              className="w-2 h-2 rounded-full animate-pulse"
              style={{ backgroundColor: colors.glow, boxShadow: `0 0 6px ${colors.glow}` }}
            />
            <span className="text-[10px] font-orbitron tracking-wider" style={{ color: `${colors.glow}80` }}>
              МОДУЛЬ АКТИВЕН · ВЕРСИЯ 200.30
            </span>
          </div>
        </motion.div>

        {/* Состояние загрузки */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <motion.div
              className="w-10 h-10 rounded-full border-2"
              style={{ borderColor: `${colors.glow}20`, borderTopColor: colors.glow }}
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            />
            <span className="text-[11px] font-orbitron tracking-wider" style={{ color: `${colors.glow}60` }}>
              ЗАГРУЗКА ДАННЫХ...
            </span>
          </div>
        )}

        {/* Ошибка */}
        {!loading && error && (
          <motion.div
            className="flex flex-col items-center justify-center py-24 gap-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center"
              style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)' }}
            >
              <AlertCircle size={28} style={{ color: '#ef4444' }} />
            </div>
            <div className="text-center">
              <div className="text-[13px] font-montserrat text-white/60 mb-1">{error}</div>
              <div className="text-[11px] font-montserrat text-white/30">
                Модуль находится в разработке или API временно недоступен
              </div>
            </div>
            <button
              onClick={() => setRefreshKey((k) => k + 1)}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-[12px] font-orbitron tracking-wider transition-all"
              style={{
                background: `${colors.glow}15`,
                border: `1px solid ${colors.glow}30`,
                color: colors.glow,
              }}
            >
              <RefreshCw size={13} />
              ПОВТОРИТЬ
            </button>
          </motion.div>
        )}

        {/* Данные */}
        {!loading && !error && data && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <DataRenderer data={data} colors={colors} />
          </motion.div>
        )}
      </main>
    </div>
  )
}

/**
 * Универсальный рендерер данных API
 */
function DataRenderer({ data, colors }) {
  if (Array.isArray(data)) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.slice(0, 30).map((item, i) => (
          <DataCard key={i} item={item} colors={colors} index={i} />
        ))}
      </div>
    )
  }

  if (typeof data === 'object' && data !== null) {
    // Ищем массив в объекте
    const arrayKey = Object.keys(data).find((k) => Array.isArray(data[k]) && data[k].length > 0)
    if (arrayKey) {
      return (
        <div>
          <div className="mb-4 text-[11px] font-orbitron tracking-wider uppercase" style={{ color: `${colors.glow}90` }}>
            {translateKey(arrayKey)} · {data[arrayKey].length} записей
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data[arrayKey].slice(0, 30).map((item, i) => (
              <DataCard key={i} item={item} colors={colors} index={i} />
            ))}
          </div>
        </div>
      )
    }

    // Показываем ключ-значение (финансовый стиль)
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(data)
          .filter(([, v]) => typeof v !== 'object' || v === null)
          .map(([key, value], i) => {
            const isNeg = isNegativeKey(key)
            const isPos = ['revenue', 'income', 'total_revenue', 'total_income', 'profit', 'net_profit', 'gross_profit', 'balance', 'total_balance'].includes(key.toLowerCase())
            const valueColor = isNeg ? '#ff6b6b' : isPos ? '#00c853' : '#E0E0E0'
            return (
              <motion.div
                key={key}
                className="p-5 rounded-xl border"
                style={{
                  borderColor: `${colors.glow}20`,
                  background: `linear-gradient(135deg, rgba(0,0,0,0.5), rgba(0,0,0,0.3))`,
                  boxShadow: `0 2px 12px rgba(0,0,0,0.4)`,
                }}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                whileHover={{ y: -2 }}
              >
                <div className="text-[10px] font-orbitron tracking-[0.2em] uppercase mb-2" style={{ color: `${colors.glow}90` }}>
                  {translateKey(key)}
                </div>
                <div className="text-[18px] font-montserrat font-bold" style={{ color: valueColor }}>
                  {isNeg && value > 0 ? '−' : ''}{formatValue(key, value)}
                </div>
              </motion.div>
            )
          })}
      </div>
    )
  }

  return (
    <div className="text-center py-16 text-white/30 font-montserrat text-[13px]">
      Данные получены, но формат не распознан
    </div>
  )
}

function DataCard({ item, colors, index }) {
  if (typeof item !== 'object' || item === null) {
    return (
      <motion.div
        className="p-4 rounded-xl border text-[13px] font-montserrat"
        style={{ borderColor: `${colors.glow}15`, background: 'rgba(0,0,0,0.4)', color: '#E0E0E0' }}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.04 }}
      >
        {String(item)}
      </motion.div>
    )
  }

  const entries = Object.entries(item).slice(0, 6)
  const primaryKey = ['name', 'title', 'full_name', 'license_plate', 'id'].find((k) => item[k])
  const primaryValue = primaryKey ? item[primaryKey] : entries[0]?.[1]

  return (
    <motion.div
      className="p-4 rounded-xl border transition-all"
      style={{
        borderColor: `${colors.glow}18`,
        background: 'linear-gradient(135deg, rgba(0,0,0,0.5), rgba(0,0,0,0.3))',
        boxShadow: `0 2px 12px rgba(0,0,0,0.3)`,
      }}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      whileHover={{ y: -2, boxShadow: `0 8px 24px rgba(0,0,0,0.4), 0 0 20px ${colors.glow}10` }}
    >
      {/* Заголовок карточки — #E0E0E0 вместо accent */}
      <div
        className="text-[13px] font-montserrat font-semibold mb-3 truncate"
        style={{ color: '#E0E0E0' }}
      >
        {String(primaryValue ?? `#${index + 1}`)}
      </div>

      {/* Поля с русификацией */}
      <div className="space-y-2">
        {entries
          .filter(([k]) => k !== primaryKey)
          .slice(0, 4)
          .map(([key, value]) => {
            const isNeg = isNegativeKey(key)
            const isPos = ['revenue', 'income', 'total_revenue', 'total_income', 'profit', 'net_profit', 'balance'].includes(key.toLowerCase())
            const valColor = isNeg ? '#ff6b6b' : isPos ? '#00c853' : '#E0E0E0'
            return (
              <div key={key} className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-orbitron tracking-wider uppercase truncate" style={{ color: `${colors.glow}80` }}>
                  {translateKey(key)}
                </span>
                <span className="text-[12px] font-montserrat font-semibold truncate max-w-[60%] text-right" style={{ color: valColor }}>
                  {formatValue(key, value)}
                </span>
              </div>
            )
          })}
      </div>
    </motion.div>
  )
}
