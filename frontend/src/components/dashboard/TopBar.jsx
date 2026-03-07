import React, { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Shield } from 'lucide-react'

/**
 * S-GLOBAL DOMINION — Top Bar v2.0 (HQ Status Panel)
 * ====================================================
 * Верхняя панель: "S-GLOBAL DOMINION HQ | STATUS: ONLINE | GLOBAL THREAT LEVEL: LOW"
 * Pixel-Perfect по референсу.
 */
export default function TopBar() {
  const [time, setTime] = useState(new Date())

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

  return (
    <motion.header
      className="relative z-40 flex items-center justify-between px-6 py-3 border-b backdrop-blur-xl bg-dominion-deep/80 border-dominion-border"
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Сканирующая линия по верху */}
      <div className="absolute top-0 left-0 right-0 h-px overflow-hidden">
        <motion.div
          className="h-full w-32"
          style={{
            background: 'linear-gradient(90deg, transparent, #d4a843, transparent)',
          }}
          animate={{ x: ['-128px', 'calc(100vw + 128px)'] }}
          transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
        />
      </div>

      {/* Левая часть: Логотип + Название + STATUS + THREAT LEVEL */}
      <div className="flex items-center gap-4">
        {/* Иконка щита */}
        <motion.div
          className="flex items-center justify-center w-9 h-9 rounded-lg bg-gradient-to-br from-dominion-gold/20 to-dominion-gold/5 border border-dominion-gold/30"
          whileHover={{ scale: 1.1, rotate: 5 }}
          whileTap={{ scale: 0.95 }}
        >
          <Shield
            size={18}
            className="text-dominion-gold"
          />
        </motion.div>

        {/* Название */}
        <div className="flex items-center gap-3 flex-wrap">
          <h1
            className="font-cinzel font-bold text-sm tracking-[0.15em] uppercase"
            style={{
              background: 'linear-gradient(135deg, #d4a843 0%, #f0c060 50%, #d4a843 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            S-GLOBAL DOMINION HQ
          </h1>

          {/* Разделитель */}
          <div className="w-px h-5 bg-dominion-border" />

          {/* STATUS: ONLINE */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-orbitron tracking-wider text-dominion-muted">
              STATUS:
            </span>
            <div className="flex items-center gap-1.5">
              {/* Пульсирующая зелёная точка */}
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
              </span>
              <span className="text-xs font-orbitron font-bold tracking-wider text-emerald-400">
                ONLINE
              </span>
            </div>
          </div>

          {/* Разделитель */}
          <div className="hidden md:block w-px h-5 bg-dominion-border" />

          {/* GLOBAL THREAT LEVEL: LOW */}
          <div className="hidden md:flex items-center gap-2">
            <span className="text-xs font-orbitron tracking-wider text-dominion-muted">
              GLOBAL THREAT LEVEL:
            </span>
            <span className="text-xs font-orbitron font-bold tracking-wider text-emerald-400">
              LOW
            </span>
          </div>
        </div>
      </div>

      {/* Правая часть: Время */}
      <div className="flex items-center gap-4">
        {/* Дата и время */}
        <div className="hidden md:block text-right text-xs font-orbitron text-dominion-muted">
          <div className="tracking-wider">{formatDate(time)}</div>
          <div className="tracking-[0.2em] font-bold text-dominion-gold">
            {formatTime(time)}
          </div>
        </div>
      </div>
    </motion.header>
  )
}
