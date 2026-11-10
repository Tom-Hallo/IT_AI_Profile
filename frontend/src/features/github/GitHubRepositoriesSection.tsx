import { useState } from 'react'
import { Link } from 'react-router'
import { env } from '@/shared/config/env'
import { Button } from '@/shared/ui/Button'
import type { Repository } from './types'
import { useGitHubRepositories } from './useGitHubRepositories'
import './GitHubRepositoriesSection.css'

interface Props {
  isAuthenticated: boolean
}

// GitHub language colors mapping
const LANGUAGE_COLORS: Record<string, string> = {
  TypeScript: '#3178c6',
  JavaScript: '#f1e05a',
  Python: '#3572A5',
  Rust: '#dea584',
  Go: '#00ADD8',
  HTML: '#e34c26',
  CSS: '#563d7c',
  Java: '#b07219',
  'C++': '#f34b7d',
  C: '#555555',
  'C#': '#178600',
  Ruby: '#701516',
  PHP: '#4F5D95',
  Shell: '#89e051',
  Dockerfile: '#384d54',
}

function getLanguageColor(lang: string): string {
  return LANGUAGE_COLORS[lang] ?? '#8b949e'
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'N/A'
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('vi-VN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

export function GitHubRepositoriesSection({ isAuthenticated }: Props) {
  const {
    syncStatus,
    statusLoading,
    repositories,
    pagination,
    reposLoading,
    visibility,
    searchQuery,
    page,
    isSyncTriggering,
    isDisconnecting,
    actionNotice,
    triggerSync,
    disconnect,
    changeVisibility,
    changeSearch,
    changePage,
  } = useGitHubRepositories(isAuthenticated)

  const [useBackgroundSync, setUseBackgroundSync] = useState(true)

  if (!isAuthenticated) {
    return null
  }

  const isConnected = syncStatus?.is_connected ?? false
  const isSyncing = syncStatus?.status === 'running' || isSyncTriggering

  const handleConnect = (includePrivate: boolean) => {
    if (!env.apiBaseUrl) return
    const url = `${env.apiBaseUrl}/auth/github?include_private=${includePrivate}`
    window.location.assign(url)
  }

  return (
    <section className="github-section" aria-labelledby="github-heading">
      {/* Header */}
      <div className="github-header">
        <div className="github-header-info">
          <h2 id="github-heading">Đồng bộ GitHub Repositories</h2>
          <p>
            Đồng bộ metadata và ngôn ngữ từ GitHub API thực tế để phục vụ phân tích kỹ năng và hồ sơ.
          </p>

          <div className="github-badges">
            {isConnected ? (
              <>
                <span className="badge-pill badge-pill--public">✓ Đã kết nối GitHub</span>
                {syncStatus?.has_private_scope ? (
                  <span className="badge-pill badge-pill--private">Quyền: Public + Private</span>
                ) : (
                  <span className="badge-pill badge-pill--branch">Quyền: Chỉ Public</span>
                )}
                {syncStatus?.last_synced_at && (
                  <span className="badge-pill badge-pill--fork">
                    Lần cuối: {formatDate(syncStatus.last_synced_at)}
                  </span>
                )}
              </>
            ) : (
              <span className="badge-pill badge-pill--archived">Chưa kết nối GitHub</span>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="github-actions">
          {isConnected ? (
            <>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                <input
                  type="checkbox"
                  checked={useBackgroundSync}
                  onChange={(e) => setUseBackgroundSync(e.target.checked)}
                  disabled={isSyncing}
                />
                Chạy nền (RQ Worker)
              </label>

              <Button
                variant="primary"
                onClick={() => void triggerSync(useBackgroundSync)}
                disabled={isSyncing || statusLoading}
              >
                {isSyncing ? 'Đang đồng bộ...' : 'Đồng bộ ngay'}
              </Button>

              {!syncStatus?.has_private_scope && (
                <Button
                  variant="default"
                  onClick={() => handleConnect(true)}
                  title="Kết nối lại và cấp quyền đồng bộ các repository riêng tư"
                >
                  Cấp quyền Private
                </Button>
              )}

              <Button
                variant="ghost"
                onClick={() => void disconnect()}
                disabled={isDisconnecting || isSyncing}
                style={{ color: 'var(--color-danger)' }}
              >
                {isDisconnecting ? 'Đang hủy...' : 'Hủy liên kết'}
              </Button>
            </>
          ) : (
            <div style={{ display: 'flex', gap: 8 }}>
              <Button
                variant="primary"
                onClick={() => handleConnect(false)}
                disabled={!env.apiBaseUrl}
              >
                Liên kết GitHub (Public)
              </Button>
              <Button
                variant="default"
                onClick={() => handleConnect(true)}
                disabled={!env.apiBaseUrl}
                title="Yêu cầu scope 'repo' để đồng bộ cả private repository"
              >
                Liên kết GitHub (+Private)
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Notices & Alerts */}
      {actionNotice && (
        <div className={`github-notice github-notice--${actionNotice.type}`} role="status">
          <span>{actionNotice.message}</span>
          <button
            type="button"
            onClick={() => {}}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
            aria-label="Đóng"
          >
            ✕
          </button>
        </div>
      )}

      {isSyncing && (
        <div className="github-notice github-notice--running" role="status">
          <div>
            <strong>Đang đồng bộ repositories từ GitHub API...</strong>
            <div style={{ fontSize: '0.8rem', marginTop: 4 }}>
              Hệ thống đang tự động duyệt qua các trang (pagination), lưu trữ ngôn ngữ chi tiết và xử lý rate limit an toàn.
            </div>
          </div>
        </div>
      )}

      {syncStatus?.status === 'failed' && (
        <div className="github-notice github-notice--error" role="alert">
          <div>
            <strong>Đồng bộ thất bại:</strong> {syncStatus.error_message ?? 'Đã xảy ra lỗi khi gọi GitHub API.'}
          </div>
          <Button variant="danger" onClick={() => void triggerSync(useBackgroundSync)}>
            Thử lại
          </Button>
        </div>
      )}

      {/* Search and Filters */}
      {isConnected && (
        <div className="github-controls">
          <div className="github-search">
            <input
              type="search"
              placeholder="Tìm kiếm repository theo tên..."
              value={searchQuery}
              onChange={(e) => changeSearch(e.target.value)}
              aria-label="Tìm kiếm repository"
            />
          </div>

          <div className="github-filters">
            <button
              type="button"
              className={`filter-tab ${visibility === 'all' ? 'filter-tab--active' : ''}`}
              onClick={() => changeVisibility('all')}
            >
              Tất cả {pagination?.total !== undefined ? `(${pagination.total})` : ''}
            </button>
            <button
              type="button"
              className={`filter-tab ${visibility === 'public' ? 'filter-tab--active' : ''}`}
              onClick={() => changeVisibility('public')}
            >
              Công khai (Public)
            </button>
            <button
              type="button"
              className={`filter-tab ${visibility === 'private' ? 'filter-tab--active' : ''}`}
              onClick={() => changeVisibility('private')}
            >
              Riêng tư (Private)
            </button>
          </div>
        </div>
      )}

      {/* Repositories List */}
      {isConnected && (
        <>
          {reposLoading && repositories.length === 0 ? (
            <div className="github-empty">
              <p>Đang tải danh sách repositories...</p>
            </div>
          ) : repositories.length === 0 ? (
            <div className="github-empty">
              <p>
                {searchQuery
                  ? `Không tìm thấy repository nào phù hợp với từ khóa "${searchQuery}".`
                  : 'Chưa có repository nào được đồng bộ.'}
              </p>
              {!searchQuery && (
                <Button
                  variant="primary"
                  onClick={() => void triggerSync(useBackgroundSync)}
                  disabled={isSyncing}
                >
                  Bắt đầu đồng bộ ngay
                </Button>
              )}
            </div>
          ) : (
            <div className="repo-grid">
              {repositories.map((repo) => (
                <RepositoryCard key={repo.id} repo={repo} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {pagination && pagination.totalPages > 1 && (
            <div className="github-pagination">
              <Button
                variant="default"
                disabled={page <= 1 || reposLoading}
                onClick={() => changePage(page - 1)}
              >
                ← Trang trước
              </Button>
              <span>
                Trang {pagination.page} / {pagination.totalPages} ({pagination.total} repositories)
              </span>
              <Button
                variant="default"
                disabled={page >= pagination.totalPages || reposLoading}
                onClick={() => changePage(page + 1)}
              >
                Trang sau →
              </Button>
            </div>
          )}
        </>
      )}

      {!isConnected && (
        <div className="github-empty">
          <p>
            Kết nối tài khoản GitHub của bạn để đồng bộ các dự án, ngôn ngữ lập trình và lịch sử phát triển.
          </p>
          <Button variant="primary" onClick={() => handleConnect(false)}>
            Kết nối GitHub ngay
          </Button>
        </div>
      )}
    </section>
  )
}

function RepositoryCard({ repo }: { repo: Repository }) {
  const languageEntries = Object.entries(repo.languages ?? {})
  const totalLanguageBytes = languageEntries.reduce((acc, [, bytes]) => acc + bytes, 0)

  return (
    <article className="repo-card" aria-labelledby={`repo-${repo.id}`}>
      <div className="repo-card-header">
        <h3 className="repo-card-title" id={`repo-${repo.id}`}>
          <a href={repo.html_url} target="_blank" rel="noopener noreferrer">
            {repo.name}
          </a>
        </h3>

        <div className="repo-card-badges">
          {repo.private ? (
            <span className="badge-pill badge-pill--private">Private</span>
          ) : (
            <span className="badge-pill badge-pill--public">Public</span>
          )}
          {repo.is_fork ? (
            <span className="badge-pill badge-pill--fork">Fork</span>
          ) : (
            <span
              className="badge-pill badge-pill--original"
              style={{ background: '#e0e7ff', color: '#3730a3' }}
            >
              Original
            </span>
          )}
          {repo.archived && <span className="badge-pill badge-pill--archived">Archived</span>}
          <span className="badge-pill badge-pill--branch">{repo.default_branch}</span>
        </div>
      </div>

      {repo.is_fork && repo.fork_source && (
        <p className="repo-fork-source">
          Nguồn gốc: <code>{repo.fork_source}</code>
        </p>
      )}

      <p className="repo-card-desc">
        {repo.description || <em style={{ color: 'var(--color-text-muted)' }}>Không có mô tả</em>}
      </p>

      {/* Meta stats */}
      <div className="repo-card-meta">
        <span className="meta-item" title="Số lượt gắn sao (Stars)">
          ★ {repo.stars_count}
        </span>
        <span className="meta-item" title="Số lượt forks">
          ⑂ {repo.forks_count}
        </span>
        {repo.open_issues_count > 0 && (
          <span className="meta-item" title="Số issues mở">
            ⊙ {repo.open_issues_count}
          </span>
        )}
        {repo.size_kb > 0 && (
          <span className="meta-item" title="Kích thước repository">
            📦 {repo.size_kb} KB
          </span>
        )}
        <span className="meta-item" style={{ marginLeft: 'auto' }}>
          Cập nhật: {formatDate(repo.pushed_at ?? repo.github_updated_at)}
        </span>
      </div>

      {/* Language Breakdown */}
      {languageEntries.length > 0 && (
        <div className="repo-languages">
          {/* Visual colored bar */}
          <div className="lang-bar" title="Tỷ lệ ngôn ngữ mã nguồn">
            {languageEntries.map(([lang, bytes]) => {
              const pct = totalLanguageBytes > 0 ? (bytes / totalLanguageBytes) * 100 : 0
              return (
                <div
                  key={lang}
                  className="lang-bar-segment"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: getLanguageColor(lang),
                  }}
                  title={`${lang}: ${formatBytes(bytes)} (${pct.toFixed(1)}%)`}
                />
              )
            })}
          </div>

          {/* Language tags with exact bytes */}
          <div className="lang-tags">
            {languageEntries.slice(0, 4).map(([lang, bytes]) => {
              const pct = totalLanguageBytes > 0 ? (bytes / totalLanguageBytes) * 100 : 0
              return (
                <span key={lang} className="lang-tag" title={`${bytes.toLocaleString()} bytes`}>
                  <span
                    className="lang-dot"
                    style={{ backgroundColor: getLanguageColor(lang) }}
                  />
                  <span>{lang}</span>
                  <span style={{ opacity: 0.7 }}>({pct.toFixed(0)}%)</span>
                </span>
              )
            })}
            {languageEntries.length > 4 && (
              <span className="lang-tag" style={{ opacity: 0.7 }}>
                +{languageEntries.length - 4} khác
              </span>
            )}
          </div>
        </div>
      )}

      <div style={{ marginTop: '0.875rem', paddingTop: '0.75rem', borderTop: '1px solid var(--color-border, #e2e8f0)', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <Link
          to={`/repositories/${repo.id}/activity`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 12px',
            fontSize: '0.85rem',
            borderRadius: 6,
            background: '#16a34a',
            color: '#ffffff',
            textDecoration: 'none',
            fontWeight: 500,
          }}
        >
          📊 Hoạt động (PBI-010) →
        </Link>
        <Link
          to={`/repositories/${repo.id}/analysis`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 12px',
            fontSize: '0.85rem',
            borderRadius: 6,
            background: 'var(--color-primary, #2563eb)',
            color: '#ffffff',
            textDecoration: 'none',
            fontWeight: 500,
          }}
        >
          🔍 Mã nguồn & Kiến trúc (PBI-012) →
        </Link>
        <Link
          to={`/repositories/${repo.id}/analysis?tab=verification`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 12px',
            fontSize: '0.85rem',
            borderRadius: 6,
            background: '#8b5cf6',
            color: '#ffffff',
            textDecoration: 'none',
            fontWeight: 500,
          }}
        >
          🛡️ Xác minh Fork & Đóng góp (PBI-013) →
        </Link>
      </div>
    </article>
  )
}
