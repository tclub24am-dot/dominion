import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Загружаем .env.local / .env для чтения VITE_API_TARGET в конфиге
  const env = loadEnv(mode, process.cwd(), '')

  const apiTarget = env.VITE_API_TARGET || 'http://localhost:8001'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
      sourcemap: false,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom'],
            motion: ['framer-motion'],
            icons: ['lucide-react'],
          },
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          // Управляется через VITE_API_TARGET в frontend/.env.local
          // Локальный Docker: http://localhost:8001
          // Продакшн Цитадели: http://89.169.39.111:8001
          target: apiTarget,
          changeOrigin: true,
          secure: false,
        },
      },
    },
  }
})
