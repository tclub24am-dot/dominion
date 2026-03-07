/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // === DARK THEME: Gold/Neon ===
        dominion: {
          black:    '#080810',
          deep:     '#0d0d1a',
          card:     '#111128',
          border:   '#1e1e3f',
          gold:     '#d4a843',
          'gold-light': '#f0c060',
          neon:     '#00f5ff',
          'neon-green': '#00ff88',
          'neon-purple': '#a855f7',
          red:      '#ff3b3b',
          text:     '#e8e8f0',
          muted:    '#8888aa',
        },
      },
      fontFamily: {
        cinzel:    ['Cinzel', 'serif'],
        orbitron:  ['Orbitron', 'sans-serif'],
        montserrat: ['Montserrat', 'sans-serif'],
      },
      backgroundImage: {
        'gold-gradient': 'linear-gradient(135deg, #d4a843 0%, #f0c060 50%, #d4a843 100%)',
        'neon-gradient': 'linear-gradient(135deg, #00f5ff 0%, #a855f7 100%)',
        'dark-gradient': 'linear-gradient(180deg, #080810 0%, #0d0d1a 100%)',
        'card-gradient': 'linear-gradient(135deg, rgba(17,17,40,0.9) 0%, rgba(13,13,26,0.95) 100%)',
      },
      boxShadow: {
        'gold':       '0 0 20px rgba(212,168,67,0.4), 0 0 40px rgba(212,168,67,0.1)',
        'neon':       '0 0 20px rgba(0,245,255,0.4), 0 0 40px rgba(0,245,255,0.1)',
        'neon-green': '0 0 20px rgba(0,255,136,0.4)',
        'card':       '0 8px 32px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.05)',
        'card-hover': '0 16px 48px rgba(0,0,0,0.8), 0 0 30px rgba(212,168,67,0.2)',
      },
      animation: {
        'pulse-slow':   'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow':         'glow 2s ease-in-out infinite alternate',
        'float':        'float 6s ease-in-out infinite',
        'glitch':       'glitch 0.3s ease-in-out',
        'scan-line':    'scanLine 8s linear infinite',
      },
      keyframes: {
        glow: {
          '0%':   { textShadow: '0 0 10px #d4a843, 0 0 20px #d4a843' },
          '100%': { textShadow: '0 0 20px #f0c060, 0 0 40px #f0c060, 0 0 60px #d4a843' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':      { transform: 'translateY(-10px)' },
        },
        glitch: {
          '0%':   { transform: 'translate(0)', filter: 'none' },
          '20%':  { transform: 'translate(-3px, 2px)', filter: 'hue-rotate(90deg)' },
          '40%':  { transform: 'translate(3px, -2px)', filter: 'hue-rotate(180deg)' },
          '60%':  { transform: 'translate(-2px, 1px)', filter: 'hue-rotate(270deg)' },
          '80%':  { transform: 'translate(2px, -1px)', filter: 'none' },
          '100%': { transform: 'translate(0)', filter: 'none' },
        },
        scanLine: {
          '0%':   { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
}
