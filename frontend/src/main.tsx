import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from '@/app/App'
import { AppProviders } from '@/app/providers'
import '@/styles/global.css'
import '@/styles/tokens.css'
import '@/styles/base.css'
import '@/styles/components.css'
import '@/styles/layout.css'

const container = document.getElementById('root')
if (!container) {
  throw new Error('Không tìm thấy phần tử #root trong index.html')
}

createRoot(container).render(
  <StrictMode>
    <AppProviders>
      <App />
    </AppProviders>
  </StrictMode>,
)
