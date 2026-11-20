import { JobMatchingPage } from '@/features/jobs/JobMatchingPage'
import { CVStudioPage } from '@/features/cv-studio/CVStudioPage'
import { ResumeReferencesPage } from '@/features/resume-references/ResumeReferencesPage'
import { CVWorkspacePage } from '@/features/cvs/CVWorkspacePage'
import { AIAuditPage } from '@/features/ai-audit/AIAuditPage'
import { MentorPage } from '@/features/mentor/MentorPage'
import { createBrowserRouter } from 'react-router'
import { SystemStatusPage } from '@/features/system-status/SystemStatusPage'
import { ScopedRoleScoresPage } from '@/features/scoring/ScopedRoleScoresPage'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { PixelStudioLayout } from '@/features/pixel-studio/PixelStudioLayout'
import { PixelOverviewPage } from '@/features/pixel-studio/PixelOverviewPage'
import { PixelRepositoriesPage } from '@/features/pixel-studio/PixelRepositoriesPage'
import { PixelPrivacyPage } from '@/features/pixel-studio/PixelPrivacyPage'
import { ProfileSharingPage, PublicProfilePage } from '@/features/profile-sharing/ProfileSharingPage'
import { ATSReviewPage } from '@/features/cvs/ATSReviewPage'
import CareerRoadmap from '@/components/CareerRoadmap'
import { NotFoundPage } from './NotFoundPage'

const loadActivity = () => import('@/features/github/ActivityAnalysisPage')
  .then(module => ({ Component: module.ActivityAnalysisPage }))
const loadAnalysis = () => import('@/features/github/RepositoryAnalysisPage')
  .then(module => ({ Component: module.RepositoryAnalysisPage }))

export const router = createBrowserRouter([
  { path: '/share/:token', element: <PublicProfilePage /> },
  {
    element: <PixelStudioLayout />,
    hydrateFallbackElement: <p role="status">Đang mở trang…</p>,
    children: [
      { path: '/', element: <PixelOverviewPage /> },
      { path: '/repositories', element: <PixelRepositoriesPage /> },
      { path: '/privacy', element: <PixelPrivacyPage /> },
      { path: '/profile-sharing', element: <ProfileSharingPage /> },
      { path: '/ats-review', element: <ATSReviewPage /> },
      { path: '/roadmap', element: <CareerRoadmap /> },
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/role-scores', element: <ScopedRoleScoresPage /> },
      { path: '/repositories/:repositoryId/activity', lazy: loadActivity },
      { path: '/activity', lazy: loadActivity },
      { path: '/activity/:repositoryId', lazy: loadActivity },
      { path: '/job-matching', element: <JobMatchingPage /> },
      { path: '/cvs', element: <CVWorkspacePage /> },
      { path: '/cvs/references', element: <ResumeReferencesPage /> },
      { path: '/cv-studio', element: <CVStudioPage /> },
      { path: '/mentor', element: <MentorPage /> },
      { path: '/ai-audit', element: <AIAuditPage /> },
      { path: '/repositories/:repositoryId/analysis', lazy: loadAnalysis },
      { path: '/analysis', lazy: loadAnalysis },
      { path: '/analysis/:repositoryId', lazy: loadAnalysis },
      { path: '/system-status', element: <SystemStatusPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
