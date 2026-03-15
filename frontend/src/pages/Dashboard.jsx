import React from 'react'
import { motion } from 'framer-motion'
import {
  Car, Truck, Monitor, Wrench, Brain, Wallet,
  MapPin, FileText, Award, TrendingUp, Users, GraduationCap
} from 'lucide-react'

import TopBar from '../components/dashboard/TopBar'
import SectorCard from '../components/dashboard/SectorCard'
import ParticleBackground from '../components/dashboard/ParticleBackground'
import WorldMapBackground from '../components/dashboard/WorldMapBackground'
import ScanLinesOverlay from '../components/dashboard/ScanLinesOverlay'
import HRMetricsWidget from '../components/dashboard/HRMetricsWidget'
import SecurityAuditPanel from '../components/dashboard/SecurityAuditPanel'
import LiveFleetCounter from '../components/dashboard/LiveFleetCounter'
// DominionWidget и BottomDrawer вынесены в App.jsx (глобальный макет)

/**
 * S-GLOBAL DOMINION — Main Dashboard v7.2 (Level 5++)
 * =====================================================
 * 12 секторов империи в glassmorphism-сетке
 * Фон: ВЕЛИЧЕСТВЕННАЯ контурная карта мира с неоновыми границами
 * Эффект сканирующих линий (кабина пилота)
 * Живые карточки с левитацией
 * Статус-бар приподнят и выровнен
 * VERSHINA v200.29.1 Protocol — ГЕРМЕТИЗАЦИЯ БЕЗОПАСНОСТИ + IVORY LUXE
 */

/** Единый источник правды для версии протокола */
const PROTOCOL_VERSION = 'v200.31'

// 12 секторов империи с маршрутами
const SECTORS = [
  {
    code: 'FL',
    title: 'ТАКСОПАРК T-CLUB24',
    subtitle: 'EXPRESS · PRO · GO · PLUS',
    parks: ['EXPRESS', 'PRO', 'GO', 'PLUS'],
    description: 'Яндекс Такси · t-club24',
    icon: Car,
    route: '/fleet',
  },
  {
    code: 'LG',
    title: 'ЛОГИСТИКА И МАРШРУТЫ',
    subtitle: 'ВКУСВИЛЛ: АКТИВНО',
    icon: Truck,
    liveCount: '--',
    route: '/logistics',
  },
  {
    code: 'IT',
    title: 'КОНСАЛТИНГ И IT v30.6',
    subtitle: 'Системы стабильны',
    icon: Monitor,
    route: '/consulting',
  },
  {
    code: 'WH',
    title: 'АВТОСЕРВИС И СТРАХОВАНИЕ',
    subtitle: 'Склад синхронизирован',
    icon: Wrench,
    route: '/warehouse',
  },
  {
    code: 'AI',
    title: 'AI АНАЛИТИК',
    subtitle: 'Поток стабилен',
    icon: Brain,
    route: '/ai-analyst',
  },
  {
    code: 'FN',
    title: 'ФИНАНСЫ И БУХГАЛТЕРИЯ',
    subtitle: 'Банковские шлюзы: АКТИВНО',
    icon: Wallet,
    route: '/finance',
  },
  {
    code: 'GP',
    title: 'GPS МОНИТОРИНГ',
    subtitle: 'Трекинг активен',
    icon: MapPin,
    route: '/gps',
  },
  {
    code: 'TS',
    title: 'AI ОТЧЁТЫ И ЗАДАЧИ',
    subtitle: 'Генерация отчётов',
    icon: FileText,
    route: '/tasks',
  },
  {
    code: 'MR',
    title: 'ГАРНИЗОН ПОЧЁТА',
    subtitle: 'Рейтинг обновлён',
    icon: Award,
    route: '/merit',
  },
  {
    code: 'IV',
    title: 'ИНВЕСТИЦИИ И БЛАГОТВОРИТЕЛЬНОСТЬ',
    subtitle: 'Портфель стабилен',
    icon: TrendingUp,
    route: '/investments',
  },
  {
    code: 'FP',
    title: 'ПАРТНЁРЫ И ВЫПЛАТЫ',
    subtitle: 'Расчёты в процессе',
    icon: Users,
    route: '/partners',
  },
  {
    code: 'AC',
    title: 'S-GLOBAL ACADEMY & LEGAL',
    subtitle: 'Обучение активно',
    icon: GraduationCap,
    route: '/academy',
  },
]

