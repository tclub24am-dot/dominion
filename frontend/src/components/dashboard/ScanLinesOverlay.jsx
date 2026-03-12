import React from 'react'
import { motion } from 'framer-motion'

/**
 * S-GLOBAL DOMINION — Scan Lines Overlay v1.0
 * =============================================
 * Эффект "кабины пилота" — сканирующие горизонтальные линии
 * и лёгкий цифровой шум поверх всего фона.
 * Создаёт атмосферу высокотехнологичного командного центра.
 * VERSHINA v200.11 Protocol — Level 5++
 */

export default function ScanLinesOverlay() {
  return (
    <>
      {/* Горизонтальные сканирующие линии — CSS repeating-linear-gradient */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          zIndex: 20,
          background: `repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(212, 168, 67, 0.012) 2px,
            rgba(212, 168, 67, 0.012) 4px
          )`,
          mixBlendMode: 'overlay',
        }}
      />

      {/* Движущаяся сканирующая полоса — как в кабине пилота */}
      <motion.div
        className="fixed left-0 right-0 pointer-events-none"
        style={{
          zIndex: 20,
          height: '120px',
          background: `linear-gradient(
            180deg,
            transparent 0%,
            rgba(212, 168, 67, 0.02) 20%,
            rgba(212, 168, 67, 0.04) 50%,
            rgba(212, 168, 67, 0.02) 80%,
            transparent 100%
          )`,
          mixBlendMode: 'screen',
        }}
        animate={{
          top: ['-120px', '100vh'],
        }}
        transition={{
          duration: 8,
          repeat: Infinity,
          ease: 'linear',
        }}
      />

      {/* Лёгкая виньетка по краям — фокус на центр */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          zIndex: 20,
          background: `radial-gradient(
            ellipse at center,
            transparent 50%,
            rgba(0, 0, 0, 0.3) 100%
          )`,
        }}
      />

      {/* Тонкий цифровой шум — статичная SVG-текстура (рендерится 1 раз, тайлится через CSS) */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          zIndex: 20,
          opacity: 0.03,
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'repeat',
          backgroundSize: '200px 200px',
        }}
      />
    </>
  )
}
