import React, { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, Mail, BookOpen, Brain, GitBranch, Car, Grid3X3,
  Mic, ChevronUp, X
} from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'

/**
 * S-GLOBAL DOMINION — Floating Dock v3.2 (ABSOLUTE CENTER)
 * =========================================================
 * VERSHINA v200.29.2 Protocol — «Герметизация + Ivory Luxe»
 * - АБСОЛЮТНОЕ центрирование через style (не только Tailwind)
 * - z-index: 9999 — поверх всего
 * - Hover: градиент bg-gradient-to-t + LED glow
 * - Ivory Luxe: чёрные иконки (#000000) с матовым отблеском
 * - isStub: заглушки с grayscale + тултип «В СЛЕДУЮЩЕМ ЦИКЛЕ»
 */

const DRAWER_BUTTONS = [
  { id: 'search',  icon: Search,    label: 'Поиск',    color: '#00f5ff', colorRgb: '0, 245, 255',   isStub: false },
  { id: 'email',   icon: Mail,      label: 'Email',    color: '#a855f7', colorRgb: '168, 85, 247',  isStub: true  },
  { id: 'book',    icon: BookOpen,  label: 'Книжка',   color: '#f0c060', colorRgb: '240, 192, 96',  isStub: true  },
  { id: 'ai',      icon: Brain,     label: 'AI',       color: '#00ff88', colorRgb: '0, 255, 136',   isStub: true  },
  { id: 'mindmap', icon: GitBranch, label: 'MindMap',  color: '#06b6d4', colorRgb: '6, 182, 212',   isStub: true  },
  { id: 'fleet',   icon: Car,       label: 'Флот',     color: '#f97316', colorRgb: '249, 115, 22',  isStub: true  },
  { id: 'matrix',  icon: Grid3X3,   label: 'Матрица',  color: '#ef4444', colorRgb: '239, 68, 68',   isStub: true  },
]

