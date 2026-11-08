
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AppProviders } from '@/app/providers'
import { AuthPanel } from '@/features/auth/AuthPanel'
import '@/styles/global.css'

const container = document.getElementById('auth-root')

if (container) {
  createRoot(container).render(
    <StrictMode>
      <AppProviders>
        <AuthPanel />
      </AppProviders>
    </StrictMode>,
  )
}
