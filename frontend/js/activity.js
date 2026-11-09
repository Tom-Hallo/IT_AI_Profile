const $ = id => document.getElementById(id);
const mode = $('mode');
function refresh() {
  $('presetField').hidden = mode.value !== 'preset';
  $('monthField').hidden = mode.value !== 'month';
  $('startField').hidden = $('endField').hidden = mode.value !== 'custom';
}
mode.addEventListener('change', refresh);
$('theme').addEventListener('click', () => document.body.classList.toggle('dark'));
$('filter').addEventListener('submit', async event => {
  event.preventDefault();
  const params = new URLSearchParams({mode:mode.value, timezone:$('timezone').value});
  if (mode.value === 'preset') params.set('preset', $('preset').value);
  if (mode.value === 'month') params.set('month', $('month').value);
  if (mode.value === 'custom') {
    params.set('start_date', $('start').value);
    params.set('end_date', $('end').value);
  }
  $('message').textContent = 'Đang tải...'; $('results').hidden = true;
  try {
    // Integrate repository ID from authenticated route/state, not user-controlled trust context.
    const repoId = new URLSearchParams(location.search).get('repository_id');
    if (!repoId || !/^\d+$/.test(repoId)) throw Error('Thiếu repository_id hợp lệ trên URL.');
    const response = await fetch(`/api/v1/repositories/${repoId}/activity/analysis?${params}`, {credentials:'same-origin'});
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Không thể truy vấn dữ liệu');
    $('commits').textContent = data.activity.commits;
    $('prs').textContent = data.activity.pull_requests_created;
    $('lines').textContent = `${data.activity.additions} / ${data.activity.deletions}`;
    $('base').textContent = data.base_code.status === 'available' ? `${data.base_code.lines} LOC` : 'Chưa có snapshot';
    $('range').textContent = `UTC: ${data.period.start_utc} → ${data.period.end_exclusive_utc} (không bao gồm mốc cuối)`;
    $('sync').textContent = data.sync.complete_through_end ? 'Dữ liệu đã đồng bộ qua cuối kỳ.' : 'Lưu ý: dữ liệu đồng bộ có thể chưa bao phủ toàn bộ kỳ.';
    $('message').textContent = ''; $('results').hidden = false;
  } catch(error) { $('message').textContent = error.message; }
});
refresh();