export default function BottomDrawer() {
  const [isOpen, setIsOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchValue, setSearchValue] = useState('')
  const [activeId, setActiveId] = useState(null)
  const hoverZoneRef = useRef(null)
  const { theme } = useTheme()
  const isIvory = theme === 'ivory'

  const handleButtonClick = (id) => {
    // Цифровая гигиена: заглушки не меняют состояние activeId
    const btn = DRAWER_BUTTONS.find(b => b.id === id)
    if (btn?.isStub) return
    setActiveId(id)
    if (id === 'search') {
      setSearchOpen(prev => !prev)
    }
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
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          height: '32px',
          zIndex: 9998,
        }}
        onMouseEnter={() => setIsOpen(true)}
      />

      {/* Индикатор-подсказка */}
      <AnimatePresence>
        {!isOpen && (
          /* Внешний div держит горизонтальное центрирование — Framer не трогает transform */
          <div
            style={{
              position: 'fixed',
              bottom: '12px',
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 9997,
              cursor: 'pointer',
            }}
            onClick={() => setIsOpen(true)}
          >
            <motion.div
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              transition={{ duration: 0.3 }}
            >
              <motion.div
                animate={{ y: [0, -4, 0] }}
                transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
              >
                <ChevronUp
                  size={16}
                  style={{ color: isIvory ? 'rgba(139,105,20,0.5)' : 'rgba(212,168,67,0.4)' }}
                />
              </motion.div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Панель */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Оверлей для закрытия */}
            <motion.div
              style={{
                position: 'fixed',
                inset: 0,
                zIndex: 9996,
              }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => { setIsOpen(false); setSearchOpen(false); setActiveId(null) }}
            />

            {/* === FLOATING DOCK — АБСОЛЮТНЫЙ ЦЕНТР ===
                Внешний div держит left:50% + translateX(-50%) — Framer не трогает.
                motion.div внутри анимирует только y/opacity/scale. */}
            <div
              style={{
                position: 'fixed',
                bottom: '32px',
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 9999,
                width: 'max-content',
              }}
            >
            <motion.div
              initial={{ y: 120, opacity: 0, scale: 0.9 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              exit={{ y: 120, opacity: 0, scale: 0.9 }}
              transition={{ type: 'spring', stiffness: 320, damping: 28 }}
              onMouseLeave={() => { if (!searchOpen) { setIsOpen(false) } }}
            >
              {/* Поле поиска (раскрывается над доком) */}
              <AnimatePresence>
                {searchOpen && (
                  <motion.form
                    style={{ marginBottom: '12px', width: '100%' }}
                    initial={{ height: 0, opacity: 0, y: 10 }}
                    animate={{ height: 'auto', opacity: 1, y: 0 }}
                    exit={{ height: 0, opacity: 0, y: 10 }}
                    transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                    onSubmit={handleSearchSubmit}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        padding: '12px 16px',
                        borderRadius: '16px',
                        background: isIvory
                          ? 'rgba(245, 244, 230, 0.92)'
                          : 'rgba(var(--card-bg-rgb, 10,10,10), 0.85)',
                        backdropFilter: 'blur(20px) saturate(180%)',
                        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
                        border: isIvory
                          ? '1px solid rgba(139,105,20,0.25)'
                          : '1px solid rgba(255, 255, 255, 0.12)',
                        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
                      }}
                    >
                      <Search size={16} style={{ color: 'var(--text-label)', flexShrink: 0 }} />
                      <input
                        type="text"
                        value={searchValue}
                        onChange={(e) => setSearchValue(e.target.value)}
                        onKeyDown={(e) => e.key === 'Escape' && setSearchOpen(false)}
                        placeholder="Поиск по империи... (Esc — закрыть)"
                        aria-label="Поиск по S-GLOBAL DOMINION"
                        style={{
                          flex: 1,
                          background: 'transparent',
                          outline: 'none',
                          fontSize: '14px',
                          fontFamily: 'Montserrat, sans-serif',
                          color: 'var(--text-primary)',
                        }}
                        autoFocus
                      />
                      <motion.button
                        type="button"
                        style={{
                          padding: '6px',
                          borderRadius: '8px',
                          color: 'var(--text-label)',
                          background: 'transparent',
                          border: 'none',
                          cursor: 'pointer',
                          opacity: 0.5,  // Голосовой ввод — заглушка, визуально приглушён
                        }}
                        whileHover={{ scale: 1.15, backgroundColor: 'rgba(255,255,255,0.1)', opacity: 1 }}
                        whileTap={{ scale: 0.9 }}
                        title="Голосовой ввод (скоро)"
                        aria-label="Голосовой ввод (в разработке)"
                        disabled
                      >
                        <Mic size={16} />
                      </motion.button>
                      <motion.button
                        type="submit"
                        style={{
                          padding: '6px 12px',
                          borderRadius: '8px',
                          fontSize: '11px',
                          fontFamily: 'Orbitron, sans-serif',
                          fontWeight: 700,
                          letterSpacing: '0.1em',
                          background: 'rgba(212,168,67,0.2)',
                          color: '#d4a843',
                          border: '1px solid rgba(212,168,67,0.3)',
                          cursor: 'pointer',
                        }}
                        whileHover={{ scale: 1.05, backgroundColor: 'rgba(212,168,67,0.3)' }}
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
                style={{
                  position: 'relative',
                  display: 'flex',
                  alignItems: 'flex-end',
                  gap: '8px',
                  padding: '12px 20px',
                  borderRadius: '24px',
                  background: isIvory
                    ? 'rgba(253, 252, 240, 0.92)'
                    : 'rgba(13, 13, 26, 0.88)',
                  backdropFilter: 'blur(24px) saturate(200%)',
                  WebkitBackdropFilter: 'blur(24px) saturate(200%)',
                  border: isIvory
                    ? '1px solid rgba(139,105,20,0.3)'
                    : '1px solid rgba(255,255,255,0.1)',
                  boxShadow: isIvory
                    ? '0 20px 50px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.8)'
                    : '0 20px 50px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.08)',
                }}
              >
                {/* Верхняя декоративная линия */}
                <div
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: '32px',
                    right: '32px',
                    height: '1px',
                    overflow: 'hidden',
                    borderRadius: '9999px',
                  }}
                >
                  <motion.div
                    style={{
                      height: '100%',
                      width: '100%',
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
                    isIvory={isIvory}
                    onClick={() => handleButtonClick(btn.id)}
                  />
                ))}

                {/* Кнопка закрытия */}
                <motion.button
                  style={{
                    marginLeft: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    background: isIvory ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.05)',
                    border: isIvory ? '1px solid rgba(0,0,0,0.12)' : '1px solid rgba(255,255,255,0.08)',
                    color: isIvory ? 'rgba(0,0,0,0.5)' : 'rgba(255,255,255,0.4)',
                    cursor: 'pointer',
                  }}
                  onClick={() => { setIsOpen(false); setSearchOpen(false); setActiveId(null) }}
                  whileHover={{ scale: 1.15, background: isIvory ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.1)' }}
                  whileTap={{ scale: 0.9 }}
                >
                  <X size={12} />
                </motion.button>
              </div>
            </motion.div>
            </div>  {/* /внешний div центрирования */}
          </>
        )}
      </AnimatePresence>
    </>
  )
}

/**
 * Отдельный компонент кнопки дока
 * VERSHINA v200.29.1 — Vibrant Interaction + Stub UX:
 * - Hover: градиент снизу вверх (bg-gradient-to-t)
 * - LED точка под иконкой с drop-shadow
 * - Ivory Luxe: чёрные иконки (#000000) с матовым отблеском
 * - isStub: grayscale(0.85) + opacity(0.55) + тултип «В СЛЕДУЮЩЕМ ЦИКЛЕ»
 */
