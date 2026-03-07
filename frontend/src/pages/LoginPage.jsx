import React, { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { Shield, Eye, EyeOff, LogIn } from 'lucide-react'
import api from '../api/client'

/**
 * S-GLOBAL DOMINION — Login Page
 * ================================
 * Минималистичная страница входа.
 * Glassmorphism-панель по центру, логотип Dominion,
 * фон: глубокий чёрный с эффектом золотой пыли.
 * 
 * AUTH: cookie-based (httpOnly) — токен НЕ хранится на клиенте.
 */

export default function LoginPage({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email.trim() || !password.trim()) {
      setError('Вход в Цитадель требует идентификации')
      return
    }
    setError('')
    setIsLoading(true)

    try {
      await api.post('/api/v1/auth/login', {
        username: email.trim(),
        password: password.trim(),
      })

      // Cookie установлен бэкендом (httpOnly) — сохраняем только флаг аутентификации
      sessionStorage.setItem('dominion_authenticated', '1')
      if (onLogin) onLogin({ email })
    } catch (err) {
      if (err.response && err.response.status === 401) {
        setError('Неверные учётные данные')
      } else if (err.response) {
        const detail = err.response.data?.detail
        setError(detail || 'Неверные учётные данные')
      } else {
        // Сеть недоступна или CORS-ошибка
        setError('Сервер Цитадели недоступен')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 flex items-center justify-center overflow-hidden"
      style={{ backgroundColor: '#050508' }}
    >
      {/* Золотая пыль — фоновые частицы */}
      <GoldDustBackground />

      {/* Тонкие лучи света */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div
          className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px]"
          style={{
            background: 'radial-gradient(ellipse at center, rgba(212,168,67,0.06) 0%, transparent 70%)',
          }}
        />
        <div
          className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px]"
          style={{
            background: 'radial-gradient(ellipse at center, rgba(212,168,67,0.03) 0%, transparent 70%)',
          }}
        />
      </div>

      {/* Glassmorphism-панель */}
      <motion.div
        className="relative z-10 w-full max-w-md mx-4"
        initial={{ opacity: 0, y: 40, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      >
        <div
          className="relative overflow-hidden rounded-2xl border border-white/[0.08] p-8 md:p-10"
          style={{
            background: 'rgba(12, 12, 24, 0.65)',
            backdropFilter: 'blur(40px)',
            WebkitBackdropFilter: 'blur(40px)',
            boxShadow: '0 32px 64px rgba(0,0,0,0.8), 0 0 80px rgba(212,168,67,0.05), inset 0 1px 0 rgba(255,255,255,0.05)',
          }}
        >
          {/* Верхняя декоративная линия */}
          <div className="absolute top-0 left-0 right-0 h-px"
            style={{ background: 'linear-gradient(90deg, transparent, rgba(212,168,67,0.4), transparent)' }}
          />

          {/* Логотип */}
          <motion.div
            className="flex flex-col items-center mb-8"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.6 }}
          >
            {/* Иконка щита */}
            <motion.div
              className="flex items-center justify-center w-16 h-16 rounded-2xl mb-5"
              style={{
                background: 'linear-gradient(135deg, rgba(212,168,67,0.15), rgba(212,168,67,0.03))',
                border: '1px solid rgba(212,168,67,0.25)',
                boxShadow: '0 0 40px rgba(212,168,67,0.1)',
              }}
              whileHover={{ scale: 1.05, rotate: 3 }}
            >
              <Shield size={28} style={{ color: '#d4a843' }} />
            </motion.div>

            {/* Название */}
            <h1
              className="font-cinzel font-bold text-2xl tracking-[0.15em] text-white mb-1"
              style={{
                textShadow: '0 0 30px rgba(212,168,67,0.3)',
              }}
            >
              S-GLOBAL
            </h1>
            <h2
              className="font-cinzel font-bold text-lg tracking-[0.3em]"
              style={{
                background: 'linear-gradient(135deg, #d4a843 0%, #f0c060 50%, #d4a843 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}
            >
              DOMINION
            </h2>

            {/* Подзаголовок */}
            <p className="mt-3 text-[10px] font-orbitron tracking-[0.4em] uppercase text-white/25">
              VERSHINA v200.11 · SECURE ACCESS
            </p>
          </motion.div>

          {/* Форма */}
          <motion.form
            onSubmit={handleSubmit}
            className="space-y-5"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5, duration: 0.6 }}
          >
            {/* Email */}
            <div>
              <label className="block text-[10px] font-orbitron tracking-[0.2em] uppercase text-white/40 mb-2">
                Email / Логин
              </label>
              <input
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="master@s-global.space"
                autoComplete="username"
                className="w-full px-4 py-3 rounded-xl text-sm font-montserrat text-white/90 placeholder:text-white/20 outline-none transition-all duration-300 border border-white/[0.08] focus:border-yellow-600/40 focus:ring-1 focus:ring-yellow-600/20"
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  backdropFilter: 'blur(10px)',
                }}
              />
            </div>

            {/* Пароль */}
            <div>
              <label className="block text-[10px] font-orbitron tracking-[0.2em] uppercase text-white/40 mb-2">
                Пароль
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className="w-full px-4 py-3 pr-12 rounded-xl text-sm font-montserrat text-white/90 placeholder:text-white/20 outline-none transition-all duration-300 border border-white/[0.08] focus:border-yellow-600/40 focus:ring-1 focus:ring-yellow-600/20"
                  style={{
                    background: 'rgba(255,255,255,0.03)',
                    backdropFilter: 'blur(10px)',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Ошибка */}
            {error && (
              <motion.p
                className="text-xs font-montserrat text-red-400 text-center"
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
              >
                {error}
              </motion.p>
            )}

            {/* Кнопка входа */}
            <motion.button
              type="submit"
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-orbitron font-bold text-sm tracking-[0.15em] uppercase transition-all duration-300 disabled:opacity-50"
              style={{
                background: isLoading
                  ? 'rgba(212,168,67,0.15)'
                  : 'linear-gradient(135deg, rgba(212,168,67,0.2), rgba(212,168,67,0.08))',
                border: '1px solid rgba(212,168,67,0.3)',
                color: '#d4a843',
                boxShadow: '0 0 30px rgba(212,168,67,0.08)',
              }}
              whileHover={{
                boxShadow: '0 0 40px rgba(212,168,67,0.2), 0 8px 32px rgba(0,0,0,0.4)',
                borderColor: 'rgba(212,168,67,0.5)',
              }}
              whileTap={{ scale: 0.98 }}
            >
              {isLoading ? (
                <motion.div
                  className="w-5 h-5 border-2 border-[#d4a843]/30 border-t-[#d4a843] rounded-full"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                />
              ) : (
                <>
                  <LogIn size={16} />
                  ВОЙТИ В СИСТЕМУ
                </>
              )}
            </motion.button>
          </motion.form>

          {/* Нижняя линия */}
          <div className="absolute bottom-0 left-0 right-0 h-px"
            style={{ background: 'linear-gradient(90deg, transparent, rgba(212,168,67,0.2), transparent)' }}
          />
        </div>

        {/* Подпись под панелью */}
        <motion.p
          className="text-center mt-6 text-[9px] font-orbitron tracking-[0.3em] uppercase text-white/15"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1, duration: 0.8 }}
        >
          S-GLOBAL DOMINION EMPIRE · ENCRYPTED CONNECTION
        </motion.p>
      </motion.div>
    </div>
  )
}

