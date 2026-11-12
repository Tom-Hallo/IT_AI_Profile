import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { fetchRepositories } from '@/features/github/api'
import type { Repository } from '@/features/github/types'
import { Card } from '@/shared/ui/Card'
import { Button } from '@/shared/ui/Button'
import { sendMentorChat } from './api'
import type { ChatMessage, MentorSources } from './types'
import './MentorPage.css'

const emptySources = (): MentorSources => ({
  github_repo_ids: [],
  include_cv: false,
  jd_text: null,
  roadmap_ids: [],
})

export function MentorPage() {
  const { user, isLoading: authLoading } = useAuth()
  const [repos, setRepos] = useState<Repository[]>([])
  const [sources, setSources] = useState<MentorSources>(emptySources)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    fetchRepositories({ per_page: 50 }, controller.signal)
      .then((res) => {
        if (!controller.signal.aborted) setRepos(res.items ?? [])
      })
      .catch(() => {
        if (!controller.signal.aborted) setRepos([])
      })
    return () => controller.abort()
  }, [user])

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

  function toggleRepo(id: number) {
    setSources((prev) => {
      const exists = prev.github_repo_ids.includes(id)
      return {
        ...prev,
        github_repo_ids: exists
          ? prev.github_repo_ids.filter((x) => x !== id)
          : [...prev.github_repo_ids, id].slice(0, 10),
      }
    })
  }

  if (authLoading) {
    return (
      <div className="mentor-page">
        <p role="status">Đang kiểm tra đăng nhập…</p>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="mentor-page">
        <Card>
          <h1>AI Mentor</h1>
          <p>Bạn cần đăng nhập để dùng mentor đa nguồn.</p>
          <Link to="/system-status">
            <Button variant="primary">Đăng nhập</Button>
          </Link>
        </Card>
      </div>
    )
  }

  return (
    <div className="mentor-page">
      <header className="mentor-header">
        <div>
          <p className="eyebrow">EPIC-06 / PBI-021</p>
          <h1>AI Mentor</h1>
          <p className="muted">
            Chọn nguồn GitHub / CV / JD / Roadmap — câu trả lời chỉ dùng dữ liệu được phép.
          </p>
        </div>
        <Link to="/dashboard">
          <Button variant="ghost">Về Dashboard</Button>
        </Link>
      </header>

      <div className="mentor-layout">
        <Card className="mentor-sources">
          <h2>Nguồn tư vấn</h2>

          <fieldset>
            <legend>GitHub repositories</legend>
            {repos.length === 0 && (
              <p className="muted">Chưa có repository. Hãy đồng bộ GitHub trước.</p>
            )}
            <ul className="repo-check-list">
              {repos.map((repo) => (
                <li key={repo.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={sources.github_repo_ids.includes(repo.id)}
                      onChange={() => toggleRepo(repo.id)}
                    />
                    <span>{repo.full_name || repo.name}</span>
                    {repo.private && <span className="badge">private</span>}
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>

          <label className="source-toggle">
            <input
              type="checkbox"
              checked={sources.include_cv}
              onChange={(e) =>
                setSources((prev) => ({ ...prev, include_cv: e.target.checked }))
              }
            />
            Dùng CV đã lưu
          </label>

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
              rows={4}
              placeholder="Dán job description tại đây…"
            />
          </label>

          <label className="field">
            Roadmap IDs (phân tách bằng dấu phẩy)
            <input
              type="text"
              value={sources.roadmap_ids.join(',')}
              onChange={(e) => {
                const ids = e.target.value
                  .split(',')
                  .map((part) => Number(part.trim()))
                  .filter((n) => Number.isFinite(n) && n > 0)
                setSources((prev) => ({ ...prev, roadmap_ids: ids.slice(0, 5) }))
              }}
              placeholder="vd: 1, 2"
            />
          </label>
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
                <p>{msg.content}</p>
                {msg.role === 'assistant' && msg.confidence != null && (
                  <p className="chat-meta">
                    Confidence: {(msg.confidence * 100).toFixed(0)}%
                  </p>
                )}
                {msg.evidence && msg.evidence.length > 0 && (
                  <details>
                    <summary>Evidence ({msg.evidence.length})</summary>
                    <ul>
                      {msg.evidence.map((ev, idx) => (
                        <li key={`${ev.source}-${idx}`}>
                          <strong>{ev.source}</strong>: {ev.label}
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
                      {msg.limitations.map((lim) => (
                        <li key={lim.code}>{lim.message}</li>
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