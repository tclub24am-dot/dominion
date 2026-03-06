import React, { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

/**
 * S-GLOBAL DOMINION — Cinematic Intro Sequence
 * =============================================
 * Тайминг (15 секунд):
 *   0-3s   → Fade-in "S-GLOBAL DOMINION" на чёрном фоне
 *   3-7s   → Цитата: "Мы стоим на переднем краю..."
 *   7-11s  → "СУПЕРПОЗИЦИЯ!!!" с глитч-эффектом
 *   11-15s → "ПОБЕДА и ВЕЗЕНИЕ во ВСЕХ ДЕЛАХ!!!"
 *   15s    → Переход на дашборд
 */
export default function IntroSequence({ onComplete }) {
  const [phase, setPhase] = useState(0) // 0=black, 1=title, 2=quote, 3=glitch, 4=victory, 5=exit
  const skipTimerRef = useRef(null)

  useEffect(() => {
    const timers = [
      setTimeout(() => setPhase(1), 300),    // 0.3s → показать заголовок
      setTimeout(() => setPhase(2), 3000),   // 3s   → цитата
      setTimeout(() => setPhase(3), 7000),   // 7s   → глитч
      setTimeout(() => setPhase(4), 11000),  // 11s  → победа
      setTimeout(() => setPhase(5), 14500),  // 14.5s → начать выход
      setTimeout(() => onComplete(), 15500), // 15.5s → завершить
    ]
    return () => {
      timers.forEach(clearTimeout)
      if (skipTimerRef.current) clearTimeout(skipTimerRef.current)
    }
  }, [onComplete])

  // Пропуск по клику (guard от двойного нажатия)
  const handleSkip = useCallback(() => {
    if (skipTimerRef.current) return
    setPhase(5)
    skipTimerRef.current = setTimeout(() => onComplete(), 600)
  }, [onComplete])

  return (
    <motion.div
      className="fixed inset-0 z-[9999] flex items-center justify-center cursor-pointer select-none overflow-hidden"
      style={{ backgroundColor: '#000000' }}
      onClick={handleSkip}
      initial={{ opacity: 1 }}
      animate={{ opacity: phase === 5 ? 0 : 1 }}
      transition={{ duration: 0.8, ease: 'easeInOut' }}
    >
      {/* Звёздный фон */}
      <StarField />

      {/* Сканирующая линия */}
      <ScanLine />

      {/* Контент фаз */}
      <div className="relative z-10 text-center px-8 max-w-4xl mx-auto">

        {/* ФАЗА 1: S-GLOBAL DOMINION */}
        <AnimatePresence>
          {phase >= 1 && phase < 2 && (
            <motion.div
              key="title"
              initial={{ opacity: 0, y: 30, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 1.05 }}
              transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
            >
              <TitleBlock />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ФАЗА 2: Цитата */}
        <AnimatePresence>
          {phase === 2 && (
            <motion.div
              key="quote"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 1.0, ease: 'easeOut' }}
            >
              <QuoteBlock />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ФАЗА 3: СУПЕРПОЗИЦИЯ (глитч) */}
        <AnimatePresence>
          {phase === 3 && (
            <motion.div
              key="glitch"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.1 }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
            >
              <GlitchBlock />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ФАЗА 4: ПОБЕДА */}
        <AnimatePresence>
          {phase === 4 && (
            <motion.div
              key="victory"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            >
              <VictoryBlock />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Кнопка пропуска */}
      <motion.div
        className="absolute bottom-8 right-8 text-xs text-white/30 font-montserrat tracking-widest uppercase"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 2, duration: 1 }}
      >
        нажмите для пропуска
      </motion.div>

      {/* Прогресс-бар */}
      <ProgressBar phase={phase} />
    </motion.div>
  )
}

/* ============================================================
   SUB-COMPONENTS
   ============================================================ */