export default function Dashboard({ onLogout }) {
  return (
    <div className="min-h-screen relative">
      {/* Фоновые частицы */}
      <ParticleBackground count={35} />

      {/* Контурная карта мира — ВЕЛИЧЕСТВЕННАЯ, неоновая */}
      <WorldMapBackground />

      {/* Эффект сканирующих линий — кабина пилота */}
      <ScanLinesOverlay />

      {/* Верхняя панель */}
      <TopBar onLogout={onLogout} />

      {/* Основной контент */}
      <main className="relative z-[10] px-4 md:px-6 lg:px-8 py-6 pb-24">
        {/* Заголовок секции */}
        <motion.div
          className="mb-8"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          <div className="flex items-center gap-4 mb-2">
            <div
              className="h-px flex-1 max-w-16"
              style={{
                background: 'linear-gradient(90deg, #d4a843, transparent)',
              }}
            />
            <h2
              className="font-orbitron text-xs tracking-[0.4em] uppercase text-dominion-gold/60"
            >
              СЕКТОРЫ ИМПЕРИИ
            </h2>
            <div
              className="h-px flex-1 max-w-16"
              style={{
                background: 'linear-gradient(90deg, transparent, #d4a843)',
              }}
            />
          </div>
          <p className="text-center text-xs font-montserrat text-dominion-muted">
            12 подразделений · Полный контроль · VERSHINA {PROTOCOL_VERSION}
          </p>
        </motion.div>

        {/* Сетка карточек: 1 / 2 / 4 колонки — СТРОГО одинаковая высота через h-full */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 max-w-[1440px] mx-auto auto-rows-fr">
          {SECTORS.map((sector, index) => (
            <SectorCard
              key={sector.code}
              code={sector.code}
              title={sector.title}
              subtitle={sector.subtitle}
              icon={sector.icon}
              index={index}
              liveCount={sector.liveCount ?? null}
              route={sector.route}
            />
          ))}
        </div>

        {/* HR-МЕТРИКИ — LOGIST-PAY Widget (ИП Мкртчян) */}
        <div className="mt-6 max-w-[1440px] mx-auto">
          <HRMetricsWidget />
        </div>

        {/* ЖИВОЙ ФЛОТ + АУДИТ БЕЗОПАСНОСТИ — двухколоночная сетка */}
        <motion.div
          className="mt-6 max-w-[1440px] mx-auto grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.9, duration: 0.6 }}
        >
          {/* Левая колонка: LiveFleetCounter */}
          <LiveFleetCounter parkName="PRO" />

          {/* Правая колонка: SecurityAuditPanel */}
          <SecurityAuditPanel collapsed={false} />
        </motion.div>

        {/* СТАТУС-БАР — приподнят, ровно выровнен (mt-6) */}
        <motion.div
          className="mt-6 max-w-[1440px] mx-auto"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.2, duration: 0.6 }}
        >
          <div
            className="flex items-center justify-center gap-8 flex-wrap py-4 px-6 rounded-xl border bg-white/[0.02] border-white/[0.06]"
            style={{
              backdropFilter: 'blur(16px)',
              WebkitBackdropFilter: 'blur(16px)',
              boxShadow: '0 4px 24px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.03)',
            }}
          >
            <StatItem
              label="Секторов"
              value="12"
              color="#d4a843"
            />
            <div className="w-px h-8 bg-white/10" />
            <StatItem
              label="Парковый флот"
              value="41"
              suffix="⭐"
              color="#00f5ff"
            />
            <div className="w-px h-8 bg-white/10" />
            <StatItem
              label="Статус"
              value="В СЕТИ"
              color="#00ff88"
            />
            <div className="w-px h-8 bg-white/10" />
            <StatItem
              label="Протокол"
              value={PROTOCOL_VERSION}
              color="#a855f7"
            />
          </div>
        </motion.div>

      </main>

    </div>
  )
}

/**
 * Мини-компонент статистики
 */
function StatItem({ label, value, suffix, color }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span
        className="text-[10px] font-orbitron tracking-[0.2em] uppercase text-dominion-muted"
      >
        {label}
      </span>
      <div className="flex items-center gap-1.5">
        {suffix && <span className="text-sm">{suffix}</span>}
        <span
          className="text-lg font-orbitron font-bold"
          style={{
            color,
            textShadow: `0 0 10px ${color}40`,
          }}
        >
          {value}
        </span>
      </div>
    </div>
  )
}
