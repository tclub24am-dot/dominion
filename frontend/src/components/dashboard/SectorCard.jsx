import React, { useState } from 'react'
import { motion } from 'framer-motion'

/**
 * S-GLOBAL DOMINION — Sector Card (Glassmorphism)
 * Карточка сектора империи с неоновым glow-свечением
 * 
 * Props:
 *   code     — код сектора (FL, LG, IT, ...)
 *   title    — название сектора
 *   subtitle — подзаголовок / статус
 *   icon     — Lucide icon component
 *   color    — цвет свечения (hex)
 *   index    — индекс для stagger-анимации
 *   theme    — 'dark' | 'ivory'
 */

// Цветовая палитра для каждого сектора
const SECTOR_COLORS = {
  FL: { glow: '#00f5ff', accent: '#00f5ff', gradient: 'from-cyan-500/20 to-cyan-500/5' },
  LG: { glow: '#00ff88', accent: '#00ff88', gradient: 'from-emerald-500/20 to-emerald-500/5' },
  IT: { glow: '#a855f7', accent: '#a855f7', gradient: 'from-purple-500/20 to-purple-500/5' },
  WH: { glow: '#f97316', accent: '#f97316', gradient: 'from-orange-500/20 to-orange-500/5' },
  AI: { glow: '#06b6d4', accent: '#06b6d4', gradient: 'from-cyan-600/20 to-cyan-600/5' },
  IM: { glow: '#8b5cf6', accent: '#8b5cf6', gradient: 'from-violet-500/20 to-violet-500/5' },
  GP: { glow: '#22d3ee', accent: '#22d3ee', gradient: 'from-cyan-400/20 to-cyan-400/5' },
  TS: { glow: '#f59e0b', accent: '#f59e0b', gradient: 'from-amber-500/20 to-amber-500/5' },
  MR: { glow: '#ef4444', accent: '#ef4444', gradient: 'from-red-500/20 to-red-500/5' },
  IV: { glow: '#10b981', accent: '#10b981', gradient: 'from-emerald-600/20 to-emerald-600/5' },
  FP: { glow: '#d4a843', accent: '#d4a843', gradient: 'from-yellow-600/20 to-yellow-600/5' },
  AC: { glow: '#ec4899', accent: '#ec4899', gradient: 'from-pink-500/20 to-pink-500/5' },
}

export default function SectorCard({ code, title, subtitle, icon: Icon, index = 0, theme = 'dark' }) {
  const [isHovered, setIsHovered] = useState(false)
  const isDark = theme === 'dark'
  const colors = SECTOR_COLORS[code] || SECTOR_COLORS.FL

  return (
    <motion.div
      className="relative group"
      initial={{ opacity: 0, y: 30, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{
        duration: 0.5,
        delay: index * 0.08,
        ease: [0.16, 1, 0.3, 1],
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Внешний неоновый glow */}
      <motion.div
        className="absolute -inset-0.5 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-sm"
        style={{
          background: `linear-gradient(135deg, ${colors.glow}40, transparent, ${colors.glow}20)`,
        }}
        animate={isHovered ? { opacity: 0.6 } : { opacity: 0 }}
      />

      {/* Карточка */}
      <div
        className={`
          relative overflow-hidden rounded-xl border p-5
          transition-all duration-300 cursor-pointer
          ${isDark
            ? 'bg-white/[0.03] border-white/[0.08] hover:border-white/[0.15]'
            : 'bg-white/60 border-ivory-border hover:border-ivory-gold/40'
          }
        `}
        style={{
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          boxShadow: isHovered
            ? `0 8px 32px rgba(0,0,0,${isDark ? '0.6' : '0.1'}), 0 0 20px ${colors.glow}15, inset 0 1px 0 rgba(255,255,255,${isDark ? '0.05' : '0.8'})`
            : `0 4px 16px rgba(0,0,0,${isDark ? '0.4' : '0.05'}), inset 0 1px 0 rgba(255,255,255,${isDark ? '0.03' : '0.6'})`,
        }}
      >
        {/* Фоновый градиент */}
        <div
          className="absolute inset-0 opacity-30 transition-opacity duration-500 group-hover:opacity-50"
          style={{
            background: `radial-gradient(ellipse at top right, ${colors.glow}08, transparent 70%)`,
          }}
        />

        {/* Сканирующая линия при ховере */}
        {isHovered && (
          <motion.div
            className="absolute left-0 right-0 h-px pointer-events-none"
            style={{
              background: `linear-gradient(90deg, transparent, ${colors.glow}60, transparent)`,
            }}
            initial={{ top: 0 }}
            animate={{ top: '100%' }}
            transition={{ duration: 1.5, ease: 'linear' }}
          />
        )}

        {/* Верхняя часть: Бейдж + Статус */}
        <div className="relative flex items-start justify-between mb-4">
          {/* Бейдж сектора */}
          <motion.div
            className="flex items-center justify-center w-11 h-11 rounded-lg"
            style={{
              background: isDark
                ? `linear-gradient(135deg, ${colors.glow}20, ${colors.glow}05)`
                : `linear-gradient(135deg, ${colors.glow}15, ${colors.glow}05)`,
              border: `1px solid ${colors.glow}${isDark ? '40' : '30'}`,
              boxShadow: isHovered ? `0 0 12px ${colors.glow}30` : 'none',
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
          className="text-[10px] font-orbitron font-bold tracking-[0.3em] uppercase mb-1.5"
          style={{ color: `${colors.accent}${isDark ? 'aa' : '80'}` }}
        >
          {code}
        </div>

        {/* Название */}
        <h3
          className={`
            font-montserrat font-bold text-[15px] leading-tight mb-2
            ${isDark ? 'text-white/90' : 'text-ivory-text'}
          `}
        >
          {title}
        </h3>

        {/* Подзаголовок */}
        <p
          className={`
            text-xs font-montserrat
            ${isDark ? 'text-dominion-muted' : 'text-ivory-muted'}
          `}
        >
          {subtitle}
        </p>

        {/* Нижняя линия-акцент */}
        <motion.div
          className="absolute bottom-0 left-0 right-0 h-[2px]"
          style={{
            background: `linear-gradient(90deg, transparent, ${colors.glow}, transparent)`,
          }}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: isHovered ? 1 : 0 }}
          transition={{ duration: 0.3 }}
        />

        {/* Угловые декоративные элементы */}
        <div
          className="absolute top-0 left-0 w-4 h-4 border-t border-l rounded-tl-xl opacity-0 group-hover:opacity-40 transition-opacity duration-500"
          style={{ borderColor: colors.glow }}
        />
        <div
          className="absolute top-0 right-0 w-4 h-4 border-t border-r rounded-tr-xl opacity-0 group-hover:opacity-40 transition-opacity duration-500"
          style={{ borderColor: colors.glow }}
        />
        <div
          className="absolute bottom-0 left-0 w-4 h-4 border-b border-l rounded-bl-xl opacity-0 group-hover:opacity-40 transition-opacity duration-500"
          style={{ borderColor: colors.glow }}
        />
        <div
          className="absolute bottom-0 right-0 w-4 h-4 border-b border-r rounded-br-xl opacity-0 group-hover:opacity-40 transition-opacity duration-500"
          style={{ borderColor: colors.glow }}
        />
      </div>
    </motion.div>
  )
}

export { SECTOR_COLORS }
