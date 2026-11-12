import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { fetchRepositories } from '@/features/github/api'
import type { RepositoryListResponse } from '@/features/github/types'
import { Card } from '@/shared/ui/Card'
import { Button } from '@/shared/ui/Button'
import { fetchMentorSources, sendMentorChat } from './api'
import type { ChatMessage, MentorSourceOptions, MentorSources } from './types'
import './MentorPage.css'

const emptySources = (): MentorSources => ({
  github_repo_ids: [],
  include_cv: false,
  cv_ids: [],
  jd_text: null,
  roadmap_ids: [],
})

export function MentorPage() {
  const { user, isLoading: authLoading } = useAuth()
  if (authLoading) {
    return <p className="mentor-page" role="status">Đang kiểm tra đăng nhập…</p>
  }

  if (!user) {
    return (
      <div className="mentor-page">
        <Card>
          <h1>AI Mentor</h1>
          <p>Bạn cần đăng nhập để dùng AI Mentor.</p>
          <Link to="/">Trang đăng nhập</Link>
        </Card>
      </div>
    )
  }

  return <MentorWorkspace key={user.id} />
}

function MentorWorkspace() {
  const [options, setOptions] = useState<MentorSourceOptions | null>(null)
  const [optionsError, setOptionsError] = useState(false)
  const [repoPage, setRepoPage] = useState(1)
  const [repoResult, setRepoResult] = useState<{ page: number; data: RepositoryListResponse | null }>()
  const repoData = repoResult?.page === repoPage ? repoResult.data : undefined
  const repos = repoData?.items ?? []
  const [sources, setSources] = useState<MentorSources>(emptySources)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchRepositories({ page: repoPage, per_page: 50 }, controller.signal)
      .then((res) => {
        if (!controller.signal.aborted) setRepoResult({ page: repoPage, data: res })
      })
      .catch(() => {
        if (!controller.signal.aborted) setRepoResult({ page: repoPage, data: null })
      })
    return () => controller.abort()
  }, [repoPage])

  useEffect(() => {
    const controller = new AbortController()
    fetchMentorSources(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setOptions(result)
      })
      .catch(() => {
        if (!controller.signal.aborted) setOptionsError(true)
      })
    return () => controller.abort()
  }, [])

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    const text = message.trim()
    if (!text || sending) return

    setError(null)
    setSending(true)
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
    }
    setMessages((prev) => [...prev, userMsg])
    setMessage('')

    try {
      const payloadSources: MentorSources = {
        ...sources,
        jd_text: sources.jd_text?.trim() || null,
      }
      const result = await sendMentorChat({ message: text, sources: payloadSources })
      const botMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: result.answer,
        evidence: result.evidence,
        sourcesUsed: result.sources_used,
        limitations: result.limitations,
        confidence: result.confidence,
      }
      setMessages((prev) => [...prev, botMsg])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gửi câu hỏi thất bại')
    } finally {
      setSending(false)
    }
  }

  function toggleSource(key: 'github_repo_ids' | 'cv_ids' | 'roadmap_ids', id: number) {
    setSources((prev) => ({
      ...prev,
      [key]: prev[key].includes(id) ? prev[key].filter((value) => value !== id) : [...prev[key], id],
    }))
  }

  return (
    <div className="mentor-page">
      <header className="mentor-header">
        <div>
          <h1>AI Mentor</h1>
          <p className="muted">
            Câu hỏi và dữ liệu bạn chọn sẽ được gửi đến nhà cung cấp AI đã cấu hình.
          </p>
        </div>
        <Link to="/">Trang chính</Link>
      </header>

      <div className="mentor-layout">
        <Card className="mentor-sources">
          <h2>Nguồn tư vấn</h2>

          <fieldset>
            <legend>GitHub repositories</legend>
            {repoData === undefined && <p role="status">Đang tải repository…</p>}
            {repoData === null && <p role="alert">Không tải được danh sách repository.</p>}
            <p className="muted">Đã chọn {sources.github_repo_ids.length}/10. Repo riêng tư cần hai lần đồng ý đúng phạm vi tệp.</p>
            {repoData && repos.length === 0 && (
              <p className="muted">Chưa có repository. Hãy đồng bộ GitHub trước.</p>
            )}
            <ul className="repo-check-list">
              {repos.map((repo) => (
                <li key={repo.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={sources.github_repo_ids.includes(repo.id)}
                      disabled={!sources.github_repo_ids.includes(repo.id) && sources.github_repo_ids.length >= 10}
                      onChange={() => toggleSource('github_repo_ids', repo.id)}
                    />
                    <span>{repo.full_name || repo.name}</span>
                    {repo.private && <span className="badge">private</span>}
                  </label>
                </li>
              ))}
            </ul>
            {(repoPage > 1 || (repoData?.total_pages ?? 0) > 1) && (
              <nav aria-label="Trang repository Mentor">
                <Button type="button" variant="ghost" disabled={repoPage === 1}
                  onClick={() => setRepoPage(repoPage - 1)}>Trang trước</Button>
                <Button type="button" variant="ghost"
                  disabled={repoPage >= (repoData?.total_pages ?? 0)}
                  onClick={() => setRepoPage(repoPage + 1)}>Trang sau</Button>
              </nav>
            )}
          </fieldset>

          {optionsError && <p role="alert">Không tải được danh sách CV và roadmap.</p>}
          <fieldset>
            <legend>CV đã lưu (tối đa 3)</legend>
            {options?.cvs.length === 0 && <p className="muted">Chưa có CV.</p>}
            <ul className="repo-check-list">
              {options?.cvs.map((cv) => (
                <li key={cv.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={sources.cv_ids.includes(cv.id)}
                      disabled={!sources.cv_ids.includes(cv.id) && sources.cv_ids.length >= 3}
                      onChange={() => toggleSource('cv_ids', cv.id)}
                    />
                    CV #{cv.id} · {new Date(cv.uploaded_at).toLocaleDateString('vi-VN')}
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>

          <label className="field">
            JD (dán mô tả công việc)
            <textarea
              value={sources.jd_text ?? ''}
              onChange={(e) =>
                setSources((prev) => ({
                  ...prev,
                  jd_text: e.target.value || null,
                }))
              }
              maxLength={8000}
              rows={4}
              placeholder="Dán job description tại đây…"
            />
          </label>

          <fieldset>
            <legend>Roadmap (tối đa 5)</legend>
            {options?.roadmaps.length === 0 && <p className="muted">Chưa có roadmap.</p>}
            <ul className="repo-check-list">
              {options?.roadmaps.map((roadmap) => (
                <li key={roadmap.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={sources.roadmap_ids.includes(roadmap.id)}
                      disabled={!sources.roadmap_ids.includes(roadmap.id) && sources.roadmap_ids.length >= 5}
                      onChange={() => toggleSource('roadmap_ids', roadmap.id)}
                    />
                    {roadmap.title}
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        </Card>

        <section className="mentor-chat">
          <Card className="mentor-messages" aria-live="polite">
            {messages.length === 0 && (
              <p className="muted">
                Đặt câu hỏi sau khi chọn nguồn. Ví dụ: “Kỹ năng backend của tôi phù hợp
                JD này không?”
              </p>
            )}
            {messages.map((msg) => (
              <article
                key={msg.id}
                className={`chat-bubble chat-bubble--${msg.role}`}
              >
                <p className="chat-content">{msg.content}</p>
                {Boolean(msg.sourcesUsed?.length) && (
                  <p className="chat-meta">Nguồn đã gửi: {msg.sourcesUsed?.join(', ')}</p>
                )}
                {msg.role === 'assistant' && msg.confidence != null && (
                  <p className="chat-meta">
                    Độ tin cậy: {(msg.confidence * 100).toFixed(0)}%
                  </p>
                )}
                {msg.evidence && msg.evidence.length > 0 && (
                  <details>
                    <summary>Bằng chứng ({msg.evidence.length})</summary>
                    <ul>
                      {msg.evidence.map((ev) => (
                        <li key={ev.id}>
                          <strong>[{ev.id}] {ev.source}</strong>  {ev.label}
                          {ev.detail ? ` — ${ev.detail}` : ''}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {msg.limitations && msg.limitations.length > 0 && (
                  <details>
                    <summary>Giới hạn ({msg.limitations.length})</summary>
                    <ul>
                      {msg.limitations.map((lim, index) => (
                        <li key={`${lim.code}-${index}`}>{lim.message}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </article>
            ))}
          </Card>

          {error && <p role="alert" className="mentor-error">{error}</p>}

          <form className="mentor-form" onSubmit={onSubmit}>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              aria-label="Câu hỏi cho AI Mentor"
              maxLength={4000}
              rows={3}
              placeholder="Nhập câu hỏi cho mentor…"
              disabled={sending}
            />
            <Button type="submit" variant="primary" disabled={sending || !message.trim()}>
              {sending ? 'Đang hỏi…' : 'Gửi'}
            </Button>
          </form>
        </section>
      </div>
    </div>
  )
}
