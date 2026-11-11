import { useEffect, useRef, useState } from 'react';
import './EvidenceDrawer.css';

type Evidence = { id: number; commit_sha: string; file_path: string; line_number: number | null; pr_number: number | null; evidence_source: string; detection_method: string; confidence_score: number };
type Finding = { id: number; report_id: number; repository_id: number; classification: string; rationale: string; confidence_score: number; analyzer_version: string; evidence: Evidence[] };
type Props = { findingId: number | null; onClose: () => void };

export default function EvidenceDrawer({ findingId, onClose }: Props) {
  const [finding, setFinding] = useState<Finding | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (findingId === null) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const controller = new AbortController();
    fetch(`/api/v1/analysis/findings/${findingId}`, { credentials: 'include', cache: 'no-store', signal: controller.signal })
      .then(async (res) => { if (!res.ok) throw new Error('Evidence unavailable'); return await res.json() as Finding; })
      .then(setFinding)
      .catch(() => { if (!controller.signal.aborted) setError('Evidence unavailable or access denied'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    closeRef.current?.focus();
    return () => { controller.abort(); previousFocus?.focus(); };
  }, [findingId]);
  if (findingId === null) return null;
  return <div className="evidence-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <aside className="evidence-panel" role="dialog" aria-modal="true" aria-label="Evidence Inspector" onKeyDown={(e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Tab') {
        const controls = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('button, a[href], [tabindex]:not([tabindex="-1"])')).filter((x) => !x.hasAttribute('disabled'));
        if (!controls.length) return;
        if (e.shiftKey && document.activeElement === controls[0]) { e.preventDefault(); controls[controls.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === controls[controls.length - 1]) { e.preventDefault(); controls[0].focus(); }
      }
    }}>
      <header className="evidence-top"><div><small>AI TRACEABILITY</small><h2>Evidence Inspector</h2></div><button ref={closeRef} type="button" onClick={onClose} aria-label="Close evidence">✕</button></header>
      {loading && <p role="status">Loading evidence...</p>}
      {error && <p role="alert">{error}</p>}
      {finding && <section><h3>{finding.classification}</h3><p>{finding.rationale}</p><div className="evidence-metric">Confidence <strong>{Math.round(finding.confidence_score * 100)}%</strong></div><p>Report #{finding.report_id} · Analyzer {finding.analyzer_version}</p><h4>Supporting evidence</h4>{finding.evidence.map((item) => <article className="evidence-record" key={item.id}><strong>{item.file_path}</strong><small>{item.evidence_source} · {item.detection_method}</small><span>Commit: {item.commit_sha.slice(0, 12)}</span>{item.line_number !== null && <span>Line: {item.line_number}</span>}{item.pr_number !== null && <span>PR #{item.pr_number}</span>}</article>)}<p className="evidence-notice">🔒 Raw private source snippets are never returned by this endpoint.</p></section>}
    </aside>
  </div>;
}
