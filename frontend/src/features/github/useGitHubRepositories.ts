import { useCallback, useEffect, useRef, useState } from 'react'
import { isAbortError } from '@/shared/api/client'
import {
  disconnectGitHub,
  fetchRepositories,
  fetchSyncStatus,
  triggerSync as apiTriggerSync,
} from './api'
import type {
  RepositoryListResponse,
  RepositoryQueryParams,
  SyncStatusResponse,
} from './types'

export function useGitHubRepositories(isAuthenticated: boolean) {
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const [repoData, setRepoData] = useState<RepositoryListResponse | null>(null)
  const [reposLoading, setReposLoading] = useState(false)
  const [reposError, setReposError] = useState<string | null>(null)

  const [page, setPage] = useState(1)
  const [perPage] = useState(10)
  const [visibility, setVisibility] = useState<'all' | 'public' | 'private'>('all')
  const [searchQuery, setSearchQuery] = useState('')

  const [isSyncTriggering, setIsSyncTriggering] = useState(false)
  const [isDisconnecting, setIsDisconnecting] = useState(false)
  const [actionNotice, setActionNotice] = useState<{
    type: 'success' | 'error' | 'info'
    message: string
  } | null>(null)

  const pollIntervalRef = useRef<number | null>(null)

  // Tải trạng thái đồng bộ thủ công
  const loadSyncStatus = useCallback(async () => {
    if (!isAuthenticated) return
    setStatusLoading(true)
    setStatusError(null)
    try {
      const data = await fetchSyncStatus()
      setSyncStatus(data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Không thể tải trạng thái đồng bộ'
      setStatusError(msg)
    } finally {
      setStatusLoading(false)
    }
  }, [isAuthenticated])

  // Tải danh sách repositories thủ công
  const loadRepositories = useCallback(
    async (params?: Partial<RepositoryQueryParams>) => {
      if (!isAuthenticated) return
      setReposLoading(true)
      setReposError(null)
      try {
        const queryParams: RepositoryQueryParams = {
          page: params?.page ?? page,
          per_page: params?.per_page ?? perPage,
          visibility: params?.visibility ?? visibility,
          search: params?.search !== undefined ? params.search : searchQuery,
        }
        const data = await fetchRepositories(queryParams)
        setRepoData(data)
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Không thể tải danh sách repository'
        setReposError(msg)
      } finally {
        setReposLoading(false)
      }
    },
    [isAuthenticated, page, perPage, visibility, searchQuery],
  )

  // Khởi tạo và đồng bộ dữ liệu khi authentication hoặc query thay đổi
  useEffect(() => {
    if (!isAuthenticated) {
      return
    }

    let cancelled = false
    const controller = new AbortController()

    fetchSyncStatus(controller.signal)
      .then((data) => {
        if (!cancelled) setSyncStatus(data)
      })
      .catch((err: unknown) => {
        if (!cancelled && !isAbortError(err)) {
          const msg = err instanceof Error ? err.message : 'Không thể tải trạng thái đồng bộ'
          setStatusError(msg)
        }
      })

    fetchRepositories(
      { page, per_page: perPage, visibility, search: searchQuery },
      controller.signal,
    )
      .then((data) => {
        if (!cancelled) setRepoData(data)
      })
      .catch((err: unknown) => {
        if (!cancelled && !isAbortError(err)) {
          const msg = err instanceof Error ? err.message : 'Không thể tải danh sách repository'
          setReposError(msg)
        }
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [isAuthenticated, page, perPage, visibility, searchQuery])

  // Polling khi trạng thái đồng bộ đang chạy ("running")
  useEffect(() => {
    if (syncStatus?.status === 'running') {
      pollIntervalRef.current = window.setInterval(async () => {
        try {
          const updated = await fetchSyncStatus()
          setSyncStatus(updated)
          if (updated.status !== 'running') {
            if (pollIntervalRef.current !== null) {
              clearInterval(pollIntervalRef.current)
              pollIntervalRef.current = null
            }
            // Đồng bộ xong, cập nhật lại danh sách repository
            void loadRepositories()
            if (updated.status === 'completed') {
              setActionNotice({
                type: 'success',
                message: `Đồng bộ hoàn tất! Tìm thấy ${updated.total_repositories} repository.`,
              })
            } else if (updated.status === 'failed') {
              setActionNotice({
                type: 'error',
                message: `Đồng bộ thất bại: ${updated.error_message ?? 'Đã xảy ra lỗi'}`,
              })
            }
          }
        } catch {
          // Bỏ qua lỗi polling tạm thời
        }
      }, 2500)
    }

    return () => {
      if (pollIntervalRef.current !== null) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [syncStatus?.status, loadRepositories])

  // Kích hoạt đồng bộ
  const handleTriggerSync = async (background = true) => {
    setIsSyncTriggering(true)
    setActionNotice(null)
    try {
      const resp = await apiTriggerSync(background)
      setActionNotice({
        type: 'info',
        message: resp.message || 'Đã gửi yêu cầu đồng bộ repositories.',
      })
      await loadSyncStatus()
      if (!background) {
        await loadRepositories()
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Không thể kích hoạt đồng bộ'
      setActionNotice({ type: 'error', message: msg })
    } finally {
      setIsSyncTriggering(false)
    }
  }

  // Hủy kết nối GitHub
  const handleDisconnect = async () => {
    if (!window.confirm('Bạn có chắc chắn muốn hủy liên kết GitHub? Token đã lưu sẽ bị xóa.')) {
      return
    }
    setIsDisconnecting(true)
    setActionNotice(null)
    try {
      const res = await disconnectGitHub()
      setActionNotice({ type: 'success', message: res.message })
      setSyncStatus((prev) => (prev ? { ...prev, is_connected: false, status: 'idle' } : null))
      setRepoData(null)
      await loadSyncStatus()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Không thể hủy liên kết GitHub'
      setActionNotice({ type: 'error', message: msg })
    } finally {
      setIsDisconnecting(false)
    }
  }

  // Thay đổi bộ lọc visibility
  const handleVisibilityChange = (newVisibility: 'all' | 'public' | 'private') => {
    setVisibility(newVisibility)
    setPage(1)
    void loadRepositories({ visibility: newVisibility, page: 1 })
  }

  // Tìm kiếm repository
  const handleSearchChange = (query: string) => {
    setSearchQuery(query)
    setPage(1)
    void loadRepositories({ search: query, page: 1 })
  }

  // Chuyển trang
  const handlePageChange = (newPage: number) => {
    setPage(newPage)
    void loadRepositories({ page: newPage })
  }

  return {
    syncStatus,
    statusLoading,
    statusError,
    repositories: repoData?.items ?? [],
    pagination: repoData
      ? {
          total: repoData.total,
          page: repoData.page,
          perPage: repoData.per_page,
          totalPages: repoData.total_pages,
        }
      : null,
    reposLoading,
    reposError,
    visibility,
    searchQuery,
    page,
    isSyncTriggering,
    isDisconnecting,
    actionNotice,
    triggerSync: handleTriggerSync,
    disconnect: handleDisconnect,
    changeVisibility: handleVisibilityChange,
    changeSearch: handleSearchChange,
    changePage: handlePageChange,
    refresh: () => {
      void loadSyncStatus()
      void loadRepositories()
    },
  }
}
