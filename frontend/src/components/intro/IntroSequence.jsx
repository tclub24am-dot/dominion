import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

/**
 * S-GLOBAL DOMINION — Cinematic Intro Sequence v3.0
 * ==================================================
 * ЧИСТЫЙ, МОНУМЕНТАЛЬНЫЙ дизайн. Без глитча, без шума.
 * 
 * Тайминг (15 секунд строго):
 *   0-4s   → Логотип "S-GLOBAL DOMINION" — fade-in, золотое свечение, затухание
 *   4-8s   → Цитата: "Мы стоим на переднем краю, на вершине человеческой мысли!"
 *   8-12s  → "СУПЕРПОЗИЦИЯ!!!" — монументальный fade-in, вспышка, золотой градиент
 *   12-15s → "ПОБЕДА и ВЕЗЕНИЕ во ВСЕХ ДЕЛАХ!!!" — золотой градиент
 *   15s    → Автоматический переход на дашборд
 * 
 * VERSHINA v200.11 Protocol — СУПЕРПОЗИЦИЯ v53.0
 */
export default function IntroSequence({ onComplete }) {
  const [phase, setPhase] = useState(0) // 0=black, 1=title, 2=quote, 3=superposition, 4=victory, 5=exit
  const skipTimerRef = useRef(null)
  const completedRef = useRef(false)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    const timers = [
      setTimeout(() => setPhase(1), 200),     // 0.2s → показать заголовок
      setTimeout(() => setPhase(2), 4000),    // 4s   → цитата
      setTimeout(() => setPhase(3), 8000),    // 8s   → СУПЕРПОЗИЦИЯ
      setTimeout(() => setPhase(4), 12000),   // 12s  → победа
      setTimeout(() => setPhase(5), 14500),   // 14.5s → начать выход
      setTimeout(() => {                       // 15s  → завершить
        if (!completedRef.current) {
          completedRef.current = true
          onCompleteRef.current()
        }
      }, 15000),
    ]
    return () => {
      timers.forEach(clearTimeout)
      if (skipTimerRef.current) clearTimeout(skipTimerRef.current)
    }
  }, []) // пустой массив — таймеры запускаются один раз

  // Пропуск по кнопке SKIP
  const handleSkip = useCallback(() => {
    if (skipTimerRef.current || completedRef.current) return
    setPhase(5)
    skipTimerRef.current = setTimeout(() => {
      if (!completedRef.current) {
        completedRef.current = true
        onCompleteRef.current()
      }
    }, 600)
  }, [])

  return (
    <motion.div
      className="fixed inset-0 z-[9999] flex items-center justify-center select-none overflow-hidden"
      style={{ backgroundColor: '#000000' }}
      initial={{ opacity: 1 }}
      animate={{ opacity: phase === 5 ? 0 : 1 }}
      transition={{ duration: 0.8, ease: 'easeInOut' }}
    >
      {/* Минимальное звёздное поле */}
      <StarField />

      {/* Контент фаз */}
      <div className="relative z-10 text-center px-8 max-w-4xl mx-auto">

        {/* ФАЗА 1 (0-4s): S-GLOBAL DOMINION — логотип с золотым свечением */}
        <AnimatePresence>
          {phase >= 1 && phase < 2 && (
            <motion.div
              key="title"
              initial={{ opacity: 0, y: 30, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 1.05 }}
              transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
            >
              <TitleBlock />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ФАЗА 2 (4-8s): Цитата — серебристый неон, тонкий шрифт */}
        <AnimatePresence>
          {phase === 2 && (
            <motion.div
              key="quote"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 1.2, ease: 'easeOut' }}
            >
              <QuoteBlock />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ФАЗА 3 (8-12s): СУПЕРПОЗИЦИЯ!!! — монументальный fade-in с вспышкой */}
        <AnimatePresence>
          {phase === 3 && (
            <motion.div
              key="superposition"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.05 }}
              transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
            >
              <SuperpositionBlock />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ФАЗА 4 (12-15s): ПОБЕДА и ВЕЗЕНИЕ — золотой градиент */}
        <AnimatePresence>
          {phase === 4 && (
            <motion.div
              key="victory"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 1.0, ease: [0.16, 1, 0.3, 1] }}
            >
              <VictoryBlock />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Кнопка SKIP — внизу справа */}
      <motion.button
        className="absolute bottom-8 right-8 px-4 py-2 text-xs font-orbitron tracking-[0.2em] uppercase text-white/25 hover:text-white/50 transition-colors duration-300 border border-white/10 hover:border-white/20 rounded-lg backdrop-blur-sm"
        style={{ background: 'rgba(255,255,255,0.03)' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.5, duration: 1 }}
        onClick={handleSkip}
      >
        SKIP ▸
      </motion.button>

      {/* Прогресс-бар */}
      <ProgressBar phase={phase} />
    </motion.div>
  )
}