function TitleBlock() {
  return (
    <div>
      {/* Верхняя линия */}
      <motion.div
        className="flex items-center justify-center gap-4 mb-6"
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.8, delay: 0.3 }}
      >
        <div className="h-px flex-1 max-w-32" style={{ background: 'linear-gradient(90deg, transparent, #d4a843)' }} />
        <span className="text-xs font-orbitron tracking-[0.4em] text-yellow-500/60 uppercase">
          S-GLOBAL EMPIRE
        </span>
        <div className="h-px flex-1 max-w-32" style={{ background: 'linear-gradient(90deg, #d4a843, transparent)' }} />
      </motion.div>

      {/* Главный заголовок */}
      <motion.h1
        className="font-cinzel font-bold text-white leading-none"
        style={{
          fontSize: 'clamp(2.5rem, 8vw, 6rem)',
          textShadow: '0 0 40px rgba(212,168,67,0.6), 0 0 80px rgba(212,168,67,0.2)',
          letterSpacing: '0.15em',
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.5, delay: 0.2 }}
      >
        S-GLOBAL
      </motion.h1>

      <motion.h1
        className="font-cinzel font-bold leading-none"
        style={{
          fontSize: 'clamp(2rem, 6vw, 4.5rem)',
          background: 'linear-gradient(135deg, #d4a843 0%, #f0c060 50%, #d4a843 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
          letterSpacing: '0.3em',
          textShadow: 'none',
        }}
        initial={{ opacity: 0, letterSpacing: '0.6em' }}
        animate={{ opacity: 1, letterSpacing: '0.3em' }}
        transition={{ duration: 1.5, delay: 0.5 }}
      >
        DOMINION
      </motion.h1>

      {/* Подзаголовок */}
      <motion.p
        className="mt-6 text-sm font-orbitron tracking-[0.5em] uppercase"
        style={{ color: 'rgba(212,168,67,0.5)' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1, delay: 1.2 }}
      >
        VERSHINA v200.11 · EMPIRE PROTOCOL
      </motion.p>
    </div>
  )
}

function QuoteBlock() {
  return (
    <div className="max-w-2xl mx-auto">
      <motion.div
        className="text-4xl mb-6"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 200, damping: 15 }}
      >
        ⚡
      </motion.div>

      <motion.p
        className="font-cinzel text-white/90 leading-relaxed"
        style={{
          fontSize: 'clamp(1.1rem, 3vw, 1.6rem)',
          textShadow: '0 0 20px rgba(255,255,255,0.1)',
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.5, delay: 0.3 }}
      >
        «Мы стоим на переднем краю,
        <br />
        <span style={{ color: '#d4a843' }}>на вершине человеческой мысли!</span>»
      </motion.p>

      {/* Декоративная линия */}
      <motion.div
        className="mt-8 mx-auto h-px max-w-xs"
        style={{ background: 'linear-gradient(90deg, transparent, #d4a843, transparent)' }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 1, delay: 1 }}
      />
    </div>
  )
}

