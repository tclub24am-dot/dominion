import React, { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, Mail, BookOpen, Brain, GitBranch, Car, Grid3X3,
  Mic, ChevronUp, X
} from 'lucide-react'

/**
 * S-GLOBAL DOMINION — Bottom Drawer (Hover Reveal)
 * Выдвижная нижняя панель с кнопками быстрого доступа
 * Скрыта внизу, плавно выплывает при наведении мыши
 */

const DRAWER_BUTTONS = [
  { id: 'search',  icon: Search,    label: 'Поиск',    color: '#00f5ff' },
  { id: 'email',   icon: Mail,      label: 'Email',    color: '#a855f7' },
  { id: 'book',    icon: BookOpen,  label: 'Книжка',   color: '#f0c060' },
  { id: 'ai',      icon: Brain,     label: 'AI',       color: '#00ff88' },
  { id: 'mindmap', icon: GitBranch, label: 'MindMap',  color: '#06b6d4' },
  { id: 'fleet',   icon: Car,       label: 'Флот',     color: '#f97316' },
  { id: 'matrix',  icon: Grid3X3,   label: 'Матрица',  color: '#ef4444' },
]

export default function BottomDrawer({ theme = 'dark' }) {
  const [isOpen, setIsOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchValue, setSearchValue] = useState('')
  const hoverZoneRef = useRef(null)
  const isDark = theme === 'dark'

  const handleButtonClick = (id) => {
    if (id === 'search') {
      setSearchOpen(prev => !prev)
    }
    // Другие кнопки — заглушки для будущего функционала
  }

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    if (searchValue.trim()) {
      console.log('[DOMINION] Search:', searchValue)
      // TODO: Интеграция с поиском
    }
  }

  return (
    <>
      {/* Зона активации (невидимая полоса внизу экрана) */}
      <div
        ref={hoverZoneRef}
        className="fixed bottom-0 left-0 right-0 h-6 z-[60]"
        onMouseEnter={() => setIsOpen(true)}
      />

      {/* Индикатор-подсказка */}
      <AnimatePresence>
        {!isOpen && (
          <motion.div
            className="fixed bottom-2 left-1/2 -translate-x-1/2 z-[59] flex items-center gap-2 cursor-pointer"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ duration: 0.3 }}
            onClick={() => setIsOpen(true)}
          >
            <motion.div
              animate={{ y: [0, -3, 0] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
            >
              <ChevronUp
                size={16}
                className={isDark ? 'text-dominion-gold/40' : 'text-ivory-gold/40'}
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
              onClick={() => { setIsOpen(false); setSearchOpen(false) }}
            />

            {/* Drawer */}
            <motion.div
              className={`
                fixed bottom-0 left-0 right-0 z-[60]
                border-t backdrop-blur-xl
                ${isDark
                  ? 'bg-dominion-deep/95 border-dominion-gold/20'
                  : 'bg-ivory-card/95 border-ivory-border'
                }
              `}
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              onMouseLeave={() => { setIsOpen(false); setSearchOpen(false) }}
            >
              {/* Верхняя декоративная линия */}
              <div className="absolute top-0 left-0 right-0 h-px overflow-hidden">
                <motion.div
                  className="h-full w-full"
                  style={{
                    background: isDark
                      ? 'linear-gradient(90deg, transparent, #d4a843, transparent)'
                      : 'linear-gradient(90deg, transparent, #b8860b, transparent)',
                  }}
                  animate={{ opacity: [0.3, 0.8, 0.3] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
              </div>

              {/* Кнопка закрытия */}
              <motion.button
                className={`
                  absolute top-2 right-4 p-1 rounded-full
                  ${isDark ? 'text-dominion-muted hover:text-white' : 'text-ivory-muted hover:text-ivory-text'}
                `}
                onClick={() => { setIsOpen(false); setSearchOpen(false) }}
                whileHover={{ scale: 1.2 }}
                whileTap={{ scale: 0.9 }}
              >
                <X size={14} />
              </motion.button>

              {/* Контент */}
              <div className="px-6 py-4">
                {/* Кнопки быстрого доступа */}
                <div className="flex items-center justify-center gap-3 flex-wrap">
                  {DRAWER_BUTTONS.map((btn, i) => (
                    <motion.button
                      key={btn.id}
                      className={`
                        flex flex-col items-center gap-1.5 px-4 py-3 rounded-xl
                        transition-all duration-300 min-w-[72px]
                        ${isDark
                          ? 'bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.15]'
                          : 'bg-white/40 border border-ivory-border hover:border-ivory-gold/30'
                        }
                      `}
                      style={{
                        boxShadow: 'none',
                      }}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.05, duration: 0.3 }}
                      whileHover={{
                        scale: 1.08,
                        boxShadow: `0 0 20px ${btn.color}25, 0 4px 12px rgba(0,0,0,0.3)`,
                        borderColor: `${btn.color}50`,
                      }}
                      whileTap={{ scale: 0.95 }}
                      onClick={() => handleButtonClick(btn.id)}
                    >
                      <btn.icon
                        size={18}
                        style={{ color: btn.color }}
                      />
                      <span
                        className={`text-[10px] font-orbitron tracking-wider ${isDark ? 'text-dominion-muted' : 'text-ivory-muted'}`}
                      >
                        {btn.label}
                      </span>
                    </motion.button>
                  ))}
                </div>

                {/* Поле поиска (раскрывается) */}
                <AnimatePresence>
                  {searchOpen && (
                    <motion.form
                      className="mt-4"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.3 }}
                      onSubmit={handleSearchSubmit}
                    >
                      <div
                        className={`
                          flex items-center gap-3 px-4 py-3 rounded-xl border
                          ${isDark
                            ? 'bg-white/[0.03] border-white/[0.08] focus-within:border-dominion-neon/40'
                            : 'bg-white/60 border-ivory-border focus-within:border-ivory-gold/40'
                          }
                        `}
                        style={{
                          backdropFilter: 'blur(20px)',
                        }}
                      >
                        <Search
                          size={16}
                          className={isDark ? 'text-dominion-muted' : 'text-ivory-muted'}
                        />
                        <input
                          type="text"
                          value={searchValue}
                          onChange={(e) => setSearchValue(e.target.value)}
                          placeholder="Поиск по империи..."
                          className={`
                            flex-1 bg-transparent outline-none text-sm font-montserrat
                            placeholder:text-dominion-muted/50
                            ${isDark ? 'text-white' : 'text-ivory-text placeholder:text-ivory-muted/50'}
                          `}
                          autoFocus
                        />
                        {/* Иконка микрофона (голосовой ввод) */}
                        <motion.button
                          type="button"
                          className={`
                            p-1.5 rounded-lg transition-colors
                            ${isDark
                              ? 'hover:bg-white/10 text-dominion-muted hover:text-dominion-neon'
                              : 'hover:bg-ivory-gold/10 text-ivory-muted hover:text-ivory-gold'
                            }
                          `}
                          whileHover={{ scale: 1.15 }}
                          whileTap={{ scale: 0.9 }}
                          title="Голосовой ввод"
                        >
                          <Mic size={16} />
                        </motion.button>
                        {/* Кнопка Enter */}
                        <motion.button
                          type="submit"
                          className={`
                            px-3 py-1.5 rounded-lg text-xs font-orbitron font-bold tracking-wider
                            transition-colors
                            ${isDark
                              ? 'bg-dominion-gold/20 text-dominion-gold border border-dominion-gold/30 hover:bg-dominion-gold/30'
                              : 'bg-ivory-gold/20 text-ivory-gold border border-ivory-gold/30 hover:bg-ivory-gold/30'
                            }
                          `}
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                        >
                          ENTER
                        </motion.button>
                      </div>
                    </motion.form>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