/* ============================================================
   SUB-COMPONENTS
   ============================================================ */

/**
 * ФАЗА 1: Логотип S-GLOBAL DOMINION
 * Мягкое золотое свечение (glow), появление из opacity 0 → 1
 */
function TitleBlock() {
  return (
    <div>
      {/* Верхняя декоративная линия */}
      <motion.div
        className="flex items-center justify-center gap-4 mb-6"
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 1.0, delay: 0.3 }}
      >
        <div className="h-px flex-1 max-w-32" style={{ background: 'linear-gradient(90deg, transparent, #d4a843)' }} />
        <span className="text-xs font-orbitron tracking-[0.4em] text-yellow-500/60 uppercase">
          S-GLOBAL EMPIRE
        </span>
        <div className="h-px flex-1 max-w-32" style={{ background: 'linear-gradient(90deg, #d4a843, transparent)' }} />
      </motion.div>

      {/* Главный заголовок — S-GLOBAL */}
      <motion.h1
        className="font-cinzel font-bold text-white leading-none"
        style={{
          fontSize: 'clamp(2.5rem, 8vw, 6rem)',
          textShadow: '0 0 40px rgba(212,168,67,0.6), 0 0 80px rgba(212,168,67,0.3), 0 0 120px rgba(212,168,67,0.1)',
          letterSpacing: '0.15em',
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 2.0, delay: 0.2 }}
      >
        S-GLOBAL
      </motion.h1>

      {/* DOMINION — золотой градиент */}
      <motion.h1
        className="font-cinzel font-bold leading-none"
        style={{
          fontSize: 'clamp(2rem, 6vw, 4.5rem)',
          background: 'linear-gradient(135deg, #d4a843 0%, #f0c060 50%, #d4a843 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
          letterSpacing: '0.3em',
          filter: 'drop-shadow(0 0 30px rgba(212,168,67,0.4))',
        }}
        initial={{ opacity: 0, letterSpacing: '0.6em' }}
        animate={{ opacity: 1, letterSpacing: '0.3em' }}
        transition={{ duration: 2.0, delay: 0.5 }}
      >
        DOMINION
      </motion.h1>

      {/* Подзаголовок */}
      <motion.p
        className="mt-6 text-sm font-orbitron tracking-[0.5em] uppercase"
        style={{ color: 'rgba(212,168,67,0.5)' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1, delay: 1.5 }}
      >
        VERSHINA v200.31 · EMPIRE PROTOCOL
      </motion.p>

      {/* Золотое свечение-ореол за логотипом */}
      <motion.div
        className="absolute inset-0 -inset-x-32 -inset-y-16 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at center, rgba(212,168,67,0.08) 0%, transparent 60%)',
        }}
        initial={{ opacity: 0, scale: 0.6 }}
        animate={{ opacity: [0, 1, 0.6], scale: [0.6, 1.2, 1] }}
        transition={{ duration: 3.5, ease: 'easeInOut' }}
      />
    </div>
  )
}

/**
 * ФАЗА 2: Цитата — серебристый неон, тонкий шрифт
 */
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
        className="font-montserrat font-light leading-relaxed"
        style={{
          fontSize: 'clamp(1.1rem, 3vw, 1.6rem)',
          color: 'rgba(200, 210, 230, 0.9)',
          textShadow: '0 0 20px rgba(200,210,230,0.15), 0 0 40px rgba(180,200,220,0.08)',
          letterSpacing: '0.02em',
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.8, delay: 0.3 }}
      >
        «Мы стоим на переднем краю,
        <br />
        <span
          style={{
            color: 'rgba(220, 230, 245, 1)',
            textShadow: '0 0 15px rgba(200,210,230,0.3)',
          }}
        >
          на вершине человеческой мысли!»
        </span>
      </motion.p>

      {/* Декоративная линия */}
      <motion.div
        className="mt-8 mx-auto h-px max-w-xs"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(200,210,230,0.3), transparent)' }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 1, delay: 1 }}
      />
    </div>
  )
}

