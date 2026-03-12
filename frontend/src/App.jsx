import React, { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import LoginPage from './pages/LoginPage'
import IntroSequence from './components/intro/IntroSequence'
import Dashboard from './pages/Dashboard'
import api from './api/client'

/**
 * S-GLOBAL DOMINION — Root Application v3.2
 * VERSHINA v200.29.2 Protocol — ГЕРМЕТИЗАЦИЯ БЕЗОПАСНОСТИ
 * 
 * Строгий поток: Auth → Intro (15s) → Dashboard
 * Стадии: 'loading' | 'auth' | 'intro' | 'dashboard'
 * AUTH: cookie-based (httpOnly) — токен НЕ хранится на клиенте.
 */
export default function App() {
  const [stage, setStage] = useState('loading') // 'loading' | 'auth' | 'intro' | 'dashboard' | 'network_error'

  // Всегда применяем dark-тему
  useEffect(() => {
    document.documentElement.classList.add('dark')
  }, [])

  // Восстанавливаем сессию при перезагрузке — всегда проверяем httpOnly cookie через /auth/me
  // sessionStorage используется только для флага intro (не как условие для запроса)
  useEffect(() => {
    api.get('/api/v1/auth/me')
      .then(() => {
        // Cookie валиден — восстанавливаем сессию
        const introShown = sessionStorage.getItem('dominion_intro_shown')
        setStage(introShown ? 'dashboard' : 'intro')
      })
      .catch((error) => {
        const status = error?.response?.status
        if (status === 401 || status === 403) {
          // Токен истёк или невалиден — очищаем и на логин
          sessionStorage.clear()
          setStage('auth')
        } else {
          // Сетевая ошибка (500, таймаут, нет сети) — НЕ очищаем сессию,
          // показываем экран ошибки с кнопкой повтора
          setStage('network_error')
        }
      })
  }, [])

  const handleLogin = useCallback(() => {
    // Cookie уже установлен бэкендом при логине, флаг сохранён в LoginPage
    setStage('intro')
  }, [])

  const handleIntroComplete = useCallback(() => {
    sessionStorage.setItem('dominion_intro_shown', '1')
    setStage('dashboard')
  }, [])

  const handleLogout = useCallback(async () => {
    // Единая точка logout: убиваем httpOnly cookie на сервере, затем чистим клиент
    // Используем централизованный api-клиент (axios) — перехватчики ошибок работают корректно
    try {
      await api.post('/api/v1/auth/logout')
    } catch (err) {
      // Игнорируем сетевую ошибку — всё равно очищаем клиентскую сессию
      // В dev-режиме логируем для диагностики
      if (import.meta.env.DEV) {
        console.warn('[Logout] Server error (cookie may not be deleted):', err?.response?.status ?? err?.message)
      }
    }
    sessionStorage.clear()
    localStorage.clear()
    setStage('auth')
  }, [])

  // Стадия -1: Сетевая ошибка — сессия сохранена, предлагаем повтор
  if (stage === 'network_error') {
    return (
      <div className="fixed inset-0 flex flex-col items-center justify-center gap-4" style={{ backgroundColor: '#000000' }}>
        <div className="text-[#d4a843] font-orbitron text-sm tracking-widest">СВЯЗЬ С ЦИТАДЕЛЬЮ ПРЕРВАНА</div>
        <div className="text-white/40 text-xs">Сервер недоступен. Ваша сессия сохранена.</div>
        <button
          onClick={() => { setStage('loading'); window.location.reload() }}
          className="mt-2 px-6 py-2 rounded-lg border border-[#d4a843]/40 text-[#d4a843] text-xs font-orbitron tracking-wider hover:bg-[#d4a843]/10 transition-colors"
        >
          ПОВТОРИТЬ ПОДКЛЮЧЕНИЕ
        </button>
      </div>
    )
  }

  // Стадия 0: Проверка сессии — золотой спиннер на чёрном фоне
  if (stage === 'loading') {
    return (
      <div className="fixed inset-0 flex items-center justify-center" style={{ backgroundColor: '#000000' }}>
        <motion.div
          className="w-10 h-10 rounded-full border-2 border-[#d4a843]/20 border-t-[#d4a843]"
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
        />
      </div>
    )
  }

  // Стадия 1: Страница входа
  if (stage === 'auth') {
    return <LoginPage onLogin={handleLogin} />
  }

  // Стадия 2: Интро-последовательность (15 секунд)
  if (stage === 'intro') {
    return <IntroSequence onComplete={handleIntroComplete} />
  }

  // Стадия 3: Дашборд
  return (
    <Dashboard onLogout={handleLogout} />
  )
}
