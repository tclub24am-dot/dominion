import React, { useState } from 'react'
import { Moon, Sun, Zap } from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'

/**
 * S-GLOBAL DOMINION — Theme Switcher v200.17
 * Переключатель тем: The Void / Ivory Luxe / Cyber-Cobalt
 * VERSHINA v200.17 — Ivory: strokeWidth=2.5, глубокий чёрный #1A1A1B, opacity:1
 */

const themes = [
  {
    id: 'void',
    label: 'THE VOID',
    Icon: Moon,
    glowColor: 'rgba(255, 215, 0, 0.7)',
    iconColor: { default: 'rgba(255,215,0,0.55)', active: '#FFD700', hover: '#FFD700' },
    title: 'The Void — тёмная тема',
  },
  {
    id: 'ivory',
    label: 'IVORY LUXE',
    Icon: Sun,
    glowColor: 'rgba(139, 105, 20, 0.7)',
    iconColor: { default: '#1A1A1B', active: '#8B6914', hover: '#d4a843' },
    title: 'Ivory Luxe — светлая тема',
  },
  {
    id: 'cobalt',
    label: 'CYBER-COBALT',
    Icon: Zap,
    glowColor: 'rgba(0, 240, 255, 0.7)',
    iconColor: { default: 'rgba(0,240,255,0.55)', active: '#00F0FF', hover: '#00F0FF' },
    title: 'Cyber-Cobalt — синяя тема',
  },
]

export default function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()
  const [hoveredId, setHoveredId] = useState(null)

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      marginLeft: '12px',
    }}>
      {themes.map((t) => {
        const isActive = theme === t.id
        const isHovered = hoveredId === t.id

        // Цвет иконки: в Ivory — всегда тёмный и видимый
        const iconColor = isActive
          ? t.iconColor.active
          : isHovered
            ? t.iconColor.hover
            : t.iconColor.default

        // Opacity: в Ivory — всегда 1 для всех иконок (видимость на светлом фоне)
        const opacity = theme === 'ivory'
          ? 1
          : isActive ? 1 : isHovered ? 0.85 : 0.45

        return (
          <button
            key={t.id}
            onClick={() => setTheme(t.id)}
            onMouseEnter={() => setHoveredId(t.id)}
            onMouseLeave={() => setHoveredId(null)}
            title={t.title}
            style={{
              background: isHovered || isActive
                ? `rgba(${t.id === 'void' ? '255,215,0' : t.id === 'ivory' ? '139,105,20' : '0,240,255'}, 0.08)`
                : 'none',
              border: isActive
                ? `1px solid rgba(${t.id === 'void' ? '255,215,0' : t.id === 'ivory' ? '139,105,20' : '0,240,255'}, 0.3)`
                : '1px solid transparent',
              cursor: 'pointer',
              padding: '5px 7px',
              borderRadius: '8px',
              opacity,
              color: iconColor,
              filter: isActive
                ? `drop-shadow(0 0 6px ${t.glowColor})`
                : isHovered
                  ? `drop-shadow(0 0 5px ${t.glowColor})`
                  : 'none',
              transform: isActive ? 'scale(1.18)' : isHovered ? 'scale(1.1)' : 'scale(1)',
              transition: 'opacity 0.25s ease, filter 0.25s ease, transform 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275), background 0.2s ease, border-color 0.2s ease, color 0.2s ease',
              lineHeight: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {/* Ivory Luxe: strokeWidth=2.5 — иконки чёткие как буквы на бумаге */}
            <t.Icon
              size={16}
              color={iconColor}
              strokeWidth={theme === 'ivory' ? 2.5 : 2}
            />
          </button>
        )
      })}
    </div>
  )
}
