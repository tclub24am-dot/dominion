import React, { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import LoginPage from './pages/LoginPage'
import IntroSequence from './components/intro/IntroSequence'
import Dashboard from './pages/Dashboard'
import api from './api/client'

/**
 * S-GLOBAL DOMINION — Root Application v3.1
 * VERSHINA v200.11 Protocol — ГЕРМЕТИЗАЦИЯ БЕЗОПАСНОСТИ
 * 
 * Строгий поток: Auth → Intro (15s) → Dashboard
 * Стадии: 'loading' | 'auth' | 'intro' | 'dashboard'
 * AUTH: cookie-based (httpOnly) — токен НЕ хранится на клиенте.
 */
export default function App() {
  const [stage, setStage] = useState('loading') // 'loading' | 'auth' | 'intro' | 'dashboard'
  const [theme, setTheme] = useState('dark') // 'dark' | 'ivory'

  // Восстанавливаем сессию при перезагрузке — проверяем httpOnly cookie через /auth/me
  useEffect(() => {
    const authenticated = sessionStorage.getItem('dominion_authenticated')
    const introShown = sessionStorage.getItem('dominion_intro_shown')

    if (!authenticated) {
      // Нет флага — сразу на логин, без запроса к серверу
      setStage('auth')
      return
    }

    // Флаг есть — проверяем валидность cookie через бэкенд
    api.get('/api/v1/auth/me')
      .then(() => {
        // Cookie валиден — восстанавливаем сессию
        if (introShown) {
          setStage('dashboard')
        } else {
          setStage('intro')
        }
      })
      .catch(() => {
        // Cookie невалиден или истёк — очищаем и на логин
        sessionStorage.clear()
        setStage('auth')
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

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'ivory' : 'dark')
  }

  // Применяем тему к html элементу
  useEffect(() => {
    const html = document.documentElement
    if (theme === 'dark') {
      html.classList.add('dark')
      html.classList.remove('theme-ivory')
    } else {
      html.classList.remove('dark')
      html.classList.add('theme-ivory')
    }
  }, [theme])

  // Стадия 0: Проверка сессии — золотой спиннер на чёрном фоне
  if (stage === 'loading') {
    return (
      <div className="fixed inset-0 flex items-center justify-center" style={{ backgroundColor: '#050508' }}>
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
    <Dashboard theme={theme} onToggleTheme={toggleTheme} />
  )
}
