import React, { useState } from 'react'
import { Moon, Sun, Zap } from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'

/**
 * S-GLOBAL DOMINION — Theme Switcher v200.12.1
 * Переключатель тем: The Void / Ivory Luxe / Cyber-Cobalt
 * Hover-эффекты через React state — без прямой мутации DOM.
 */

const themes = [
  { id: 'void',   label: 'THE VOID',     Icon: Moon, glowColor: 'rgba(255, 215, 0, 0.6)',   title: 'The Void — тёмная тема' },
  { id: 'ivory',  label: 'IVORY LUXE',   Icon: Sun,  glowColor: 'rgba(139, 105, 20, 0.6)',  title: 'Ivory Luxe — светлая тема' },
  { id: 'cobalt', label: 'CYBER-COBALT', Icon: Zap,  glowColor: 'rgba(0, 240, 255, 0.6)',   title: 'Cyber-Cobalt — синяя тема' },
]

export default function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()
  const [hoveredId, setHoveredId] = useState(null)

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      marginLeft: '12px'
    }}>
      {themes.map((t) => {
        const isActive = theme === t.id
        const isHovered = hoveredId === t.id

        return (
          <button
            key={t.id}
            onClick={() => setTheme(t.id)}
            onMouseEnter={() => setHoveredId(t.id)}
            onMouseLeave={() => setHoveredId(null)}
            title={t.title}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '4px 6px',
              borderRadius: '6px',
              opacity: isActive ? 1 : isHovered ? 0.8 : 0.45,
              filter: isActive
                ? `drop-shadow(0 0 6px ${t.glowColor})`
                : isHovered
                  ? `drop-shadow(0 0 4px ${t.glowColor})`
                  : 'none',
              transform: isActive ? 'scale(1.15)' : 'scale(1)',
              transition: 'opacity 0.3s ease, filter 0.3s ease, transform 0.3s ease',
              lineHeight: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <t.Icon size={16} />
          </button>
        )
      })}
    </div>
  )
}
