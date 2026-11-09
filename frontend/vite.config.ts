import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// CÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¢ng cÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹nh trong container theo Technical Blueprint (mÃƒÂ¡Ã‚Â»Ã‚Â¥c 6).
// CÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¢ng trÃƒÆ’Ã‚Âªn mÃƒÆ’Ã‚Â¡y host do Compose ÃƒÆ’Ã‚Â¡nh xÃƒÂ¡Ã‚ÂºÃ‚Â¡ qua FRONTEND_PORT, khÃƒÆ’Ã‚Â´ng Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¢i ÃƒÂ¡Ã‚Â»Ã…Â¸ Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â¢y.
const FRONTEND_PORT = 5173

export default defineConfig(({ mode }) => {
  // ChÃƒÂ¡Ã‚Â»Ã¢â‚¬Â° dÃƒÆ’Ã‚Â¹ng phÃƒÆ’Ã‚Â­a Node (khÃƒÆ’Ã‚Â´ng lÃƒÂ¡Ã‚Â»Ã¢â€žÂ¢ ra trÃƒÆ’Ã‚Â¬nh duyÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡t vÃƒÆ’Ã‚Â¬ khÃƒÆ’Ã‚Â´ng cÃƒÆ’Ã‚Â³ tiÃƒÂ¡Ã‚Â»Ã‚Ân tÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ VITE_).
  // BiÃƒÂ¡Ã‚ÂºÃ‚Â¿n mÃƒÆ’Ã‚Â´i trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âng cÃƒÂ¡Ã‚Â»Ã‚Â§a tiÃƒÂ¡Ã‚ÂºÃ‚Â¿n trÃƒÆ’Ã‚Â¬nh (Compose) Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c Ãƒâ€ Ã‚Â°u tiÃƒÆ’Ã‚Âªn hÃƒâ€ Ã‚Â¡n file .env.
  const fileEnv = loadEnv(mode, process.cwd(), '')
  const read = (name: string): string | undefined => process.env[name] ?? fileEnv[name]

  const backendInternalUrl = read('BACKEND_INTERNAL_URL') ?? 'http://127.0.0.1:8000'
  const watchPolling = read('FRONTEND_WATCH_POLLING') === 'true'

  const proxy = {
    // MÃƒÂ¡Ã‚Â»Ã‚Âi lÃƒÂ¡Ã‚Â»Ã‚Âi gÃƒÂ¡Ã‚Â»Ã‚Âi /api/* Ãƒâ€žÃ¢â‚¬Ëœi cÃƒÆ’Ã‚Â¹ng origin rÃƒÂ¡Ã‚Â»Ã¢â‚¬Å“i Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c chuyÃƒÂ¡Ã‚Â»Ã†â€™n tiÃƒÂ¡Ã‚ÂºÃ‚Â¿p tÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºi Backend (Blueprint mÃƒÂ¡Ã‚Â»Ã‚Â¥c 4.4, D03).
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
      strictPort: true, // bÃƒÆ’Ã‚Â¡o lÃƒÂ¡Ã‚Â»Ã¢â‚¬â€i thay vÃƒÆ’Ã‚Â¬ tÃƒÂ¡Ã‚Â»Ã‚Â± Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¢i sang cÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¢ng khÃƒÆ’Ã‚Â¡c, Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã†â€™ khÃƒÆ’Ã‚Â´ng phÃƒÆ’Ã‚Â¡ hÃƒÂ¡Ã‚Â»Ã‚Â£p Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã¢â‚¬Å“ng port
      proxy,
      // BÃƒÂ¡Ã‚ÂºÃ‚Â­t khi hot-reload khÃƒÆ’Ã‚Â´ng hoÃƒÂ¡Ã‚ÂºÃ‚Â¡t Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã¢â€žÂ¢ng (bind mount tÃƒÂ¡Ã‚Â»Ã‚Â« ÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¢ Windows vÃƒÆ’Ã‚ o Docker).
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
    },
  }
})
