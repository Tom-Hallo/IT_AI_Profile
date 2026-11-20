import type { ReactNode } from 'react'
import { AuthContext, useAuthSession } from '@/features/auth/useAuth'

export function AppProviders({ children }: { children: ReactNode }) {
  const session = useAuthSession()
  return <AuthContext.Provider value={session}>{children}</AuthContext.Provider>
}
