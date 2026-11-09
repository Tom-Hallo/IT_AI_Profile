/** Same-origin cookie-authenticated polling; no fake progress. */
export function mountAnalysisJob(root, initialJobId) {
  let jobId = initialJobId;
  let active = true;
  const status = root.querySelector('[data-status]');
  const progress = root.querySelector('[data-progress]');
  const error = root.querySelector('[data-error]');
  const retry = root.querySelector('[data-retry]');
  const cancel = root.querySelector('[data-cancel]');
  async function api(suffix = '', method = 'GET') {
    const response = await fetch(`/api/v1/analysis/jobs/${jobId}${suffix}`, {
      method, credentials: 'same-origin', cache: 'no-store',
      headers: method === 'POST' ? { 'Content-Type': 'application/json' } : {},
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
  function render(job) {
    const pct = Math.min(100, Math.max(0, Number(job.progress) || 0));
    progress.value = pct;
    status.textContent = `${job.status} — ${pct}% — ${job.step}`;
    error.textContent = job.status === 'failed' ? `Analysis failed: ${job.error_code || 'unknown'}` : '';
    retry.hidden = !['failed', 'cancelled'].includes(job.status);
    cancel.hidden = !['queued', 'running'].includes(job.status);
  }
  async function poll() {
    while (active) {
      try {
        const job = await api();
        render(job);
        if (['failed', 'succeeded', 'cancelled'].includes(job.status)) return;
      } catch (_) { error.textContent = 'Không tải được tiến độ; đang thử lại.'; }
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }
  cancel.addEventListener('click', async () => { cancel.disabled = true; try { render(await api('/cancel', 'POST')); } finally { cancel.disabled = false; } });
  retry.addEventListener('click', async () => {
    retry.disabled = true;
    try { const job = await api('/retry', 'POST'); jobId = job.id; render(job); void poll(); }
    finally { retry.disabled = false; }
  });
  void poll();
  return () => { active = false; };
}