/**
 * Фоновые частицы золотой пыли
 */
function GoldDustBackground() {
  const particles = useMemo(() => {
    return Array.from({ length: 60 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: Math.random() * 2.5 + 0.5,
      opacity: Math.random() * 0.4 + 0.05,
      duration: Math.random() * 25 + 15,
      delay: Math.random() * 10,
      drift: (Math.random() - 0.5) * 40,
    }))
  }, [])

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {particles.map(p => (
        <motion.div
          key={p.id}
          className="absolute rounded-full"
          style={{
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.size,
            height: p.size,
            willChange: 'transform, opacity',
            backgroundColor: `rgba(212, 168, 67, ${p.opacity})`,
            boxShadow: `0 0 ${p.size * 3}px rgba(212, 168, 67, ${p.opacity * 0.6})`,
          }}
          animate={{
            y: [0, -60, 0],
            x: [0, p.drift, 0],
            opacity: [p.opacity, p.opacity * 0.2, p.opacity],
          }}
          transition={{
            duration: p.duration,
            repeat: Infinity,
            ease: 'easeInOut',
            delay: p.delay,
          }}
        />
      ))}

      {/* Виньетка */}
      <div
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse at center, transparent 30%, rgba(5,5,8,0.8) 100%)',
        }}
      />
    </div>
  )
}