function GlitchBlock() {
  const [glitchActive, setGlitchActive] = useState(false)

  useEffect(() => {
    // Запускаем глитч несколько раз
    const intervals = [
      setTimeout(() => setGlitchActive(true), 100),
      setTimeout(() => setGlitchActive(false), 400),
      setTimeout(() => setGlitchActive(true), 800),
      setTimeout(() => setGlitchActive(false), 1100),
      setTimeout(() => setGlitchActive(true), 1800),
      setTimeout(() => setGlitchActive(false), 2100),
      setTimeout(() => setGlitchActive(true), 2600),
      setTimeout(() => setGlitchActive(false), 2900),
      setTimeout(() => setGlitchActive(true), 3200),
      setTimeout(() => setGlitchActive(false), 3600),
    ]
    return () => intervals.forEach(clearTimeout)
  }, [])

  return (
    <div className="relative">
      <motion.div
        className="relative inline-block"
        animate={glitchActive ? {
          x: [0, -4, 4, -2, 2, 0],
          filter: [
            'none',
            'hue-rotate(90deg) saturate(2)',
            'hue-rotate(180deg) saturate(3)',
            'hue-rotate(270deg) saturate(2)',
            'none',
          ],
        } : {}}
        transition={{ duration: 0.15, ease: 'linear' }}
      >
        {/* Псевдо-слои для глитча */}
        {glitchActive && (
          <>
            <span
              className="absolute inset-0 font-orbitron font-black"
              style={{
                fontSize: 'clamp(2.5rem, 8vw, 5rem)',
                color: '#00f5ff',
                transform: 'translate(-4px, 2px)',
                clipPath: 'polygon(0 0, 100% 0, 100% 40%, 0 40%)',
                opacity: 0.8,
                letterSpacing: '0.1em',
              }}
            >
              СУПЕРПОЗИЦИЯ!!!
            </span>
            <span
              className="absolute inset-0 font-orbitron font-black"
              style={{
                fontSize: 'clamp(2.5rem, 8vw, 5rem)',
                color: '#ff3b3b',
                transform: 'translate(4px, -2px)',
                clipPath: 'polygon(0 60%, 100% 60%, 100% 100%, 0 100%)',
                opacity: 0.8,
                letterSpacing: '0.1em',
              }}
            >
              СУПЕРПОЗИЦИЯ!!!
            </span>
          </>
        )}

        <span
          className="relative font-orbitron font-black"
          style={{
            fontSize: 'clamp(2.5rem, 8vw, 5rem)',
            background: glitchActive
              ? 'linear-gradient(135deg, #00f5ff, #a855f7, #ff3b3b)'
              : 'linear-gradient(135deg, #d4a843, #f0c060)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            letterSpacing: '0.1em',
            display: 'block',
          }}
        >
          СУПЕРПОЗИЦИЯ!!!
        </span>
      </motion.div>

      <motion.p
        className="mt-6 text-sm font-orbitron tracking-[0.4em] uppercase"
        style={{ color: 'rgba(0,245,255,0.6)' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
      >
        QUANTUM STATE ACTIVATED
      </motion.p>
    </div>
  )
}

function VictoryBlock() {
  return (
    <div>
      {/* Иконки победы */}
      <motion.div
        className="flex justify-center gap-4 mb-6 text-3xl"
        initial={{ opacity: 0, scale: 0 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      >
        {'🏆 👑 ⚡'.split(' ').map((emoji, i) => (
          <motion.span
            key={i}
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: i * 0.15, type: 'spring' }}
          >
            {emoji}
          </motion.span>
        ))}
      </motion.div>

      <motion.h2
        className="font-cinzel font-bold text-white"
        style={{
          fontSize: 'clamp(1.8rem, 5vw, 3.5rem)',
          textShadow: '0 0 30px rgba(212,168,67,0.8), 0 0 60px rgba(212,168,67,0.3)',
          letterSpacing: '0.05em',
          animation: 'glow-pulse 1.5s ease-in-out infinite',
        }}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      >
        ПОБЕДА и ВЕЗЕНИЕ
      </motion.h2>

      <motion.h2
        className="font-cinzel font-bold"
        style={{
          fontSize: 'clamp(1.5rem, 4vw, 2.8rem)',
          background: 'linear-gradient(135deg, #d4a843 0%, #f0c060 50%, #d4a843 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
          letterSpacing: '0.05em',
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.3 }}
      >
        во ВСЕХ ДЕЛАХ!!!
      </motion.h2>

      {/* Частицы */}
      <ParticlesBurst />
    </div>
  )
}

function ParticlesBurst() {
  const particles = Array.from({ length: 12 }, (_, i) => ({
    id: i,
    angle: (i / 12) * 360,
    distance: 80 + Math.random() * 60,
    size: 4 + Math.random() * 4,
    color: i % 3 === 0 ? '#d4a843' : i % 3 === 1 ? '#00f5ff' : '#f0c060',
  }))

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {particles.map(p => (
        <motion.div
          key={p.id}
          className="absolute rounded-full"
          style={{
            width: p.size,
            height: p.size,
            backgroundColor: p.color,
            top: '50%',
            left: '50%',
            boxShadow: `0 0 ${p.size * 2}px ${p.color}`,
          }}
          initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
          animate={{
            x: Math.cos((p.angle * Math.PI) / 180) * p.distance,
            y: Math.sin((p.angle * Math.PI) / 180) * p.distance,
            opacity: 0,
            scale: 0,
          }}
          transition={{ duration: 1.5, ease: 'easeOut', delay: 0.2 }}
        />
      ))}
    </div>
  )
}

function StarField() {
  const stars = Array.from({ length: 80 }, (_, i) => ({
    id: i,
    x: Math.random() * 100,
    y: Math.random() * 100,
    size: Math.random() * 2 + 0.5,
    opacity: Math.random() * 0.6 + 0.1,
    duration: Math.random() * 3 + 2,
  }))

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {stars.map(star => (
        <motion.div
          key={star.id}
          className="absolute rounded-full bg-white"
          style={{
            left: `${star.x}%`,
            top: `${star.y}%`,
            width: star.size,
            height: star.size,
          }}
          animate={{ opacity: [star.opacity, star.opacity * 0.2, star.opacity] }}
          transition={{
            duration: star.duration,
            repeat: Infinity,
            ease: 'easeInOut',
            delay: Math.random() * 3,
          }}
        />
      ))}
    </div>
  )
}

function ScanLine() {
  return (
    <motion.div
      className="absolute left-0 right-0 h-px pointer-events-none z-20"
      style={{
        background: 'linear-gradient(90deg, transparent, rgba(0,245,255,0.4), transparent)',
        boxShadow: '0 0 10px rgba(0,245,255,0.3)',
      }}
      initial={{ top: '-2px' }}
      animate={{ top: '100vh' }}
      transition={{ duration: 6, repeat: Infinity, ease: 'linear', delay: 1 }}
    />
  )
}

function ProgressBar({ phase }) {
  const progress = Math.min((phase / 4) * 100, 100)

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 w-48">
      <div className="h-px bg-white/10 rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ background: 'linear-gradient(90deg, #d4a843, #f0c060)' }}
          initial={{ width: '0%' }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>
    </div>
  )
}