function DockButton({ btn, index, isActive, isIvory, onClick }) {
  const [isHovered, setIsHovered] = useState(false)
  const isStub = btn.isStub === true

  // Ivory: иконки чёрные, при hover — цвет темы (изумрудный/золотой)
  // Заглушки: цвет приглушён независимо от темы
  const iconColor = isStub
    ? (isIvory ? 'rgba(0,0,0,0.35)' : 'rgba(255,255,255,0.25)')
    : isIvory
      ? (isHovered ? btn.color : '#000000')
      : (isHovered ? btn.color : `rgba(${btn.colorRgb}, 0.65)`)

  const labelColor = isStub
    ? (isIvory ? 'rgba(0,0,0,0.3)' : 'rgba(255,255,255,0.25)')
    : isIvory
      ? (isHovered ? btn.color : 'rgba(0,0,0,0.75)')
      : (isHovered ? btn.color : 'rgba(255,255,255,0.5)')

  return (
    <motion.div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        // Тултип через CSS title — нативный, без зависимостей
      }}
      title={isStub ? 'В СЛЕДУЮЩЕМ ЦИКЛЕ' : undefined}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Кнопка */}
      <motion.button
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '6px',
          padding: '10px 12px',
          borderRadius: '16px',
          minWidth: '60px',
          // Заглушки: серый курсор + grayscale + пониженная прозрачность
          cursor: isStub ? 'not-allowed' : 'pointer',
          opacity: isStub ? 0.55 : 1,
          filter: isStub ? 'grayscale(0.85)' : 'none',
          border: isHovered && !isStub
            ? `1px solid rgba(${btn.colorRgb}, 0.45)`
            : isIvory
              ? '1px solid rgba(0,0,0,0.08)'
              : '1px solid rgba(255,255,255,0.06)',
          // Hover: градиент снизу вверх — «Vibrant Interaction» (только для активных)
          background: isHovered && !isStub
            ? `linear-gradient(to top, rgba(${btn.colorRgb}, 0.22) 0%, rgba(${btn.colorRgb}, 0.06) 100%)`
            : isIvory
              ? 'rgba(0,0,0,0.03)'
              : 'rgba(255,255,255,0.03)',
          transition: 'background 0.2s ease, border-color 0.2s ease, opacity 0.2s ease',
        }}
        animate={{
          scale: isHovered && !isStub ? 1.22 : 1,
          y: isHovered && !isStub ? -10 : 0,
        }}
        transition={{
          type: 'spring',
          stiffness: 450,
          damping: 18,
          mass: 0.8,
        }}
        whileTap={isStub ? {} : { scale: 0.92 }}
        onHoverStart={() => setIsHovered(true)}
        onHoverEnd={() => setIsHovered(false)}
        onClick={isStub ? undefined : onClick}
      >
        {/* Иконка — glow при наведении (только для активных кнопок) */}
        <motion.div
          animate={{
            filter: isHovered && !isStub
              ? `drop-shadow(0 0 10px rgba(${btn.colorRgb}, 1)) drop-shadow(0 0 20px rgba(${btn.colorRgb}, 0.5))`
              : isIvory
                ? 'drop-shadow(0 1px 2px rgba(0,0,0,0.15))'  // матовый отблеск в Ivory
                : 'none',
          }}
          transition={{ duration: 0.15 }}
        >
          <btn.icon
            size={20}
            style={{
              color: iconColor,
              transition: 'color 0.15s ease',
            }}
          />
        </motion.div>

        {/* Лейбл */}
        <span
          style={{
            fontSize: '9px',
            fontFamily: 'Orbitron, sans-serif',
            letterSpacing: '0.08em',
            color: labelColor,
            transition: 'color 0.15s ease',
            fontWeight: isHovered && !isStub ? 700 : (isIvory ? 600 : 400),
          }}
        >
          {btn.label}
        </span>
      </motion.button>

      {/* LED точка — светящаяся под активной/наведённой кнопкой (только для активных) */}
      <AnimatePresence>
        {(isHovered || isActive) && !isStub && (
          <motion.div
            style={{
              position: 'absolute',
              bottom: '-8px',
              left: '50%',
              transform: 'translateX(-50%)',
            }}
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0 }}
            transition={{ type: 'spring', stiffness: 500, damping: 20 }}
          >
            <div
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: btn.color,
                boxShadow: `0 0 8px rgba(${btn.colorRgb}, 1), 0 0 16px rgba(${btn.colorRgb}, 0.6), 0 0 24px rgba(${btn.colorRgb}, 0.3)`,
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
