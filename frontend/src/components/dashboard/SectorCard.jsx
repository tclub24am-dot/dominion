import React, { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { SECTOR_COLORS } from './sectorColors'

/**
 * S-GLOBAL DOMINION — Sector Card v3.1 (Level 5++ LEVITATION + AURA)
 * ====================================================================
 * Карточка сектора империи с эффектами:
 * - Левитация при наведении (y: -12, scale: 1.04)
 * - Glow x2 при ховере
 * - Стеклянный блик, пробегающий по карточке
 * - Фиксированная высота h-[160px]
 * - Неоновый border-glow
 * - Эффект «АУРЫ» — медленно пульсирующее цветное пятно
 *
 * VERSHINA v200.13 Protocol — Level 5++
 */

// Статические данные активности для каждого сектора (заглушки — подключить к API)
const SECTOR_ACTIVITY = {
  FL: { load: 78, trend: '+3%', metric: '41 авто' },
  LG: { load: 62, trend: '+1%', metric: 'ВКУСВИЛЛ' },
  IT: { load: 95, trend: '0%',  metric: 'v30.6' },
  WH: { load: 45, trend: '-2%', metric: 'Склад OK' },
  AI: { load: 88, trend: '+5%', metric: 'GPT-4o' },
  FN: { load: 71, trend: '+2%', metric: '₽ Активно' },
  GP: { load: 55, trend: '0%',  metric: 'GPS Live' },
  TS: { load: 40, trend: '+1%', metric: 'Задачи' },
  MR: { load: 82, trend: '+4%', metric: 'Рейтинг' },
  IV: { load: 33, trend: '-1%', metric: 'Портфель' },
  FP: { load: 60, trend: '+2%', metric: 'Партнёры' },
  AC: { load: 25, trend: '0%',  metric: 'Обучение' },
}

export default function SectorCard({ code, title, subtitle, icon: Icon, index = 0, liveCount = null }) {
  const [isHovered, setIsHovered] = useState(false)
  const [glintTriggered, setGlintTriggered] = useState(false)
  const [loadAnimated, setLoadAnimated] = useState(false)
  const colors = SECTOR_COLORS[code] || SECTOR_COLORS.FL
  const activity = SECTOR_ACTIVITY[code] || { load: 50, trend: '0%', metric: '—' }

  // Запуск стеклянного блика при наведении
  const handleMouseEnter = () => {
    setIsHovered(true)
    setGlintTriggered(false)
    setLoadAnimated(true)
    // Небольшая задержка перед запуском блика
    requestAnimationFrame(() => setGlintTriggered(true))
  }

  const handleMouseLeave = () => {
    setIsHovered(false)
    setGlintTriggered(false)
  }

  // Запускаем анимацию прогресс-бара при монтировании
  useEffect(() => {
    const t = setTimeout(() => setLoadAnimated(true), index * 80 + 400)
    return () => clearTimeout(t)
  }, [index])

  return (
    <motion.div
      className="relative group h-full"
      initial={{ opacity: 0, y: 30, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      whileHover={{
        y: -12,
        scale: 1.04,
        transition: {
          type: 'spring',
          stiffness: 300,
          damping: 20,
        },
      }}
      transition={{
        duration: 0.5,
        delay: index * 0.08,
        ease: [0.16, 1, 0.3, 1],
      }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* === ЭФФЕКТ «АУРЫ» — медленно пульсирующее цветное пятно === */}
      <motion.div
        className="absolute -inset-6 rounded-2xl pointer-events-none"
        style={{
          background: `radial-gradient(circle at center, rgba(${colors.glowRgb}, 0.063) 0%, transparent 70%)`,
          zIndex: -1,
        }}
        animate={{
          opacity: [0.4, 1, 0.4],
          scale: [0.95, 1.05, 0.95],
        }}
        transition={{
          duration: 6,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />

      {/* Внешний неоновый glow — УСИЛЕННЫЙ x2 при ховере */}
      <motion.div
        className="absolute -inset-[2px] rounded-xl blur-[2px]"
        style={{
          background: `linear-gradient(135deg, ${colors.glow}40, transparent 40%, ${colors.glow}20, transparent 70%, ${colors.glow}30)`,
        }}
        animate={{
          opacity: isHovered ? 0.9 : 0.3,
        }}
        transition={{ duration: 0.4 }}
      />

      {/* Второй слой glow — появляется при ховере (x2 мощность) */}
      <motion.div
        className="absolute -inset-[4px] rounded-2xl blur-[6px]"
        style={{
          background: `radial-gradient(ellipse at center, ${colors.glow}25, transparent 70%)`,
        }}
        animate={{
          opacity: isHovered ? 0.7 : 0,
        }}
        transition={{ duration: 0.5 }}
      />

      {/* Карточка — ФИКСИРОВАННАЯ ВЫСОТА */}
      <div
        className="sector-card relative overflow-hidden rounded-xl border p-4 h-[190px] flex flex-col transition-colors duration-300 cursor-pointer backdrop-blur-2xl hover:border-white/[0.15]"
        style={{
          borderColor: isHovered ? `${colors.glow}60` : `${colors.glow}20`,
          boxShadow: isHovered
            ? `0 12px 40px rgba(0,0,0,0.7), 0 0 40px ${colors.glow}25, 0 0 80px ${colors.glow}10, inset 0 1px 0 rgba(255,255,255,0.08)`
            : `0 4px 16px rgba(0,0,0,0.4), 0 0 12px ${colors.glow}08, inset 0 1px 0 rgba(255,255,255,0.03)`,
          transition: 'box-shadow 0.4s ease, border-color 0.3s ease',
        }}
      >
        {/* Фоновый градиент */}
        <div
          className="absolute inset-0 transition-opacity duration-500"
          style={{
            background: `radial-gradient(ellipse at top right, ${colors.glow}${isHovered ? '12' : '06'}, transparent 70%)`,
            opacity: isHovered ? 0.6 : 0.3,
          }}
        />

        {/* === СТЕКЛЯННЫЙ БЛИК — пробегает при наведении === */}
        {glintTriggered && (
          <motion.div
            className="absolute inset-0 pointer-events-none z-10"
            initial={{ x: '-100%' }}
            animate={{ x: '200%' }}
            transition={{ duration: 0.7, ease: [0.25, 0.46, 0.45, 0.94] }}
            onAnimationComplete={() => setGlintTriggered(false)}
          >
            <div
              className="h-full w-1/3"
              style={{
                background: `linear-gradient(105deg, transparent 0%, rgba(255,255,255,0) 30%, rgba(255,255,255,0.08) 45%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0.08) 55%, rgba(255,255,255,0) 70%, transparent 100%)`,
              }}
            />
          </motion.div>
        )}

        {/* Сканирующая линия при ховере */}
        {isHovered && (
          <motion.div
            className="absolute left-0 right-0 h-[1px] pointer-events-none z-10"
            style={{
              background: `linear-gradient(90deg, transparent, ${colors.glow}80, transparent)`,
              boxShadow: `0 0 8px ${colors.glow}40`,
            }}
            initial={{ top: 0 }}
            animate={{ top: '100%' }}
            transition={{ duration: 1.5, ease: 'linear' }}
          />
        )}

        {/* Верхняя часть: Бейдж + Статус */}
        <div className="relative flex items-start justify-between mb-3">
          {/* Бейдж сектора */}
          <motion.div
            className="flex items-center justify-center w-11 h-11 rounded-lg"
            style={{
              background: `linear-gradient(135deg, ${colors.glow}20, ${colors.glow}05)`,
              border: `1px solid ${colors.glow}40`,
              boxShadow: isHovered ? `0 0 16px ${colors.glow}40` : 'none',
              transition: 'box-shadow 0.4s ease',
            }}
            whileHover={{ scale: 1.1, rotate: 5 }}
            transition={{ type: 'spring', stiffness: 400, damping: 15 }}
          >
            {Icon ? (
              <Icon size={20} style={{ color: colors.accent }} />
            ) : (
              <span
                className="text-xs font-orbitron font-bold"
                style={{ color: colors.accent }}
              >
                {code}
              </span>
            )}
          </motion.div>

          {/* Индикатор статуса */}
          <div className="flex items-center gap-1.5">
            <span className="relative flex h-2 w-2">
              <span
                className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                style={{ backgroundColor: colors.glow }}
              />
              <span
                className="relative inline-flex rounded-full h-2 w-2"
                style={{
                  backgroundColor: colors.glow,
                  boxShadow: `0 0 6px ${colors.glow}`,
                }}
              />
            </span>
          </div>
        </div>

        {/* Код сектора */}
        <div
          className="text-[10px] font-orbitron font-bold tracking-[0.3em] uppercase mb-1"
          style={{ color: `${colors.accent}aa` }}
        >
          {code}
        </div>

        {/* Название — flex-grow для выравнивания */}
        <h3 className="font-montserrat font-bold text-[14px] leading-tight mb-auto text-white/90">
          {title}
        </h3>

        {/* Подзаголовок — всегда внизу */}
        <div className="flex items-center gap-2 mt-2">
          <p className="text-xs font-montserrat text-dominion-muted truncate">
            {subtitle}
          </p>
          {/* Пульсирующий индикатор активных машин (для LG и других секторов с liveCount) */}
          {liveCount !== null && (
            <span className="flex items-center gap-1 ml-auto flex-shrink-0">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full animate-pulse"
                style={{ backgroundColor: colors.glow, boxShadow: `0 0 6px ${colors.glow}80` }}
              />
              <span
                className="text-[10px] font-orbitron font-bold"
                style={{ color: colors.glow }}
              >
                {liveCount}
              </span>
            </span>
          )}
        </div>

        {/* Прогресс-бар активности сектора */}
        <div className="mt-2.5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[8px] font-montserrat text-white/25 tracking-wider uppercase">
              Активность
            </span>
            <div className="flex items-center gap-1">
              <span
                className="text-[9px] font-orbitron font-bold"
                style={{ color: `${colors.glow}cc` }}
              >
                {activity.load}%
              </span>
              <span
                className="text-[8px] font-montserrat"
                style={{
                  color: activity.trend.startsWith('+') ? '#00ff88' : activity.trend.startsWith('-') ? '#ef4444' : '#8888aa',
                }}
              >
                {activity.trend}
              </span>
            </div>
          </div>
          <div
            className="h-[3px] rounded-full overflow-hidden"
            style={{ background: 'rgba(255,255,255,0.06)' }}
          >
            <motion.div
              className="h-full rounded-full"
              style={{
                background: `linear-gradient(90deg, ${colors.glow}cc, ${colors.glow})`,
                boxShadow: `0 0 6px ${colors.glow}60`,
              }}
              initial={{ width: 0 }}
              animate={{ width: loadAnimated ? `${activity.load}%` : 0 }}
              transition={{ duration: 1.2, ease: 'easeOut' }}
            />
          </div>
        </div>

        {/* Нижняя линия-акцент */}
        <motion.div
          className="absolute bottom-0 left-0 right-0 h-[2px]"
          style={{
            background: `linear-gradient(90deg, transparent, ${colors.glow}, transparent)`,
            boxShadow: `0 0 8px ${colors.glow}60`,
          }}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: isHovered ? 1 : 0 }}
          transition={{ duration: 0.3 }}
        />

        {/* Угловые декоративные элементы */}
        <div
          className="absolute top-0 left-0 w-4 h-4 border-t border-l rounded-tl-xl transition-opacity duration-500"
          style={{
            borderColor: colors.glow,
            opacity: isHovered ? 0.5 : 0.15,
          }}
        />
        <div
          className="absolute top-0 right-0 w-4 h-4 border-t border-r rounded-tr-xl transition-opacity duration-500"
          style={{
            borderColor: colors.glow,
            opacity: isHovered ? 0.5 : 0.15,
          }}
        />
        <div
          className="absolute bottom-0 left-0 w-4 h-4 border-b border-l rounded-bl-xl transition-opacity duration-500"
          style={{
            borderColor: colors.glow,
            opacity: isHovered ? 0.5 : 0.15,
          }}
        />
        <div
          className="absolute bottom-0 right-0 w-4 h-4 border-b border-r rounded-br-xl transition-opacity duration-500"
          style={{
            borderColor: colors.glow,
            opacity: isHovered ? 0.5 : 0.15,
          }}
        />
      </div>
    </motion.div>
  )
}
