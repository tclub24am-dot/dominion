import React, { createContext, useContext, useState, useEffect } from 'react'

const ThemeContext = createContext()

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('dominion_theme') || 'void')

  useEffect(() => {
    const body = document.body
    body.classList.remove('theme-ivory', 'theme-cobalt')
    if (theme === 'ivory') body.classList.add('theme-ivory')
    if (theme === 'cobalt') body.classList.add('theme-cobalt')
    localStorage.setItem('dominion_theme', theme)
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within <ThemeProvider>')
  return ctx
}
