import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MessageCircle } from 'lucide-react'

/**
 * S-GLOBAL DOMINION — 3D Messenger Bubble
 * Объёмная иконка мессенджера в левом нижнем углу
 * drop-shadow + rotate при наведении
 */
export default function MessengerBubble({ theme = 'dark' }) {
  const [isHovered, setIsHovered] = useState(false)
  const [unread] = useState(3) // Заглушка для непрочитанных
  const isDark = theme === 'dark'

  return (
    <motion.div
      className="fixed bottom-6 left-6 z-[55]"
      initial={{ scale: 0, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ delay: 0.8, type: 'spring', stiffness: 200, damping: 15 }}
    >
      {/* Пульсирующий фон */}
      <motion.div
        className="absolute inset-0 rounded-2xl"
        style={{
          background: isDark
            ? 'linear-gradient(135deg, #8b5cf6, #a855f7)'
            : 'linear-gradient(135deg, #7c3aed, #8b5cf6)',
        }}
        animate={{
          scale: isHovered ? [1, 1.2, 1] : [1, 1.08, 1],
          opacity: isHovered ? [0.4, 0.1, 0.4] : [0.3, 0.1, 0.3],
        }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Кнопка */}
      <motion.button
        className={`
          relative flex items-center justify-center w-14 h-14 rounded-2xl
          transition-colors duration-300
          ${isDark
            ? 'bg-gradient-to-br from-violet-600 to-purple-700 border border-violet-400/30'
            : 'bg-gradient-to-br from-violet-500 to-purple-600 border border-violet-300/40'
          }
        `}
        style={{
          boxShadow: isHovered
            ? '0 8px 30px rgba(139,92,246,0.5), 0 0 20px rgba(139,92,246,0.3)'
            : '0 4px 20px rgba(139,92,246,0.3), 0 0 10px rgba(139,92,246,0.15)',
          perspective: '600px',
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        whileHover={{
          scale: 1.1,
          rotateY: 15,
          rotateX: -10,
        }}
        whileTap={{ scale: 0.9 }}
        transition={{ type: 'spring', stiffness: 400, damping: 15 }}
      >
        <MessageCircle
          size={24}
          className="text-white"
          style={{
            filter: isHovered
              ? 'drop-shadow(0 0 8px rgba(255,255,255,0.6))'
              : 'drop-shadow(0 2px 4px rgba(0,0,0,0.3))',
          }}
        />

        {/* Бейдж непрочитанных */}
        {unread > 0 && (
          <motion.div
            className="absolute -top-1 -right-1 flex items-center justify-center w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold"
            style={{
              boxShadow: '0 0 8px rgba(239,68,68,0.6)',
            }}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 1.2, type: 'spring', stiffness: 500 }}
          >
            {unread}
          </motion.div>
        )}

        {/* 3D блик */}
        <div
          className="absolute inset-0 rounded-2xl pointer-events-none"
          style={{
            background: 'linear-gradient(135deg, rgba(255,255,255,0.2) 0%, transparent 50%)',
          }}
        />
      </motion.button>

      {/* Подпись при ховере */}
      <AnimatePresence>
        {isHovered && (
          <motion.div
            className={`
              absolute left-full ml-3 top-1/2 -translate-y-1/2
              px-3 py-1.5 rounded-lg whitespace-nowrap
              text-xs font-orbitron tracking-wider
              ${isDark
                ? 'bg-dominion-deep/90 border border-dominion-border text-dominion-gold'
                : 'bg-ivory-card/90 border border-ivory-border text-ivory-gold'
              }
            `}
            style={{ backdropFilter: 'blur(12px)' }}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.2 }}
          >
            IMPERIAL MESSENGER
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
