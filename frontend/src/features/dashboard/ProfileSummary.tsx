import { Card } from '@/shared/ui/Card'
import type { AuthUser } from '@/features/auth/types'

interface Props {
  user: AuthUser
}

export function ProfileSummary({ user }: Props) {
  return (
    <Card className="profile-summary">
      <div className="profile-avatar" aria-hidden="true">
        {user.full_name
          ?.split(' ')
          .map((w) => w[0])
          .slice(0, 2)
          .join('')
          .toUpperCase() || 'U'}
      </div>
      <div className="profile-info">
        <h2>{user.full_name || 'Developer'}</h2>
        <p className="muted">{user.email}</p>
        <p className="profile-id">User ID: {user.id}</p>
      </div>
    </Card>
  )
}