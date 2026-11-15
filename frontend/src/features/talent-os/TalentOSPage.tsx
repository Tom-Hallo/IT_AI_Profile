import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { TalentOSLayout } from './TalentOSLayout'

/** The production dashboard renders actual backend data in the V9 workspace. */
export function TalentOSPage() {
  return <TalentOSLayout title="Dashboard"><DashboardPage /></TalentOSLayout>
}
