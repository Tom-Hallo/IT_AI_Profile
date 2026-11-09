import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Cổng cố định trong container theo Technical Blueprint (mục 6).
// Cổng trên máy host do Compose ánh xạ qua FRONTEND_PORT, không đổi ở đây.
const FRONTEND_PORT = 5173

export default defineConfig(({ mode }) => {
  // Chỉ dùng phía Node (không lộ ra trình duyệt vì không có tiền tố VITE_).
  // Biến môi trường của tiến trình (Compose) được ưu tiên hơn file .env.
  const fileEnv = loadEnv(mode, process.cwd(), '')
  const read = (name: string): string | undefined => process.env[name] ?? fileEnv[name]

  const backendInternalUrl = read('BACKEND_INTERNAL_URL') ?? 'http://127.0.0.1:8000'
  const watchPolling = read('FRONTEND_WATCH_POLLING') === 'true'

  const proxy = {
    // Mọi lời gọi /api/* đi cùng origin rồi được chuyển tiếp tới Backend (Blueprint mục 4.4, D03).
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
      strictPort: true, // báo lỗi thay vì tự đổi sang cổng khác, để không phá hợp đồng port
      proxy,
      // Bật khi hot-reload không hoạt động (bind mount từ ổ Windows vào Docker).
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
