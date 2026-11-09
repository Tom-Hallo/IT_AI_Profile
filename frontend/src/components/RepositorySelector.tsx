import { useEffect, useState } from "react";
import "./RepositorySelector.css";

type Scope = "public" | "private" | "combined";
type Repo = { id: number; full_name: string; private: boolean; html_url: string };
type Selection = { scope: Scope; repository_ids: number[] };
const scopes: Scope[] = ["public", "private", "combined"];

export default function RepositorySelector() {
  const [scope, setScope] = useState<Scope>("public");
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingScope, setLoadingScope] = useState<Scope | null>(null);
  const [ready, setReady] = useState(false);
  const loading = ready && loadingScope !== null;
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/github/selection", { credentials: "include", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Không thể tải lựa chọn");
        return response.json() as Promise<Selection>;
      })
      .then((data) => { if (!controller.signal.aborted) { setScope(data.scope); setSelected(data.repository_ids); } })
      .catch(() => { if (!controller.signal.aborted) setError("Không thể tải lựa chọn đã lưu."); })
      .finally(() => { if (!controller.signal.aborted) setReady(true); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setLoadingScope(scope);
        setError("");
        setNotice("");
      }
    });
    fetch(`/api/v1/github/repos?scope=${scope}`, { credentials: "include", signal: controller.signal })
      .then(async (response) => {
        if (response.status === 403) throw new Error("Cần cấp quyền truy cập private repositories.");
        if (response.status === 401) throw new Error("Vui lòng đăng nhập lại GitHub.");
        if (!response.ok) throw new Error("Không thể tải danh sách repository.");
        return response.json() as Promise<{ items: Repo[] }>;
      })
      .then((data) => { if (!controller.signal.aborted) setRepos(data.items); })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setRepos([]);
          setError(err instanceof Error ? err.message : "Lỗi không xác định");
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoadingScope(null); });
    return () => controller.abort();
  }, [scope, ready]);

  const eligible = new Set(repos.map((repo) => repo.id));
  const current = selected.filter((id) => eligible.has(id));
  const filtered = repos.filter((repo) => repo.full_name.toLowerCase().includes(query.toLowerCase()));
  function toggle(id: number) {
    setSelected((prev) => prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id]);
  }
  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/v1/github/selection", {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope, repository_ids: current }),
      });
      if (!response.ok) throw new Error(`Không thể lưu lựa chọn (HTTP ${response.status}).`);
      setSelected(current);
      setNotice("Đã lưu lựa chọn thành công.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể lưu lựa chọn.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ita-selector" aria-label="Chọn GitHub repository">
      <header><div><span className="ita-eyebrow">GITHUB · ANALYSIS SOURCES</span><h2>Repository Selection</h2><p>Chỉ những repository bạn chọn mới được đưa vào phân tích.</p></div><span className="ita-count">{current.length} selected</span></header>
      <div className="ita-tabs" role="group" aria-label="Phạm vi repository">
        {scopes.map((item) => <button type="button" key={item} aria-pressed={scope === item} className={scope === item ? "active" : ""} onClick={() => setScope(item)}>{item === "combined" ? "Combined" : item === "private" ? "Private" : "Public"}</button>)}
      </div>
      <input className="ita-search" aria-label="Tìm repository" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search repositories..." />
      {loading && <p role="status">Đang tải repositories…</p>}
      {error && <p role="alert" className="ita-error">{error}</p>}
      {error.includes("quyền truy cập private") && <a className="ita-grant" href="/api/v1/auth/github?include_private=true">Cấp quyền GitHub private →</a>}
      {notice && <p role="status" className="ita-success">{notice}</p>}
      <div className="ita-repos">
        {filtered.map((repo) => <label className="ita-repo" key={repo.id}><span><strong>{repo.full_name}</strong><small>{repo.private ? "🔒 Private" : "◉ Public"}</small></span><input type="checkbox" checked={selected.includes(repo.id)} onChange={() => toggle(repo.id)} /></label>)}
        {!loading && !error && filtered.length === 0 && <p>Không có repository phù hợp.</p>}
      </div>
      <footer><span>Quyền được kiểm tra lại khi lưu</span><button type="button" disabled={busy || loading || !!error || !ready} onClick={() => void save()}>{busy ? "Đang lưu…" : "Save selection"}</button></footer>
    </section>
  );
}
