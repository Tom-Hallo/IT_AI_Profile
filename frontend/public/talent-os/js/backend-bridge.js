/* V10 Phase 1: GitHub + dashboard data bridge. Same-origin API, cookie auth. */
const API = '/api/v1';
const $ = (selector, root = document) => root.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

async function apiRequest(path, options = {}) {
  const response = await fetch(API + path, {
    credentials: 'include',
    ...options,
    headers: { Accept: 'application/json', ...(options.headers || {}) },
  });
  if (!response.ok) {
    const error = new Error(`API ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function setStat(label, value, detail) {
  for (const card of document.querySelectorAll('.card.stat')) {
    if ($('.label', card)?.textContent.trim() !== label) continue;
    const number = $('.value', card);
    const note = $('.delta', card);
    if (number) number.textContent = String(value);
    if (note) note.textContent = detail;
  }
}

function clearUnverifiedDashboard() {
  const labels = ['AI TALENT SCORE', 'REPOSITORIES', 'VISIBLE REPOS', 'SKILLS DETECTED',
    'JOB ALIGNMENT', 'LANGUAGES', 'ANALYSIS JOBS', 'EVIDENCE'];
  for (const label of labels) setStat(label, '—', 'Chưa có dữ liệu xác thực');
  const heroScore = $('.hero-card .score');
  if (heroScore) heroScore.textContent = '— / 100';
  const chip = $('.hero-card .chip');
  if (chip) chip.textContent = 'CHƯA CÓ ĐIỂM ĐƯỢC XÁC MINH';
  const dashboardSections = [...document.querySelectorAll('#main section.card')];
  for (const section of dashboardSections) {
    const heading = $('h2', section)?.textContent.trim();
    if (heading === 'AI Signals') {
      const head = $('.section-head span', section);
      if (head) head.textContent = 'EVIDENCE REQUIRED';
      for (const row of section.querySelectorAll('.row-item')) row.remove();
      const actions = $('.actions', section);
      actions?.insertAdjacentHTML('beforebegin', '<p class="muted">Chưa có kết luận năng lực được xác minh. Hãy phân tích repository để tạo evidence.</p>');
    }
    if (heading === 'Growth trajectory') {
      const head = $('.section-head span', section);
      if (head) head.textContent = 'NO VERIFIED HISTORY';
      const chart = section.querySelector('[style*="height:210px"]');
      if (chart) chart.outerHTML = '<p class="muted">Chưa có dữ liệu lịch sử phân tích được xác minh.</p>';
      for (const row of section.querySelectorAll('.row-item')) row.remove();
    }
    if (heading === 'Skill Constellation') {
      const head = $('.section-head span', section);
      if (head) head.textContent = 'AWAITING SCORING';
      const cards = $('.skills', section);
      if (cards) cards.innerHTML = '<p class="muted">Chưa có kết quả chấm điểm kỹ năng được xác minh. Kết quả Insufficient không được coi là điểm 0.</p>';
      const detail = $('#skillDetail', section);
      if (detail) detail.textContent = 'Chọn repository đã phân tích để xem kỹ năng có evidence.';
    }
  }
}

function updateUser(user) {
  const name = user.full_name || user.name || user.email || 'Developer';
  const node = $('.side-bottom .user strong');
  if (node) node.textContent = name;
  const status = $('.side-bottom .status');
  if (status) status.textContent = 'Đã đăng nhập';
  const connect = $('#connectionStatus');
  if (connect) connect.textContent = `Đã đăng nhập · ${name}`;
}

function updateAuthFailure(error) {
  const message = error.status === 401 ? 'Chưa đăng nhập GitHub' : 'Không thể kết nối backend';
  const status = $('.side-bottom .status');
  if (status) status.textContent = message;
  const connect = $('#connectionStatus');
  if (connect) connect.textContent = message;
}

let currentRepoPage = 1;
async function loadRepositories(page = 1) {
  const result = await apiRequest(`/github/repositories?visibility=public&page=${page}&per_page=20`);
  if (!result || !Array.isArray(result.items)) throw new Error('Repository response không đúng cấu trúc');
  currentRepoPage = page;
  const total = Number.isInteger(result.total) ? result.total : result.items.length;
  setStat('REPOSITORIES', total, 'Public repositories đã đồng bộ');
  setStat('VISIBLE REPOS', total, 'Public repositories đã đồng bộ');
  if (document.body.dataset.page === 'github') renderRepositoryList(result);
}

function renderRepositoryList(data) {
  const section = [...document.querySelectorAll('#main section.card')]
    .find(node => $('h2', node)?.textContent.trim() === 'Repository explorer');
  if (!section) return;
  const rows = data.items.map(repo => {
    const id = Number(repo.id);
    const validId = Number.isSafeInteger(id) && id > 0;
    const name = repo.full_name || repo.name || 'Repository';
    const desc = repo.description || (repo.private ? 'Private repository' : 'Public repository');
    const action = validId
      ? `<a class="btn-ghost" href="/repositories/${encodeURIComponent(id)}/activity">View activity →</a>`
      : '<span class="tag">Không có ID</span>';
    return `<div class="row-item"><div class="repo-line"><div class="repo-icon">⌘</div><div><strong>${escapeHTML(name)}</strong><small>${escapeHTML(desc)}</small></div></div>${action}</div>`;
  }).join('');
  const previous = currentRepoPage > 1
    ? '<button class="btn-ghost" data-repo-page="prev">← Trước</button>' : '';
  const next = currentRepoPage < data.total_pages
    ? '<button class="btn-ghost" data-repo-page="next">Tiếp →</button>' : '';
  section.innerHTML = `<div class="section-head"><h2>Repository explorer</h2><span>BACKEND API · ${data.total} REPOS</span></div>
    ${rows || '<p class="muted">Chưa có repository công khai đã đồng bộ. Hãy kiểm tra GitHub Sync.</p>'}
    <div class="actions">
      <button class="btn-ghost" id="syncGithubBtn" type="button">
        ↻ Sync GitHub
      </button>
      ${previous}${next}
    </div>`;
}

async function syncPage() {
  const page = document.body.dataset.page;
  if (!page) return;
  if (page === 'dashboard' || page === 'github') clearUnverifiedDashboard();
  try {
    const user = await apiRequest('/auth/me');
    updateUser(user);
  } catch (error) {
    updateAuthFailure(error);
    return;
  }
  if (page !== 'dashboard' && page !== 'github') return;
  try {
    await loadRepositories();
  } catch (error) {
    const detail = `Không tải được repositories (${error.status || 'network'})`;
    setStat('REPOSITORIES', '—', detail);
    setStat('VISIBLE REPOS', '—', detail);
  }
}

async function triggerGithubSync(button) {
  button.disabled = true;
  button.textContent = 'Đang gửi yêu cầu...';

  try {
    const result = await apiRequest(
      '/github/sync?background=true&visibility=public',
      { method: 'POST' }
    );

    button.textContent = 'Đã đưa vào hàng đợi';

    console.info('GitHub sync:', result);
  } catch (error) {
    button.disabled = false;
    button.textContent = '↻ Sync GitHub';

    console.error('GitHub sync failed:', error);
    alert(`Đồng bộ thất bại (${error.status || 'network'})`);
  }
}
// Capture phase prevents app.js's demo click handlers from firing.
document.addEventListener('click', event => {
  const syncButton = event.target.closest('#syncGithubBtn');
  if (syncButton) {
    event.preventDefault();
    event.stopImmediatePropagation();
    triggerGithubSync(syncButton);
    return;
  }
  const oauth = event.target.closest('#githubOAuth');
  if (oauth) {
    event.preventDefault();
    event.stopImmediatePropagation();
    window.location.assign(API + '/auth/github');
    return;
  }
  const pager = event.target.closest('[data-repo-page]');
  if (pager) {
    event.preventDefault();
    event.stopImmediatePropagation();
    loadRepositories(Math.max(1, currentRepoPage + (pager.dataset.repoPage === 'next' ? 1 : -1)))
      .catch(() => { const toast = $('#toast'); if (toast) toast.textContent = 'Không tải được trang repositories'; });
    return;
  }
  const demoRepo = event.target.closest('[data-action="repo"]');
  if (demoRepo) {
    event.preventDefault();
    event.stopImmediatePropagation();
  }
}, true);

if (document.body.dataset.page) {
  syncPage();
} else {
  const score = $('.hero-art .score strong');
  if (score) score.textContent = '— / 100';
}
