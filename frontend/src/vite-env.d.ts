/// <reference types="vite/client" />

// Chỉ khai báo biến có tiền tố VITE_ (các biến này bị lộ ra trình duyệt).
// Tuyệt đối không đặt secret ở đây.
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
