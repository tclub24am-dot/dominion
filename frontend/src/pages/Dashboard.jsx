import React from 'react'
import { motion } from 'framer-motion'
import {
  Car, Truck, Monitor, Wrench, Brain, MessageCircle,
  MapPin, FileText, Award, TrendingUp, Users, GraduationCap
} from 'lucide-react'

import TopBar from '../components/dashboard/TopBar'
import SectorCard from '../components/dashboard/SectorCard'
import BottomDrawer from '../components/dashboard/BottomDrawer'
import MessengerBubble from '../components/dashboard/MessengerBubble'
import ParticleBackground from '../components/dashboard/ParticleBackground'

/**
 * S-GLOBAL DOMINION — Main Dashboard v5.0
 * =========================================
 * 12 секторов империи в glassmorphism-сетке
 * Верхняя панель HQ | Нижний drawer | 3D Messenger
 * Две темы: Dark (золото/неон) и Ivory (слоновая кость)
 */

// 12 секторов империи
const SECTORS = [
  {
    code: 'FL',
    title: 'ТАКСОПАРК T-CLUB24',
    subtitle: 'На линии: 0 · ⭐ ПАРКОВЫЙ (41)',
    icon: Car,
  },
  {
    code: 'LG',
    title: 'ЛОГИСТИКА И МАРШРУТЫ',
    subtitle: 'Грузы активны',
    icon: Truck,
  },
  {
    code: 'IT',
    title: 'КОНСАЛТИНГ И IT v30.6',
    subtitle: 'Системы стабильны',
    icon: Monitor,
  },
  {
    code: 'WH',
    title: 'АВТОСЕРВИС И СТРАХОВАНИЕ',
    subtitle: 'Склад синхронизирован',
    icon: Wrench,
  },
  {
    code: 'AI',
    title: 'AI АНАЛИТИК',
    subtitle: 'Поток стабилен',
    icon: Brain,
  },
  {
    code: 'IM',
    title: 'IMPERIAL MESSENGER',
    subtitle: 'Онлайн',
    icon: MessageCircle,
  },
  {
    code: 'GP',
    title: 'GPS МОНИТОРИНГ',
    subtitle: 'Трекинг активен',
    icon: MapPin,
  },
  {
    code: 'TS',
    title: 'AI ОТЧЁТЫ И ЗАДАЧИ',
    subtitle: 'Генерация отчётов',
    icon: FileText,
  },
  {
    code: 'MR',
    title: 'ГАРНИЗОН ПОЧЁТА',
    subtitle: 'Рейтинг обновлён',
    icon: Award,
  },
  {
    code: 'IV',
    title: 'ИНВЕСТИЦИИ И БЛАГОТВОРИТЕЛЬНОСТЬ',
    subtitle: 'Портфель стабилен',
    icon: TrendingUp,
  },
  {
    code: 'FP',
    title: 'ПАРТНЁРЫ И ВЫПЛАТЫ',
    subtitle: 'Расчёты в процессе',
    icon: Users,
  },
  {
    code: 'AC',
    title: 'S-GLOBAL ACADEMY & LEGAL',
    subtitle: 'Обучение активно',
    icon: GraduationCap,
  },
]

export default function Dashboard({ theme = 'dark', onToggleTheme }) {
  const isDark = theme === 'dark'

  return (
    <div
      className={`
        min-h-screen relative
        ${isDark ? 'bg-dominion-black' : 'bg-ivory-bg'}
      `}
    >
      {/* Фоновые частицы */}
      <ParticleBackground theme={theme} count={35} />

      {/* Верхняя панель */}
      <TopBar theme={theme} onToggleTheme={onToggleTheme} />

      {/* Основной контент */}
      <main className="relative z-10 px-4 md:px-6 lg:px-8 py-6 pb-24">
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
                background: isDark
                  ? 'linear-gradient(90deg, #d4a843, transparent)'
                  : 'linear-gradient(90deg, #b8860b, transparent)',
              }}
            />
            <h2
              className={`
                font-orbitron text-xs tracking-[0.4em] uppercase
                ${isDark ? 'text-dominion-gold/60' : 'text-ivory-gold/60'}
              `}
            >
              СЕКТОРЫ ИМПЕРИИ
            </h2>
            <div
              className="h-px flex-1 max-w-16"
              style={{
                background: isDark
                  ? 'linear-gradient(90deg, transparent, #d4a843)'
                  : 'linear-gradient(90deg, transparent, #b8860b)',
              }}
            />
          </div>
          <p
            className={`
              text-center text-xs font-montserrat
              ${isDark ? 'text-dominion-muted' : 'text-ivory-muted'}
            `}
          >
            12 подразделений · Полный контроль · VERSHINA v200.11
          </p>
        </motion.div>

        {/* Сетка карточек: 1 / 2 / 4 колонки */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-[1440px] mx-auto">
          {SECTORS.map((sector, index) => (
            <SectorCard
              key={sector.code}
              code={sector.code}
              title={sector.title}
              subtitle={sector.subtitle}
              icon={sector.icon}
              index={index}
              theme={theme}
            />
          ))}
        </div>

        {/* Нижняя статистика */}
        <motion.div
          className="mt-10 max-w-[1440px] mx-auto"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2, duration: 0.6 }}
        >
          <div
            className={`
              flex items-center justify-center gap-8 flex-wrap
              py-4 px-6 rounded-xl border
              ${isDark
                ? 'bg-white/[0.02] border-white/[0.05]'
                : 'bg-white/40 border-ivory-border'
              }
            `}
            style={{ backdropFilter: 'blur(12px)' }}
          >
            <StatItem
              label="Секторов"
              value="12"
              color={isDark ? '#d4a843' : '#b8860b'}
              isDark={isDark}
            />
            <div className={`w-px h-8 ${isDark ? 'bg-white/10' : 'bg-ivory-border'}`} />
            <StatItem
              label="Парковый флот"
              value="41"
              suffix="⭐"
              color={isDark ? '#00f5ff' : '#0891b2'}
              isDark={isDark}
            />
            <div className={`w-px h-8 ${isDark ? 'bg-white/10' : 'bg-ivory-border'}`} />
            <StatItem
              label="Статус"
              value="ONLINE"
              color="#00ff88"
              isDark={isDark}
            />
            <div className={`w-px h-8 ${isDark ? 'bg-white/10' : 'bg-ivory-border'}`} />
            <StatItem
              label="Протокол"
              value="v200.11"
              color={isDark ? '#a855f7' : '#7c3aed'}
              isDark={isDark}
            />
          </div>
        </motion.div>
      </main>

      {/* 3D Messenger */}
      <MessengerBubble theme={theme} />

      {/* Нижняя выдвижная панель */}
      <BottomDrawer theme={theme} />
    </div>
  )
}

/**
 * Мини-компонент статистики
 */
function StatItem({ label, value, suffix, color, isDark }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span
        className={`text-[10px] font-orbitron tracking-[0.2em] uppercase ${isDark ? 'text-dominion-muted' : 'text-ivory-muted'}`}
      >
        {label}
      </span>
      <div className="flex items-center gap-1.5">
        {suffix && <span className="text-sm">{suffix}</span>}
        <span
          className="text-lg font-orbitron font-bold"
          style={{ color }}
        >
          {value}
        </span>
      </div>
    </div>
  )
}
