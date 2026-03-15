import React, { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import LoginPage from './pages/LoginPage'
import IntroSequence from './components/intro/IntroSequence'
import Dashboard from './pages/Dashboard'
import ModulePage from './pages/ModulePage'
import LogisticsPage from './pages/LogisticsPage'
import CallArchivePage from './pages/CallArchivePage'
import DominionWidget from './components/miks/DominionWidget'
import BottomDrawer from './components/dashboard/BottomDrawer'
import api from './api/client'

/**
 * S-GLOBAL DOMINION — Root Application v3.3
 * VERSHINA v200.31 Protocol — ЖИВЫЕ МАРШРУТЫ
 *
 * Строгий поток: Auth → Intro (15s) → Dashboard
 * Стадии: 'loading' | 'auth' | 'intro' | 'dashboard'
 * AUTH: cookie-based (httpOnly) — токен НЕ хранится на клиенте.
 * ROUTING: react-router-dom v6 — 12 секторов с маршрутами
 */

function AppCore() {
  const [stage, setStage] = useState('loading') // 'loading' | 'auth' | 'intro' | 'dashboard' | 'network_error'

  // Всегда применяем dark-тему
  useEffect(() => {
    document.documentElement.classList.add('dark')
  }, [])

  // Восстанавливаем сессию при перезагрузке — всегда проверяем httpOnly cookie через /auth/me
  useEffect(() => {
    api.get('/api/v1/auth/me')
      .then(() => {
        const introShown = sessionStorage.getItem('dominion_intro_shown')
        setStage(introShown ? 'dashboard' : 'intro')
      })
      .catch((error) => {
        const status = error?.response?.status
        if (status === 401 || status === 403) {
          sessionStorage.clear()
          setStage('auth')
        } else {
          setStage('network_error')
        }
      })
  }, [])

  const handleLogin = useCallback(() => {
    setStage('intro')
  }, [])

  const handleIntroComplete = useCallback(() => {
    sessionStorage.setItem('dominion_intro_shown', '1')
    setStage('dashboard')
  }, [])

  const handleLogout = useCallback(async () => {
    try {
      await api.post('/api/v1/auth/logout')
    } catch (err) {
      if (import.meta.env.DEV) {
        console.warn('[Logout] Server error:', err?.response?.status ?? err?.message)
      }
    }
    sessionStorage.clear()
    localStorage.clear()
    setStage('auth')
  }, [])

  // Стадия -1: Сетевая ошибка
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

  // Стадия 0: Проверка сессии
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

  // Стадия 2: Интро-последовательность
  if (stage === 'intro') {
    return <IntroSequence onComplete={handleIntroComplete} />
  }

  // Стадия 3: Дашборд + маршруты модулей
  // DominionWidget и BottomDrawer — ГЛОБАЛЬНЫЙ МАКЕТ (присутствуют на всех страницах)
  return (
    <>
      <Routes>
        {/* Главный дашборд */}
        <Route path="/" element={<Dashboard onLogout={handleLogout} />} />

        {/* 12 секторов империи */}
        <Route path="/fleet"       element={<ModulePage code="FL" title="ТАКСОПАРК T-CLUB24"              apiPath="/api/v1/fleet/vehicles"         onLogout={handleLogout} />} />
        <Route path="/logistics"   element={<LogisticsPage onLogout={handleLogout} />} />
        <Route path="/consulting"  element={<ModulePage code="IT" title="КОНСАЛТИНГ И IT"                 apiPath="/api/v1/consulting/clients"     onLogout={handleLogout} />} />
        <Route path="/warehouse"   element={<ModulePage code="WH" title="АВТОСЕРВИС И СТРАХОВАНИЕ"        apiPath="/api/v1/warehouse/items"        onLogout={handleLogout} />} />
        <Route path="/ai-analyst"  element={<ModulePage code="AI" title="AI АНАЛИТИК"                     apiPath="/api/v1/analytics/overlay"      onLogout={handleLogout} />} />
        <Route path="/finance"     element={<ModulePage code="FN" title="ФИНАНСЫ И БУХГАЛТЕРИЯ"           apiPath="/api/v1/kazna/summary"          onLogout={handleLogout} />} />
        <Route path="/gps"         element={<ModulePage code="GP" title="GPS МОНИТОРИНГ"                  apiPath="/api/v1/gps/live"               onLogout={handleLogout} />} />
        <Route path="/tasks"       element={<ModulePage code="TS" title="AI ОТЧЁТЫ И ЗАДАЧИ"              apiPath="/api/v1/tasks/list"             onLogout={handleLogout} />} />
        <Route path="/merit"       element={<ModulePage code="MR" title="ГАРНИЗОН ПОЧЁТА"                 apiPath="/api/v1/merit/leaderboard"      onLogout={handleLogout} />} />
        <Route path="/investments" element={<ModulePage code="IV" title="ИНВЕСТИЦИИ И БЛАГОТВОРИТЕЛЬНОСТЬ" apiPath="/api/v1/investments/portfolio"  onLogout={handleLogout} />} />
        <Route path="/partners"    element={<ModulePage code="FP" title="ПАРТНЁРЫ И ВЫПЛАТЫ"              apiPath="/api/v1/partner/list"           onLogout={handleLogout} />} />
        <Route path="/academy"     element={<ModulePage code="AC" title="S-GLOBAL ACADEMY & LEGAL"        apiPath="/api/v1/academy/courses"        onLogout={handleLogout} />} />

        {/* Архив звонков */}
        <Route path="/calls" element={<CallArchivePage onLogout={handleLogout} />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      {/* ── ГЛОБАЛЬНЫЕ КОМПОНЕНТЫ (присутствуют на всех страницах) ── */}
      <DominionWidget />
      <BottomDrawer />
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppCore />
    </BrowserRouter>
  )
}
