import React, { useMemo } from 'react'
import { motion } from 'framer-motion'

/**
 * S-GLOBAL DOMINION — Particle Background
 * Фоновые частицы пыли / звёзд для атмосферы дашборда
 * Лёгкие, не нагружают GPU
 */
export default function ParticleBackground({ count = 40 }) {
  const particles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: Math.random() * 3 + 1,
      opacity: Math.random() * 0.3 + 0.05,
      duration: Math.random() * 20 + 15,
      delay: Math.random() * 10,
      drift: (Math.random() - 0.5) * 30,
    }))
  }, [count])

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
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
            boxShadow: `0 0 ${p.size * 2}px rgba(212, 168, 67, ${p.opacity * 0.5})`,
          }}
          animate={{
            y: [0, -40, 0],
            x: [0, p.drift, 0],
            opacity: [p.opacity, p.opacity * 0.3, p.opacity],
          }}
          transition={{
            duration: p.duration,
            repeat: Infinity,
            ease: 'easeInOut',
            delay: p.delay,
          }}
        />
      ))}

      {/* Тонкая сетка (grid overlay) */}
      <div
        className="absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage: `
            linear-gradient(rgba(212,168,67,0.3) 1px, transparent 1px),
            linear-gradient(90deg, rgba(212,168,67,0.3) 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px',
        }}
      />

      {/* Виньетка */}
      <div
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse at center, transparent 40%, rgba(8,8,16,0.6) 100%)',
        }}
      />
    </div>
  )
}
