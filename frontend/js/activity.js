const $ = id => document.getElementById(id);
const mode = $('mode');
function refresh() {
  if ($('presetField')) $('presetField').hidden = mode.value !== 'preset';
  if ($('monthField')) $('monthField').hidden = mode.value !== 'month';
  if ($('startField') && $('endField')) $('startField').hidden = $('endField').hidden = mode.value !== 'custom';
}
if (mode) mode.addEventListener('change', refresh);
if ($('theme')) $('theme').addEventListener('click', () => document.body.classList.toggle('dark'));
if ($('filter')) $('filter').addEventListener('submit', async event => {
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
    const repoId = new URLSearchParams(location.search).get('repository_id');
    if (!repoId || !/^\d+$/.test(repoId)) {
      throw Error('Thiếu repository_id hợp lệ trên URL (Ví dụ: /activity?repository_id=1). Hãy đăng nhập và chọn repository từ Dashboard: <a href="/">Quay về Dashboard</a>');
    }
    const response = await fetch(`/api/v1/repositories/${repoId}/activity/analysis?${params}`, {credentials:'same-origin'});
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Không thể truy vấn dữ liệu');
    $('commits').textContent = data.activity.commits;
    $('prs').textContent = data.activity.pull_requests_created;
    $('lines').textContent = `${data.activity.additions} / ${data.activity.deletions}`;
    $('base').textContent = data.base_code.status === 'available' ? `${data.base_code.lines} LOC` : 'Chưa có snapshot';
    $('range').textContent = `UTC: ${data.period.start_utc} → ${data.period.end_exclusive_utc} (không bao gồm mốc cuối)`;
    $('sync').textContent = data.sync?.complete_through_end ? 'Dữ liệu đã đồng bộ qua cuối kỳ.' : 'Lưu ý: dữ liệu đồng bộ có thể chưa bao phủ toàn bộ kỳ.';
    $('message').innerHTML = ''; $('results').hidden = false;
  } catch(error) { $('message').innerHTML = error.message; }
});
refresh();
