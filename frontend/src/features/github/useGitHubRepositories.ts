import { useEffect, useState } from 'react'
import { isAbortError } from '@/shared/api/client'
import {
  disconnectGitHub,
  fetchRepositories,
  fetchSyncStatus,
  triggerSync as apiTriggerSync,
} from './api'
import type {
  RepositoryListResponse,
  RepositoryVisibility,
  SyncStatusResponse,
  SyncTriggerResponse,
} from './types'

function completedMessage(result: SyncTriggerResponse | SyncStatusResponse) {
  const labels = { public: ' công khai', private: ' riêng tư', all: '' }
  if (result.synced_count == null || !result.synced_visibility) {
    return 'Đồng bộ GitHub hoàn tất.'
  }
  const label = labels[result.synced_visibility]
  return result.synced_count === 0
    ? `Đồng bộ hoàn tất. Không tìm thấy repository${label}.`
    : `Đồng bộ hoàn tất. Đã đồng bộ ${result.synced_count} repository${label}.`
}

export function useGitHubRepositories(isAuthenticated: boolean) {
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [statusRevision, setStatusRevision] = useState(0)
  const [listRevision, setListRevision] = useState(0)
  const [listResult, setListResult] = useState<{
    key: string
    data?: RepositoryListResponse
    error?: string
  } | null>(null)

  const [page, setPage] = useState(1)
  const [visibility, setVisibility] = useState<RepositoryVisibility>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const search = searchQuery.trim()

  const [isSyncTriggering, setIsSyncTriggering] = useState(false)
  const [isDisconnecting, setIsDisconnecting] = useState(false)
  const [actionNotice, setActionNotice] = useState<{
    type: 'success' | 'error' | 'info'
    message: string
  } | null>(null)

  const privateBlocked = visibility === 'private' && !syncStatus?.has_private_scope
  const canLoadList = isAuthenticated && syncStatus?.is_connected && !privateBlocked
  const listKey = JSON.stringify([visibility, page, search, listRevision])
  const currentList = canLoadList && listResult?.key === listKey ? listResult : null
  const repoData = currentList?.data
  const running = syncStatus?.status === 'running'

  useEffect(() => {
    if (!isAuthenticated) return
    const controller = new AbortController()
    fetchSyncStatus(controller.signal).then((data) => {
      if (controller.signal.aborted) return
      setSyncStatus(data)
      setStatusError(null)
    }).catch((err: unknown) => {
      if (controller.signal.aborted || isAbortError(err)) return
      setStatusError(err instanceof Error ? err.message : 'Không thể tải trạng thái đồng bộ')
    })
    return () => controller.abort()
  }, [isAuthenticated, statusRevision])

  useEffect(() => {
    if (!canLoadList) return
    const controller = new AbortController()
    const load = () => {
      fetchRepositories({ page, per_page: 10, visibility, search }, controller.signal)
        .then((data) => {
          if (!controller.signal.aborted) setListResult({ key: listKey, data })
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || isAbortError(err)) return
          const error = err instanceof Error ? err.message : 'Không thể tải danh sách repository'
          setListResult({ key: listKey, error })
        })
    }
    const timer = window.setTimeout(load, search ? 250 : 0)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [canLoadList, listKey, page, search, visibility])

  useEffect(() => {
    if (!isAuthenticated || !running) return
    const controller = new AbortController()
    let timer: number
    let consecutiveErrors = 0
    const poll = async () => {
      try {
        const updated = await fetchSyncStatus(controller.signal)
        if (controller.signal.aborted) return
        consecutiveErrors = 0
        setStatusError(null)
        setSyncStatus(updated)
        if (updated.status !== 'running') {
          setListRevision((n) => n + 1)
          if (updated.status === 'completed') {
            setActionNotice({ type: 'success', message: completedMessage(updated) })
          }
          return
        }
      } catch {
        if (controller.signal.aborted) return
        consecutiveErrors += 1
        if (consecutiveErrors >= 5) {
          setStatusError('Đang mất kết nối khi theo dõi đồng bộ. Hệ thống sẽ tự kiểm tra lại.')
        }
      }
      timer = window.setTimeout(poll, consecutiveErrors >= 5 ? 10000 : 2500)
    }
    timer = window.setTimeout(poll, 1000)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [isAuthenticated, running])

  const handleTriggerSync = async (background: boolean) => {
    if (!syncStatus?.is_connected || privateBlocked || running || isSyncTriggering || isDisconnecting) return
    setIsSyncTriggering(true)
    setActionNotice(null)
    try {
      const resp = await apiTriggerSync(background, visibility)
      setSyncStatus((previous) => previous && {
        ...previous,
        status: resp.status === 'completed' ? 'completed' : 'running',
        last_synced_at: resp.last_synced_at ?? previous.last_synced_at,
        error_message: null,
      })
      if (resp.status === 'completed') {
        setActionNotice({ type: 'success', message: completedMessage(resp) })
        setListRevision((n) => n + 1)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Không thể kích hoạt đồng bộ'
      setActionNotice({ type: 'error', message })
      setStatusRevision((n) => n + 1)
    } finally {
      setIsSyncTriggering(false)
    }
  }

  const handleDisconnect = async () => {
    if (!window.confirm('Bạn có chắc chắn muốn hủy liên kết GitHub? Token đã lưu sẽ bị xóa.')) return
    setIsDisconnecting(true)
    setActionNotice(null)
    try {
      const res = await disconnectGitHub()
      setActionNotice({ type: 'success', message: res.message })
      setSyncStatus((prev) => prev && { ...prev, is_connected: false, status: 'idle' })
      setListResult(null)
      setPage(1)
      setVisibility('all')
      setSearchQuery('')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Không thể hủy liên kết GitHub'
      setActionNotice({ type: 'error', message })
    } finally {
      setIsDisconnecting(false)
    }
  }

  return {
    syncStatus,
    statusLoading: !syncStatus && !statusError,
    statusError,
    repositories: repoData?.items ?? [],
    pagination: repoData
      ? {
          total: repoData.total,
          page: repoData.page,
          totalPages: repoData.total_pages,
        }
      : null,
    reposLoading: Boolean(canLoadList && !currentList),
    reposError: currentList?.error,
    privateBlocked,
    visibility,
    searchQuery,
    page,
    isSyncTriggering,
    isDisconnecting,
    actionNotice,
    dismissNotice: () => setActionNotice(null),
    triggerSync: handleTriggerSync,
    disconnect: handleDisconnect,
    changeVisibility: (next: RepositoryVisibility) => {
      setVisibility(next)
      setPage(1)
      setActionNotice(null)
    },
    changeSearch: (query: string) => {
      setSearchQuery(query)
      setPage(1)
    },
    changePage: setPage,
    retryList: () => setListRevision((n) => n + 1),
    retryStatus: () => setStatusRevision((n) => n + 1),
  }
}
