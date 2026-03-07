import React, { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Shield, LogOut } from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'
import ThemeSwitcher from './ThemeSwitcher'

/**
 * S-GLOBAL DOMINION — Top Bar v3.1 (HQ Status Panel)
 * ====================================================
 * VERSHINA v200.17 Protocol — АБСОЛЮТНЫЙ ПОРЯДОК
 * - tabular-nums + width: 120px — часы не двигают иконки
 * - LogOut кнопка: Ivory=#1A1A1B, тёмные=приглушённый красный
 * - Полная адаптация к темам через CSS-переменные
 */
export default function TopBar() {
  const [time, setTime] = useState(new Date())
  const { theme } = useTheme()

  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(interval)
  }, [])

  const formatTime = (d) => {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  const formatDate = (d) => {
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  }

  const handleLogout = async () => {
    try {
      await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'include' })
    } catch (_) {
      // Игнорируем ошибку сети — всё равно очищаем сессию
    }
    sessionStorage.clear()
    localStorage.clear()
    window.location.href = '/login'
  }

  // Цвет кнопки выхода: Ivory — чёткий антрацит, тёмные — приглушённый красный
  const logoutColor = theme === 'ivory' ? '#1A1A1B' : 'rgba(239, 68, 68, 0.65)'
  const logoutHoverColor = theme === 'ivory' ? '#8B6914' : '#ef4444'
  const logoutGlow = theme === 'ivory'
    ? 'rgba(139, 105, 20, 0.3)'
    : 'rgba(239, 68, 68, 0.4)'

  return (
    <motion.header
      className="relative z-40 flex items-center justify-between px-6 py-3"
      style={{
        background: 'var(--header-bg)',
        borderBottom: '1px solid var(--header-border)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
      }}
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Сканирующая линия по верху */}
      <div className="absolute top-0 left-0 right-0 h-px overflow-hidden">
        <motion.div
          className="h-full w-32"
          style={{
            background: 'linear-gradient(90deg, transparent, var(--accent, #d4a843), transparent)',
          }}
          animate={{ x: ['-128px', 'calc(100vw + 128px)'] }}
          transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
        />
      </div>

      {/* Левая часть: Логотип + Название + STATUS + THREAT LEVEL */}
      <div className="flex items-center gap-4">
        {/* Иконка щита */}
        <motion.div
          className="flex items-center justify-center w-9 h-9 rounded-lg"
          style={{
            background: 'linear-gradient(135deg, rgba(var(--accent-rgb, 212,168,67), 0.18) 0%, rgba(var(--accent-rgb, 212,168,67), 0.05) 100%)',
            border: '1px solid rgba(var(--accent-rgb, 212,168,67), 0.3)',
          }}
          whileHover={{ scale: 1.1, rotate: 5 }}
          whileTap={{ scale: 0.95 }}
        >
          <Shield
            size={18}
            style={{ color: 'var(--accent, #d4a843)' }}
          />
        </motion.div>

        {/* Название */}
        <div className="flex items-center gap-3 flex-wrap">
          <h1
            className="topbar-title topbar-item font-cinzel font-bold text-sm uppercase"
            style={{
              background: 'linear-gradient(135deg, var(--accent, #d4a843) 0%, color-mix(in srgb, var(--accent, #d4a843) 70%, #fff 30%) 50%, var(--accent, #d4a843) 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              letterSpacing: '0.15em',
            }}
          >
            S-GLOBAL DOMINION HQ
          </h1>

          {/* Разделитель — градиентный, 0.5px */}
          <div className="topbar-divider" />

          {/* STATUS: ONLINE */}
          <div className="flex items-center gap-2">
            <span
              className="topbar-item topbar-label text-xs font-orbitron"
            >
              STATUS:
            </span>
            <div className="flex items-center gap-1.5">
              {/* Пульсирующая зелёная точка */}
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
              </span>
              <span
                className="topbar-item text-xs font-orbitron font-bold"
                style={{ color: '#10b981', letterSpacing: '0.1em' }}
              >
                ONLINE
              </span>
            </div>
          </div>

          {/* Разделитель — градиентный, 0.5px */}
          <div className="topbar-divider hidden md:block" />

          {/* GLOBAL THREAT LEVEL: LOW */}
          <div className="hidden md:flex items-center gap-2">
            <span
              className="topbar-item topbar-label text-xs font-orbitron"
            >
              GLOBAL THREAT LEVEL:
            </span>
            <span
              className="topbar-item text-xs font-orbitron font-bold"
              style={{ color: '#10b981', letterSpacing: '0.1em' }}
            >
              LOW
            </span>
          </div>
        </div>
      </div>

      {/* Правая часть: ThemeSwitcher + Время + LogOut */}
      <div className="flex items-center gap-4">
        {/* Переключатель тем */}
        <ThemeSwitcher />

        {/* Дата и время — главный пульс Империи
            width: 120px + tabular-nums — часы не двигают соседние элементы */}
        <div
          className="hidden md:block text-right font-orbitron"
          style={{ width: '120px' }}
        >
          <div
            className="text-xs tracking-wider"
            style={{
              color: 'var(--header-label)',
              letterSpacing: '0.08em',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {formatDate(time)}
          </div>
          <div
            className="font-bold tracking-[0.2em]"
            style={{
              color: 'var(--header-time-color)',
              fontSize: 'var(--header-time-size, 13px)',
              textShadow: 'none',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {formatTime(time)}
          </div>
        </div>

        {/* Кнопка выхода — Суверенный Выход */}
        <LogoutButton
          color={logoutColor}
          hoverColor={logoutHoverColor}
          glowColor={logoutGlow}
          onLogout={handleLogout}
        />
      </div>
    </motion.header>
  )
}

/**
 * Кнопка выхода — отдельный компонент для чистоты
 */
function LogoutButton({ color, hoverColor, glowColor, onLogout }) {
  const [isHovered, setIsHovered] = useState(false)

  return (
    <motion.button
      onClick={onLogout}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title="Выход из системы"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '34px',
        height: '34px',
        borderRadius: '8px',
        background: isHovered ? `rgba(239, 68, 68, 0.08)` : 'transparent',
        border: isHovered
          ? `1px solid ${glowColor}`
          : '1px solid transparent',
        cursor: 'pointer',
        color: isHovered ? hoverColor : color,
        filter: isHovered ? `drop-shadow(0 0 6px ${glowColor})` : 'none',
        transition: 'color 0.2s ease, background 0.2s ease, border-color 0.2s ease, filter 0.2s ease',
      }}
      whileHover={{ scale: 1.1 }}
      whileTap={{ scale: 0.92 }}
    >
      <LogOut size={16} strokeWidth={2} />
    </motion.button>
  )
}
