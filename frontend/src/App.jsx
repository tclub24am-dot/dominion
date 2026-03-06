import React, { useState, useEffect, useCallback } from 'react'
import IntroSequence from './components/intro/IntroSequence'
import Dashboard from './pages/Dashboard'

/**
 * S-GLOBAL DOMINION — Root Application
 * VERSHINA v200.11 Protocol
 * 
 * Поток: Intro (15s) → Dashboard
 * Темы: Dark (золото/неон) | Ivory (слоновая кость)
 */
export default function App() {
  const [introComplete, setIntroComplete] = useState(false)
  const [theme, setTheme] = useState('dark') // 'dark' | 'ivory'

  // Проверяем, был ли интро уже показан в этой сессии
  useEffect(() => {
    const shown = sessionStorage.getItem('dominion_intro_shown')
    if (shown) setIntroComplete(true)
  }, [])

  const handleIntroComplete = useCallback(() => {
    sessionStorage.setItem('dominion_intro_shown', '1')
    setIntroComplete(true)
  }, [])

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'ivory' : 'dark')
  }

  // Применяем тему к html элементу (стили body управляются через CSS-классы)
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

  // Показываем интро при первом входе
  if (!introComplete) {
    return <IntroSequence onComplete={handleIntroComplete} />
  }

  return (
    <Dashboard theme={theme} onToggleTheme={toggleTheme} />
  )
}
