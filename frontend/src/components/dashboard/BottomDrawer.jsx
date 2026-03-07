import React, { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, Mail, BookOpen, Brain, GitBranch, Car, Grid3X3,
  Mic, ChevronUp, X
} from 'lucide-react'

/**
 * S-GLOBAL DOMINION — Floating Dock v2.0 (Premium macOS-style)
 * =============================================================
 * VERSHINA v200.15 Protocol — «Панель управления дорогой яхты»
 * - Floating: отступ от краёв, border-radius 24px
 * - Glassmorphism: backdrop-filter blur(20px) saturate(180%)
 * - Hover: scale(1.2) + translateY(-8px) + indicator dot
 * - Полная адаптация к темам через CSS-переменные
 */

const DRAWER_BUTTONS = [
  { id: 'search',  icon: Search,    label: 'Поиск',    color: '#00f5ff', colorRgb: '0, 245, 255' },
  { id: 'email',   icon: Mail,      label: 'Email',    color: '#a855f7', colorRgb: '168, 85, 247' },
  { id: 'book',    icon: BookOpen,  label: 'Книжка',   color: '#f0c060', colorRgb: '240, 192, 96' },
  { id: 'ai',      icon: Brain,     label: 'AI',       color: '#00ff88', colorRgb: '0, 255, 136' },
  { id: 'mindmap', icon: GitBranch, label: 'MindMap',  color: '#06b6d4', colorRgb: '6, 182, 212' },
  { id: 'fleet',   icon: Car,       label: 'Флот',     color: '#f97316', colorRgb: '249, 115, 22' },
  { id: 'matrix',  icon: Grid3X3,   label: 'Матрица',  color: '#ef4444', colorRgb: '239, 68, 68' },
]

export default function BottomDrawer() {
  const [isOpen, setIsOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchValue, setSearchValue] = useState('')
  const [activeId, setActiveId] = useState(null)
  const hoverZoneRef = useRef(null)

  const handleButtonClick = (id) => {
    setActiveId(id)
    if (id === 'search') {
      setSearchOpen(prev => !prev)
    }
    // Другие кнопки — заглушки для будущего функционала
  }

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    if (searchValue.trim()) {
      // TODO: Интеграция с поиском
    }
  }

  return (
    <>
      {/* Зона активации (невидимая полоса внизу экрана) */}
      <div
        ref={hoverZoneRef}
        className="fixed bottom-0 left-0 right-0 h-8 z-[60]"
        onMouseEnter={() => setIsOpen(true)}
      />

      {/* Индикатор-подсказка */}
      <AnimatePresence>
        {!isOpen && (
          <motion.div
            className="fixed bottom-3 left-1/2 -translate-x-1/2 z-[59] flex items-center gap-2 cursor-pointer"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ duration: 0.3 }}
            onClick={() => setIsOpen(true)}
          >
            <motion.div
              animate={{ y: [0, -4, 0] }}
              transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
            >
              <ChevronUp
                size={16}
                className="text-dominion-gold/40"
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Панель */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Оверлей для закрытия */}
            <motion.div
              className="fixed inset-0 z-[58]"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => { setIsOpen(false); setSearchOpen(false); setActiveId(null) }}
            />

            {/* === FLOATING DOCK === */}
            <motion.div
              className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[60]"
              initial={{ y: 120, opacity: 0, scale: 0.9 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              exit={{ y: 120, opacity: 0, scale: 0.9 }}
              transition={{ type: 'spring', stiffness: 320, damping: 28 }}
              onMouseLeave={() => { setIsOpen(false); setSearchOpen(false) }}
            >
              {/* Поле поиска (раскрывается над доком) */}
              <AnimatePresence>
                {searchOpen && (
                  <motion.form
                    className="mb-3 w-full"
                    initial={{ height: 0, opacity: 0, y: 10 }}
                    animate={{ height: 'auto', opacity: 1, y: 0 }}
                    exit={{ height: 0, opacity: 0, y: 10 }}
                    transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                    onSubmit={handleSearchSubmit}
                  >
                    <div
                      className="flex items-center gap-3 px-4 py-3 rounded-2xl border"
                      style={{
                        background: 'rgba(var(--card-bg-rgb), 0.75)',
                        backdropFilter: 'blur(20px) saturate(180%)',
                        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
                        border: '1px solid rgba(255, 255, 255, 0.12)',
                        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
                      }}
                    >
                      <Search size={16} className="text-dominion-muted flex-shrink-0" />
                      <input
                        type="text"
                        value={searchValue}
                        onChange={(e) => setSearchValue(e.target.value)}
                        placeholder="Поиск по империи..."
                        className="flex-1 bg-transparent outline-none text-sm font-montserrat placeholder:text-dominion-muted/50"
                        style={{ color: 'var(--text-primary)' }}
                        autoFocus
                      />
                      <motion.button
                        type="button"
                        className="p-1.5 rounded-lg transition-colors hover:bg-white/10"
                        style={{ color: 'var(--text-label)' }}
                        whileHover={{ scale: 1.15 }}
                        whileTap={{ scale: 0.9 }}
                        title="Голосовой ввод"
                      >
                        <Mic size={16} />
                      </motion.button>
                      <motion.button
                        type="submit"
                        className="px-3 py-1.5 rounded-lg text-xs font-orbitron font-bold tracking-wider bg-dominion-gold/20 text-dominion-gold border border-dominion-gold/30 hover:bg-dominion-gold/30"
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                      >
                        ENTER
                      </motion.button>
                    </div>
                  </motion.form>
                )}
              </AnimatePresence>

              {/* Основной контейнер дока */}
              <div
                className="relative flex items-end gap-2 px-5 py-3 dock-container"
                style={{
                  borderRadius: '24px',
                  boxShadow: '0 20px 50px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.08)',
                }}
              >
                {/* Верхняя декоративная линия */}
                <div className="absolute top-0 left-8 right-8 h-px overflow-hidden rounded-full">
                  <motion.div
                    className="h-full w-full"
                    style={{
                      background: 'linear-gradient(90deg, transparent, var(--accent, #d4a843), transparent)',
                    }}
                    animate={{ opacity: [0.2, 0.6, 0.2] }}
                    transition={{ duration: 3, repeat: Infinity }}
                  />
                </div>

                {/* Кнопки дока */}
                {DRAWER_BUTTONS.map((btn, i) => (
                  <DockButton
                    key={btn.id}
                    btn={btn}
                    index={i}
                    isActive={activeId === btn.id}
                    onClick={() => handleButtonClick(btn.id)}
                  />
                ))}

                {/* Кнопка закрытия */}
                <motion.button
                  className="ml-2 flex items-center justify-center w-8 h-8 rounded-full"
                  style={{
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    color: 'var(--text-secondary, rgba(255,255,255,0.4))',
                  }}
                  onClick={() => { setIsOpen(false); setSearchOpen(false); setActiveId(null) }}
                  whileHover={{ scale: 1.15, background: 'rgba(255,255,255,0.1)' }}
                  whileTap={{ scale: 0.9 }}
                >
                  <X size={12} />
                </motion.button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  )
}

