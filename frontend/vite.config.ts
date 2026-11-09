import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

const FRONTEND_PORT = 5173

export default defineConfig(({ mode }) => {
  const fileEnv = loadEnv(mode, process.cwd(), '')
  const read = (name: string): string | undefined => process.env[name] ?? fileEnv[name]

  const backendInternalUrl = read('BACKEND_INTERNAL_URL') ?? 'http://127.0.0.1:8000'
  const watchPolling = read('FRONTEND_WATCH_POLLING') === 'true'

  const proxy = {
    '/api': { target: backendInternalUrl, changeOrigin: false },
  }

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, 'src') },
    },
    server: {
      host: true,
      port: FRONTEND_PORT,
      strictPort: true,
      proxy,
      allowedHosts: true,
      watch: watchPolling ? { usePolling: true, interval: 300 } : undefined,
    },
    build: {
      rollupOptions: {
        input: {
          main: path.resolve(import.meta.dirname, 'index.html'),
          designDemo: path.resolve(import.meta.dirname, 'design demo/index.html'),
        },
      },
    },
    preview: {
      host: true,
      port: FRONTEND_PORT,
      strictPort: true,
      proxy,
      allowedHosts: true,
    },
  }
})