/**
 * ФАЗА 3: СУПЕРПОЗИЦИЯ!!! — Монументальный, чистый блок.
 * Массивный шрифт Orbitron, эффект вспышки при появлении, золотой градиент.
 * БЕЗ глитча, БЕЗ шума.
 */
function SuperpositionBlock() {
  return (
    <div className="relative">
      {/* Вспышка при появлении — расширяющееся свечение */}
      <motion.div
        className="absolute inset-0 -inset-x-40 -inset-y-20 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at center, rgba(212,168,67,0.25) 0%, rgba(212,168,67,0.05) 40%, transparent 70%)',
        }}
        initial={{ opacity: 0, scale: 0.3 }}
        animate={{ opacity: [0, 1, 0.4], scale: [0.3, 1.5, 1] }}
        transition={{ duration: 2.0, ease: [0.16, 1, 0.3, 1] }}
      />

      {/* Главный текст — МОНУМЕНТАЛЬНЫЙ Orbitron */}
      <motion.span
        className="relative font-orbitron font-black tracking-tighter block"
        style={{
          fontSize: 'clamp(2.8rem, 10vw, 6rem)',
          background: 'linear-gradient(135deg, #d4a843 0%, #f0c060 40%, #d4a843 70%, #f0c060 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
          letterSpacing: '-0.02em',
          lineHeight: 1.05,
          filter: 'drop-shadow(0 0 50px rgba(212,168,67,0.6)) drop-shadow(0 0 100px rgba(212,168,67,0.2))',
        }}
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
      >
        СУПЕРПОЗИЦИЯ!!!
      </motion.span>

      {/* Подзаголовок */}
      <motion.p
        className="mt-6 text-sm font-orbitron tracking-[0.4em] uppercase"
        style={{ color: 'rgba(212,168,67,0.5)' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.8, duration: 1.0 }}
      >
        QUANTUM STATE ACTIVATED
      </motion.p>

      {/* Декоративные линии */}
      <motion.div
        className="mt-4 mx-auto h-px max-w-md"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(212,168,67,0.4), transparent)' }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 1, delay: 1.0 }}
      />
    </div>
  )
}

/**
 * ФАЗА 4: ПОБЕДА и ВЕЗЕНИЕ во ВСЕХ ДЕЛАХ!!! — золотой градиент
 */
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

      {/* Главный текст — золотой градиент */}
      <motion.h2
        className="font-cinzel font-bold"
        style={{
          fontSize: 'clamp(1.8rem, 5vw, 3.5rem)',
          background: 'linear-gradient(135deg, #d4a843 0%, #f0c060 50%, #d4a843 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
          letterSpacing: '0.05em',
          filter: 'drop-shadow(0 0 30px rgba(212,168,67,0.5))',
        }}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.0, ease: [0.16, 1, 0.3, 1] }}
      >
        ПОБЕДА и ВЕЗЕНИЕ
      </motion.h2>

      <motion.h2
        className="font-cinzel font-bold"
        style={{
          fontSize: 'clamp(1.5rem, 4vw, 2.8rem)',
          background: 'linear-gradient(135deg, #f0c060 0%, #d4a843 50%, #f0c060 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
          letterSpacing: '0.05em',
          filter: 'drop-shadow(0 0 20px rgba(212,168,67,0.4))',
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
    color: i % 2 === 0 ? '#d4a843' : '#f0c060',
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

/**
 * Звёздное поле — 50 звёзд, useMemo
 */
function StarField() {
  const stars = useMemo(() => Array.from({ length: 50 }, (_, i) => ({
    id: i,
    x: Math.random() * 100,
    y: Math.random() * 100,
    size: Math.random() * 1.5 + 0.5,
    opacity: Math.random() * 0.4 + 0.05,
    duration: Math.random() * 4 + 3,
  })), [])

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

/**
 * Прогресс-бар — внизу по центру
 */
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