/**
 * Отдельный компонент кнопки дока с hover-эффектом macOS-style
 * Магнитный spring: cubic-bezier(0.175, 0.885, 0.32, 1.275) — «подпрыгивание»
 */
function DockButton({ btn, index, isActive, onClick }) {
  const [isHovered, setIsHovered] = useState(false)

  return (
    <motion.div
      className="relative flex flex-col items-center"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Кнопка */}
      <motion.button
        className="relative flex flex-col items-center gap-1.5 px-3 py-2.5 rounded-2xl"
        style={{
          background: isHovered
            ? `rgba(${btn.colorRgb}, 0.15)`
            : 'rgba(255, 255, 255, 0.03)',
          border: isHovered
            ? `1px solid rgba(${btn.colorRgb}, 0.4)`
            : '1px solid rgba(255, 255, 255, 0.06)',
          minWidth: '60px',
          transition: 'background 0.2s ease, border-color 0.2s ease',
        }}
        animate={{
          scale: isHovered ? 1.22 : 1,
          y: isHovered ? -10 : 0,
        }}
        transition={{
          type: 'spring',
          stiffness: 450,
          damping: 18,
          mass: 0.8,
        }}
        whileTap={{ scale: 0.92 }}
        onHoverStart={() => setIsHovered(true)}
        onHoverEnd={() => setIsHovered(false)}
        onClick={onClick}
      >
        {/* Иконка — усиленный glow при наведении */}
        <motion.div
          animate={{
            filter: isHovered
              ? `drop-shadow(0 0 10px rgba(${btn.colorRgb}, 1)) drop-shadow(0 0 20px rgba(${btn.colorRgb}, 0.5))`
              : 'none',
          }}
          transition={{ duration: 0.15 }}
        >
          <btn.icon
            size={20}
            style={{
              color: isHovered ? btn.color : `rgba(${btn.colorRgb}, 0.65)`,
              transition: 'color 0.15s ease',
            }}
          />
        </motion.div>

        {/* Лейбл */}
        <span
          className="text-[9px] font-orbitron tracking-wider"
          style={{
            color: isHovered ? btn.color : 'var(--text-secondary, rgba(255,255,255,0.4))',
            transition: 'color 0.15s ease',
            fontWeight: isHovered ? 700 : 400,
          }}
        >
          {btn.label}
        </span>
      </motion.button>

      {/* Indicator dot — светящаяся точка под активной/наведённой кнопкой */}
      <AnimatePresence>
        {(isHovered || isActive) && (
          <motion.div
            className="absolute -bottom-2 left-1/2 -translate-x-1/2"
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0 }}
            transition={{ type: 'spring', stiffness: 500, damping: 20 }}
          >
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{
                background: btn.color,
                boxShadow: `0 0 8px rgba(${btn.colorRgb}, 1), 0 0 16px rgba(${btn.colorRgb}, 0.5)`,
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
