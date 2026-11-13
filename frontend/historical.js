const API = '/api/v1/historical';
const el = id => document.getElementById(id);
let snapshots = [];
const date = value => new Date(value).toLocaleString('vi-VN');
function option(item) { const node = document.createElement('option'); node.value = item.id; node.textContent = `${date(item.created_at)} · ${item.score}/100`; return node; }
async function load() {
  try {
    const response = await fetch(`${API}/snapshots`, { credentials: 'include' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    snapshots = await response.json();
    el('timeline').replaceChildren(); el('old').replaceChildren(); el('new').replaceChildren();
    for (const s of snapshots) {
      const entry = document.createElement('article'); entry.className = 'entry';
      const title = document.createElement('strong'); title.textContent = `${s.score}/100 · ${date(s.created_at)}`;
      const meta = document.createElement('div'); meta.className = 'meta'; meta.textContent = `Rubric ${s.rubric_version} · ${date(s.window_start)} – ${date(s.window_end)}`;
      entry.append(title, meta); el('timeline').append(entry);
      el('old').append(option(s)); el('new').append(option(s));
    }
    if (!snapshots.length) el('timeline').textContent = 'No snapshots yet.';
    if (snapshots.length > 1) { el('old').value = snapshots[1].id; el('new').value = snapshots[0].id; }
  } catch { el('timeline').textContent = 'Unable to load snapshots. Please retry.'; }
}
el('compare').addEventListener('click', async () => {
  const output = el('comparison'); output.replaceChildren();
  if (el('old').value === el('new').value) { output.textContent = 'Choose two different snapshots.'; return; }
  try {
    const query = new URLSearchParams({ old_id: el('old').value, new_id: el('new').value });
    const response = await fetch(`${API}/compare?${query}`, { credentials: 'include' });
    if (!response.ok) throw new Error();
    const result = await response.json();
    const summary = document.createElement('p'); summary.className = result.comparable ? 'delta' : 'warning';
    summary.textContent = result.comparable ? `Score delta: ${result.score_delta > 0 ? '+' : ''}${result.score_delta}` : `Comparison limited: ${result.warnings.join(', ')}`;
    output.append(summary);
    if (result.comparable) for (const [skill, delta] of Object.entries(result.skill_deltas)) {
      const line = document.createElement('p'); line.textContent = `${skill}: ${delta > 0 ? '+' : ''}${delta}`; output.append(line);
    }
  } catch { output.textContent = 'Comparison failed or access denied.'; }
});
el('refresh').addEventListener('click', load);
load();
