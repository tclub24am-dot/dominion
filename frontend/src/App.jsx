import React, { useState, useEffect } from 'react'
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

  const handleIntroComplete = () => {
    sessionStorage.setItem('dominion_intro_shown', '1')
    setIntroComplete(true)
  }

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'ivory' : 'dark')
  }

  // Применяем тему к html элементу
  useEffect(() => {
    const html = document.documentElement
    if (theme === 'dark') {
      html.classList.add('dark')
      html.classList.remove('theme-ivory')
      document.body.style.backgroundColor = '#080810'
      document.body.style.color = '#e8e8f0'
    } else {
      html.classList.remove('dark')
      html.classList.add('theme-ivory')
      document.body.style.backgroundColor = '#f5f0e8'
      document.body.style.color = '#1a1a2e'
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
