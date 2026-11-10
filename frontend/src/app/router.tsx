import { createBrowserRouter } from 'react-router'
import { SystemStatusPage } from '@/features/system-status/SystemStatusPage'
import { ActivityAnalysisPage } from '@/features/github/ActivityAnalysisPage'
import { RepositoryAnalysisPage } from '@/features/github/RepositoryAnalysisPage'
import { NotFoundPage } from './NotFoundPage'

export const router = createBrowserRouter([
  { path: '/', element: <SystemStatusPage /> },
  { path: '/repositories/:repositoryId/activity', element: <ActivityAnalysisPage /> },
  { path: '/activity', element: <ActivityAnalysisPage /> },
  { path: '/activity/:repositoryId', element: <ActivityAnalysisPage /> },
  { path: '/repositories/:repositoryId/analysis', element: <RepositoryAnalysisPage /> },
  { path: '/analysis', element: <RepositoryAnalysisPage /> },
  { path: '/analysis/:repositoryId', element: <RepositoryAnalysisPage /> },
  { path: '*', element: <NotFoundPage /> },
])
