import { MentorPage } from '@/features/mentor/MentorPage'
import { createBrowserRouter } from 'react-router'
import { SystemStatusPage } from '@/features/system-status/SystemStatusPage'
import { ActivityAnalysisPage } from '@/features/github/ActivityAnalysisPage'
import { RepositoryAnalysisPage } from '@/features/github/RepositoryAnalysisPage'
import { ScopedRoleScoresPage } from '@/features/scoring/ScopedRoleScoresPage'
import { NotFoundPage } from './NotFoundPage'

export const router = createBrowserRouter([
  { path: '/', element: <SystemStatusPage /> },
  { path: '/repositories/:repositoryId/activity', element: <ActivityAnalysisPage /> },
  { path: '/activity', element: <ActivityAnalysisPage /> },
  { path: '/activity/:repositoryId', element: <ActivityAnalysisPage /> },
  { path: '/mentor', element: <MentorPage /> },
  { path: '/repositories/:repositoryId/analysis', element: <RepositoryAnalysisPage /> },
  { path: '/analysis', element: <RepositoryAnalysisPage /> },
  { path: '/analysis/:repositoryId', element: <RepositoryAnalysisPage /> },
  { path: '/role-scores', element: <ScopedRoleScoresPage /> },
  { path: '*', element: <NotFoundPage /> },
])
