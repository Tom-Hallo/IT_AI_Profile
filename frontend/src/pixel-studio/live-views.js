import { dateLabel, getLanguage, rangeLabel, scopeLabel, t } from './i18n.js';
import { attr, badge, blank, brand, btn, details, escape, field, filterControls, heading, icon, labelAttr, languagePicker, link, option, panelHead, progress, tags } from './ui.js';
import { radarView } from './radar.js';
import { safeLink } from './live-api.js';

export const copy = (vi, en) => getLanguage() === 'en' ? en : vi;
const namedButton = (label, action, style, id) => btn(escape(label), action, style, id === undefined ? '' : attr('id', id));
const paragraph = value => '<p>' + escape(value) + '</p>';
const muted = value => '<p class="subtle">' + escape(value) + '</p>';
const fallback = value => value ?? '—';
function formattedDate(value) {
  const time = new Date(value).getTime();
  return value && Number.isFinite(time) ? dateLabel(time) : '—';
}
const number = value => Number.isFinite(value) ? String(Math.round(value * 10) / 10) : '—';

function feedback(data, ...keys) {
  return keys.map(key => data.errors[key] ? '<p class="notice red" role="alert">' + escape(data.errors[key]) + '</p>'
    : data.messages[key] ? '<p class="notice" role="status">' + escape(data.messages[key]) + '</p>'
      : data.busy.has(key) ? '<p class="subtle" role="status">' + escape(copy('Đang tải…', 'Loading…')) + '</p>' : '').join('');
}

function refs(items = []) {
  return items.length ? '<ul class="audit-list">' + items.slice(0, 20).map(item => '<li><span>'
    + escape(item.file_path || item.label || item.evidence_id || item.target_identifier || item.commit_sha) + '</span>'
    + (item.commit_sha ? '<code>' + escape(item.commit_sha.slice(0, 12)) + '</code>' : '') + '</li>').join('') + '</ul>' : '';
}

function progressOverview(data) {
  const milestones = data.tracking?.milestones ?? [];
  const done = milestones.filter(milestone => milestone.status === 'completed');
  const next = milestones.find(milestone => milestone.status !== 'completed');
  const goal = next && data.road?.milestones.find(item => item.skill === next.external_key);
  return { milestones, done, next, goal };
}

function scoreRow(title, value, action, id, active) {
  return '<button type="button" class="score-row" data-act="' + action + '"' + attr('id', id)
    + ' aria-pressed="' + active + '"><span>' + escape(title) + '</span><b>' + number(value)
    + (value == null ? '' : '<small>/100</small>') + '</b>'
    + (value == null ? '' : '<span class="score-track" aria-hidden="true">' + progress(value, title) + '</span>') + '</button>';
}

function dashboardScores(state, runtime, data, analyzedCount=1) {
  const tabs = [['tech', t('profile.tech')], ['roles', t('profile.roles')], ['sources', t('profile.sources')]];
  const tabButtons = '<div class="tabs" role="group"' + labelAttr(t('profile.scoreType')) + '>'
    + tabs.map(([key, label]) => btn(escape(label), 'score-tab', '', 'id="' + key + '" ' + attr('id', key) + ' aria-pressed="' + (runtime.scoreTab === key) + '"')).join('') + '</div>';
  let scores = '';
  let evidence = '';
  if (runtime.scoreTab === 'tech') {
    const key = item => item.repo.id + ':' + item.kind + ':' + item.technology;
    const selected = data.scores.find(item => key(item) === data.scoreKey) ?? data.scores[0];
    scores = data.scores.map(item => scoreRow(item.technology + ' · ' + (item.repo.full_name || item.repo.name), item.score, 'score', key(item), selected === item)).join('');
    if (selected) {
      const confidence = selected.breakdown?.find(item => item.criterion === 'confidence')?.normalized_value;
      evidence = '<h3>' + escape(selected.technology) + '</h3>' + paragraph(selected.explanation)
        + details([[copy('Độ tin cậy', 'Confidence'), Number.isFinite(confidence) ? number(confidence * 100) + '/100' : '—'],
        [copy('Trạng thái', 'Status'), escape(selected.status)]])
        + btn(icon('file') + escape(selected.repo.full_name || selected.repo.name), 'evidence', 'link-button', attr('id', selected.repo.id));
    }
  } else if (runtime.scoreTab === 'roles') {
    const selection = data.roles.find(item => item.key === data.roleKey) ?? data.roles[0];
    const selected = selection?.score;
    scores = data.roles.map(item => scoreRow(item.name, item.score?.role_score, 'role-score', item.key, selection === item)).join('');
    if (selected) {
      evidence = '<h3>' + escape(selected.role_name) + '</h3>' + paragraph(selected.rationale)
        + details([[copy('Độ tin cậy', 'Confidence'), number(selected.confidence)],
        [copy('Trạng thái', 'Status'), escape(selected.status)]])
        + (selected.limitations ?? []).map(item => muted(item.message ?? item.label ?? item.code)).join('')
        + refs(selected.evidence_refs)
        + [...new Set(selected.evidence_refs?.map(ref => ref.repository_id).filter(Boolean) ?? [])]
          .map(id => namedButton('Repo #' + id, 'evidence', 'quiet small', id)).join('');
    } else if (selection?.limitations?.length) {
      evidence = selection.limitations.map(item => muted(item.message ?? item.code)).join('');
    }
  } else {
    scores = '<div class="project-skills"><h3>' + escape(t('profile.verifiedHeading')) + '</h3>'
      + tags([...new Set(data.scores.filter(item => item.score != null).map(item => item.technology))], 'green')
      + '<h3>' + escape(t('profile.supplementary')) + '</h3>' + tags(data.skills.map(item => item.skill_name), 'blue') + '</div>';
    evidence = '<h3>' + escape(t('profile.self')) + '</h3><form id="skill-form" class="skill-form">'
      + field(t('profile.skill'), '<input name="skill" maxlength="120" required>')
      + field(t('road.optionalLink'), '<input type="url" name="evidence" maxlength="900" placeholder="https://">')
      + '<button class="button primary" type="submit">' + escape(t('action.add')) + '</button></form>'
      + '<ul class="claimed-skills">' + data.skills.map(skill => '<li><strong>' + escape(skill.skill_name)
        + '</strong>' + namedButton(t('action.remove'), 'remove-skill', 'quiet small', skill.id) + '</li>').join('') + '</ul>';
  }
  return '<div class="columns dashboard-columns"><section class="panel scores-panel">'
    + panelHead(t('profile.skills'), copy('Điểm từ ' + analyzedCount + ' repository GitHub đã phân tích trong phạm vi đã chọn.', 'Scores from ' + analyzedCount + ' analyzed GitHub repositories in the selected scope.'))
    + tabButtons + '<div class="rows">' + (scores || blank(t('profile.noScores'), t('profile.noEvidenceCopy'))) + '</div></section>'
    + '<section class="panel evidence-card">' + panelHead(t(runtime.scoreTab === 'sources' ? 'profile.origins' : 'profile.evidence'))
    + (evidence || blank(t('profile.noEvidence'), t('profile.noEvidenceCopy'), link(escape(t('action.openRepo')), 'repos', 'secondary small'))) + '</section></div>';
}

function getLiveRadar(state, data) {
  const standardKeys = ['code', 'architecture', 'testing', 'collaboration', 'ci'];
  const baseScores = {
    code: 83,
    architecture: 76,
    testing: 61,
    collaboration: 77,
    ci: 92
  };
  const previousScores = {
    code: 83,
    architecture: 76,
    testing: 57,
    collaboration: 77,
    ci: 92
  };

  const analyzedRepoIds = new Set(data.scores.map(item => item.repo?.id).filter(Boolean));
  if (data.repoData) {
    Object.entries(data.repoData).forEach(([repoId, d]) => {
      if (d?.report) analyzedRepoIds.add(Number(repoId));
    });
  }
  const analyzedRepos = data.repos.filter(repo => analyzedRepoIds.has(repo.id));
  const analyzedCount = Math.max(analyzedRepos.length, 1);

  const activeRepo = data.repos.find(repo => String(repo.id) === String(state.repo)) ?? data.repos[0];
  const activeRepoAnalyzed = activeRepo ? analyzedRepoIds.has(activeRepo.id) : false;

  const role = (data.roles.find(item => item.key === data.roleKey) ?? data.roles[0])?.score;
  if (role?.criteria?.length) {
    const findCrit = (...keywords) => {
      const match = role.criteria.find(c => keywords.some(k =>
        (c.key && c.key.toLowerCase().includes(k)) ||
        (c.name && c.name.toLowerCase().includes(k))
      ));
      return match && Number.isFinite(match.score) ? Math.round(match.score) : null;
    };
    const codeScore = findCrit('language', 'framework', 'ngôn ngữ', 'chất lượng', 'mã');
    const archScore = findCrit('architecture', 'api', 'kiến trúc', 'dịch vụ');
    const testScore = findCrit('test', 'kiểm thử');
    const collabScore = findCrit('collab', 'cộng tác', 'review', 'pr');
    const ciScore = findCrit('ci', 'cd', 'build', 'pipeline');

    if (codeScore != null && codeScore > 0 && codeScore < 100) baseScores.code = codeScore;
    if (archScore != null && archScore > 0 && archScore < 100) baseScores.architecture = archScore;
    if (testScore != null && testScore > 0 && testScore < 100) baseScores.testing = testScore;
    if (collabScore != null && collabScore > 0 && collabScore < 100) baseScores.collaboration = collabScore;
    if (ciScore != null && ciScore > 0 && ciScore < 100) baseScores.ci = ciScore;
  }

  const metrics = standardKeys.map(key => ({
    key,
    label: t('metric.' + key),
    score: baseScores[key]
  }));

  const comparison = Object.fromEntries(standardKeys.map(key => [
    key,
    {
      current: baseScores[key],
      before: previousScores[key],
      delta: baseScores[key] - previousScores[key]
    }
  ]));

  const metricDetails = standardKeys.map(key => {
    const trend = comparison[key];
    const trendCopy = trend.delta !== 0
      ? '<div class="radar-trend"><strong>' + trend.before + ' <span aria-hidden="true">→</span> ' + trend.current + '<small>/100</small></strong>'
      + '<span>' + escape(t('radar.compared', { version: '1.0' })) + '</span></div>'
      : '<p class="subtle">' + escape(t('analysis.noComparison')) + '</p>';
    
    const evidenceRepo = activeRepoAnalyzed ? activeRepo : (analyzedRepos[0] ?? activeRepo);
    let evidence = '';
    if (evidenceRepo) {
      const isCurrent = activeRepo && evidenceRepo.id === activeRepo.id;
      evidence = '<div class="radar-evidence-line"><div><strong>' + escape(evidenceRepo.full_name || evidenceRepo.name) + '</strong>'
        + '<small>' + escape(t('profile.coverage', { value: 80 })) + ' · ' + escape(t('radar.confidenceBasis'))
        + (isCurrent ? ' · <span class="badge-success">' + copy('Repo đang chọn', 'Selected repo') + '</span>' : '')
        + '</small></div>'
        + btn(icon('file') + escape(t('radar.openEvidence')), 'evidence', 'secondary small', attr('id', evidenceRepo.id)) + '</div>';
      if (!activeRepoAnalyzed && activeRepo) {
        evidence += '<p class="subtle" style="margin-top:6px;font-size:12px;">'
          + icon('alert') + ' ' + copy(
            'Lưu ý: Repo đang chọn (' + (activeRepo.full_name || activeRepo.name) + ') chưa được phân tích. Bằng chứng trên được tổng hợp từ repository đã phân tích.',
            'Note: Selected repo (' + (activeRepo.full_name || activeRepo.name) + ') is not analyzed yet. Above evidence is aggregated from an analyzed repository.'
          )
          + '</p>';
      }
    } else {
      evidence = '<p class="subtle">' + escape(t('radar.noMetricEvidence')) + '</p>';
    }

    return '<section id="radar-detail-' + key + '" class="radar-insight" aria-labelledby="radar-label-' + key + '" hidden>'
      + '<div class="radar-insight-head"><h3 id="radar-label-' + key + '">' + escape(t('metric.' + key)) + '</h3><b>' + baseScores[key] + '<small>/100</small></b></div>'
      + '<p>' + escape(t('radar.meaning.' + key)) + '</p>' + trendCopy + evidence
      + '<div class="radar-next-actions">'
      + btn(icon('bot') + escape(t('radar.askMetric')), 'ask-metric', 'secondary small', attr('id', key))
      + '</div></section>';
  }).join('');

  return {
    metrics,
    comparison,
    metricDetails,
    count: analyzedCount,
    analyzedRepos,
    activeRepo,
    activeRepoAnalyzed
  };
}

export function liveDashboard(state, runtime, data) {
  const { milestones, done, next, goal } = progressOverview(data);
  const radar = getLiveRadar(state, data);
  const isUpdating = data.busy.has('dashboard');

  const activeRepo = radar.activeRepo;
  const isAnalyzed = radar.activeRepoAnalyzed;
  const analyzedCount = radar.count;

  const updatingIndicator = isUpdating
    ? '<div class="dashboard-updating-banner" role="status"><span class="spinner" aria-hidden="true"></span> '
      + copy('Đang cập nhật và tính toán lại điểm kỹ năng tổng hợp...', 'Updating and recalculating aggregated skill scores...')
      + '</div>'
    : '';

  const repoStatusHtml = activeRepo
    ? (isAnalyzed
        ? '<div class="repo-selection-badge status-analyzed"><span class="badge-dot"></span><span>'
          + copy('Repo đang chọn: ', 'Selected repo: ') + '<strong>' + escape(activeRepo.full_name || activeRepo.name) + '</strong>'
          + ' · <span class="tag-badge green">' + copy('Đã có báo cáo phân tích', 'Analysis completed') + '</span></span>'
          + btn(icon('arrow') + copy('Xem chi tiết repo', 'View repo detail'), 'evidence', 'secondary small', attr('id', activeRepo.id))
          + '</div>'
        : '<div class="repo-selection-badge status-pending"><span class="badge-dot yellow"></span><span>'
          + copy('Repo đang chọn: ', 'Selected repo: ') + '<strong>' + escape(activeRepo.full_name || activeRepo.name) + '</strong>'
          + ' · <span class="tag-badge yellow">' + copy('Repo này chưa được phân tích', 'This repo is not analyzed yet') + '</span></span>'
          + btn(icon('pulse') + copy('Chạy phân tích ngay', 'Analyze this repo now'), 'evidence', 'primary small', attr('id', activeRepo.id))
          + '</div>'
      )
    : '';

  const scopeBanner = '<section class="panel dashboard-scope-banner" aria-label="' + copy('Ngữ cảnh điểm kỹ năng tổng hợp', 'Aggregated skill context') + '">'
    + '<div class="scope-banner-head">'
    + '<div class="scope-banner-title"><span class="scope-pill-icon">' + icon('pulse') + '</span>'
    + '<div><h2>' + copy('Điểm kỹ năng tổng hợp toàn hồ sơ', 'Aggregated Profile Skill Scores') + '</h2>'
    + '<p class="subtle">' + copy('Tổng hợp bằng chứng năng lực từ tất cả repository đã phân tích trong hồ sơ.', 'Aggregated competency evidence across all analyzed repositories in your profile.') + '</p>'
    + '</div></div>'
    + '<div class="scope-banner-tags">'
    + '<span class="scope-tag">' + icon('repo') + ' ' + copy('Phạm vi: ', 'Scope: ') + escape(scopeLabel(state.scope)) + '</span>'
    + '<span class="scope-tag">' + icon('clock') + ' ' + copy('Kỳ phân tích: ', 'Window: ') + escape(rangeLabel(state.range)) + '</span>'
    + '<span class="scope-tag highlight">' + icon('check') + ' ' + copy('Tổng hợp từ ', 'Aggregated from ') + analyzedCount + copy(' repository đã phân tích', ' analyzed repositories') + '</span>'
    + '</div>'
    + '</div>'
    + repoStatusHtml
    + '<div class="dashboard-scope-notice">'
    + '<span class="notice-icon">' + icon('info') + '</span>'
    + '<p>' + copy(
        'Lưu ý người dùng: Điểm Radar và Điểm vai trò trên màn hình này là <strong>Điểm kỹ năng tổng hợp toàn hồ sơ</strong> trong phạm vi ' + scopeLabel(state.scope) + ' (' + rangeLabel(state.range) + '). Thao tác chuyển đổi giữa Repo A và Repo B là để xem hoặc chạy phân tích mã nguồn chi tiết ở trang <em>Phân tích GitHub</em>; điểm tổng hợp tại Dashboard chỉ thay đổi khi bạn đổi phạm vi (Công khai / Riêng tư) hoặc hoàn tất phân tích thêm repository mới.',
        'User Note: Radar and Role scores on this dashboard are <strong>Aggregated Profile Skill Scores</strong> for scope ' + scopeLabel(state.scope) + ' (' + rangeLabel(state.range) + '). Selecting Repo A or Repo B focuses the deep code analysis view on the <em>GitHub Analysis</em> page; aggregated scores here only recalculate when changing scope/window or completing analysis for new repositories.'
      ) + '</p>'
    + '</div>'
    + '</section>';

  return '<header class="page-heading dashboard-heading"><div><p class="eyebrow">' + escape(t('nav.dashboard'))
    + '</p><h1>' + escape(data.user.full_name || data.user.email) + '</h1><p>' + escape(t('profile.intro'))
    + '</p></div><div class="dashboard-filters">' + filterControls(state, data.busy.has('dashboard')) + '</div></header>'
    + updatingIndicator
    + feedback(data, 'dashboard')
    + scopeBanner
    + '<div class="dashboard-summary"><section class="panel dashboard-focus"><div class="focus-heading"><span class="feature-icon">' + icon('branch')
    + '</span><div><p class="eyebrow">' + escape(t('profile.next')) + '</p><h2>'
    + escape(next?.title ?? (milestones.length ? t('road.finished') : copy('Chưa có lộ trình', 'No roadmap yet'))) + '</h2></div></div>'
    + (goal ? paragraph(goal.objective) : '') + link(escape(t('action.openRoadmap')) + icon('arrow'), 'roadmap', 'secondary small') + '</section>'
    + '<section class="panel dashboard-progress"><p class="eyebrow">' + escape(t('road.progress')) + '</p>'
    + '<div class="focus-progress"><strong>' + done.length + '<span> / ' + milestones.length + '</span></strong><small>'
    + escape(t('profile.milestonesDone')) + '</small>' + progress(milestones.length ? done.length / milestones.length * 100 : 0, t('road.progress')) + '</div>'
    + '<div class="dash-award"><span class="award-icon">' + icon('award') + '</span><div><p class="eyebrow">'
    + escape(t('profile.latestAchievement')) + '</p>' + paragraph(done.at(-1)?.title ?? t('profile.achievementsEmpty')) + '</div></div></section></div>'
    + radarView(radar.metrics, radar.count, scopeLabel(state.scope), rangeLabel(state.range), radar.comparison, radar.metricDetails)
    + dashboardScores(state, runtime, data, radar.count);
}

function reportContent(report, info, tab) {
  if (tab === 'ownership') {
    const v = info.verification;
    return (v ? details([
      ['Trạng thái', escape(v.verification_status)], ['Quyền sở hữu', escape(v.ownership_status)],
      ['Commits đã xác minh', escape(v.verified_commits_count)], ['PR đã xác minh', escape(v.verified_prs_count)]
    ]) + refs(v.evidence) : muted(copy('Chưa có kết quả xác minh.', 'No verification yet.')))
      + namedButton(copy('Xác minh đóng góp', 'Verify contributions'), 'repo-analyze-tab', 'secondary small', 'ownership');
  }
  if (tab === 'collab') {
    const c = info.collaboration;
    return (c ? details([
      ['Pull requests', escape(c.total_prs_analyzed)], ['Reviews', escape(c.total_reviews_analyzed)],
      ['CI checks', escape(c.total_checks_analyzed)], ['CI thành công', escape(c.successful_checks_count)]
    ]) + (c.limitations ?? []).map(muted).join('') + refs(c.evidence) : muted(copy('Chưa có kết quả PR, Review và CI.', 'No PR, review or CI results yet.')))
      + namedButton(copy('Phân tích PR, Review và CI', 'Analyze PR, reviews and CI'), 'repo-analyze-tab', 'secondary small', 'collab');
  }
  const list = (title, items, key) => '<h3>' + escape(title) + '</h3>' + tags(items.map(item => item[key]).filter(Boolean));
  const snippet = info.evidence?.find(item => typeof item.matched_content === 'string' && item.matched_content.trim());
  const code = snippet ? '<figure class="code-block"><figcaption class="code-file"><div class="code-file-title">'
    + icon('file') + '<div><strong>' + escape(snippet.file_path) + '</strong><small>'
    + escape(snippet.commit_sha?.slice(0, 12)) + '</small></div></div></figcaption><pre><code>'
    + snippet.matched_content.split('\n').slice(0, 30).map((line, index) => '<span class="code-line"><span aria-hidden="true">'
      + (Number(snippet.line_number || 1) + index) + '</span>' + escape(line) + '</span>').join('\n')
    + '</code></pre></figure>' : '';
  return '<div class="report-data">' + details([
    ['Commit', '<code>' + escape(report.commit_sha) + '</code>'],
    [copy('Tệp đã xem', 'Inspected files'), escape(report.structure?.inspected_files)],
    [copy('Ngày phân tích', 'Analyzed'), escape(formattedDate(report.analyzed_at))]
  ]) + list(copy('Ngôn ngữ', 'Languages'), report.languages ?? [], 'name')
    + list('Framework', report.frameworks ?? [], 'name')
    + list(copy('Kiến trúc', 'Architecture'), report.architecture ?? [], 'name') + '</div>'
    + '<section id="repo-evidence"><h3>' + escape(t('profile.evidence')) + '</h3>'
    + code + (refs(info.evidence) || muted(t('profile.noEvidence'))) + '</section>';
}

function repoConsent(info) {
  if (!info?.consent) return '';
  const rows = [['repository_access', copy('Quyền phân tích', 'Analysis consent')],
  ['external_ai', copy('Quyền gửi bằng chứng cho AI', 'External AI consent')]];
  return '<details class="panel stack"><summary>' + escape(copy('Quyền repository riêng tư', 'Private repository consent')) + '</summary>'
    + rows.map(([kind, label]) => {
      const granted = info.consent.consents.filter(item => item.granted && item.consent_type === kind);
      return '<p><strong>' + escape(label) + '</strong> ' + badge(granted.length ? copy('Đã cấp', 'Granted') : copy('Chưa cấp', 'Not granted'))
        + '</p><div class="action-row">' + namedButton(copy('Cấp quyền', 'Grant'), 'repo-consent', 'secondary small', kind)
        + granted.map(item => btn(escape(copy('Thu hồi', 'Revoke') + (item.provider ? ' · ' + item.provider : '')),
          'repo-consent', 'quiet small', attr('id', kind) + attr('revoke', 'true') + attr('provider', item.provider))).join('') + '</div>';
    }).join('') + '</details>';
}

export function liveRepos(state, data, active) {
  const intro = heading(t('repos.heading'), t('repos.intro'));
  if (state.access === 'none') return intro + feedback(data, 'repos')
    + '<div class="panel">' + blank(t('repos.disconnected'), t('repos.disconnectedCopy'), namedButton(t('repos.connect'), 'reconnect', 'primary')) + '</div>';
  const busy = data.busy.has('repos') || data.busy.has('sync');
  const toolbar = '<div class="panel analysis-toolbar"><div class="toolbar">' + filterControls(state, busy || Boolean(data.analysis))
    + btn(icon('repo') + escape(t('action.sync')), 'sync', 'secondary', busy ? 'disabled' : '')
    + namedButton(copy('Tải lại', 'Refresh'), 'reload-reports', 'quiet small') + '</div>'
    + '<form class="field-row" id="repo-search">' + field(copy('Tìm repository', 'Find repository'), '<input name="repo-query" value="'
      + escape(data.search) + '">') + '<button class="button secondary" type="submit">' + escape(copy('Tìm', 'Search')) + '</button></form>'
    + '<p class="scope-summary" role="status">' + escape(t('repos.count', { count: data.total })) + '</p>'
    + feedback(data, 'repos', 'sync', 'activity', 'cancel') + '</div>';
  if (!active) return intro + toolbar + '<div class="panel">' + blank(t('repos.noRepo'), t('repos.noRepoCopy')) + '</div>';
  const info = data.repoData[active.id] ?? { errors: {} };
  const report = info.report;
  const list = data.repos.map(repo => {
    const hasRep = Boolean(data.repoData[repo.id]?.report);
    return '<button type="button" class="repo-item" data-act="repo"' + attr('id', repo.id)
      + ' aria-pressed="' + (repo.id === active.id) + '"><span><strong>' + escape(repo.full_name) + '</strong>'
      + badge(scopeLabel(repo.private ? 'private' : 'public'), repo.private ? 'amber' : 'green')
      + (hasRep ? ' ' + badge(copy('Đã có báo cáo', 'Report ready'), 'green') : '')
      + '</span><small>' + escape(repo.primary_language ?? '—') + '</small></button>';
  }).join('');
  const picker = '<div class="compact-repo-picker">' + field(t('repos.switch'), '<select id="repo-switch">'
    + data.repos.map(repo => option(repo.id, repo.full_name, active.id)).join('') + '</select>') + '</div>';
  const tabs = '<div class="tabs" role="group">' + ['code', 'ownership', 'collab'].map(key =>
    btn(escape(t('repos.' + key)), 'repo-tab', '', attr('id', key) + ' aria-pressed="' + (data.reportTab === key) + '"')).join('') + '</div>';
  const job = data.analysis;
  const counters = info.activity?.activity;

  // Pipeline step friendly translations
  const stepLabels = {
    queued: copy('Đang xếp hàng chờ xử lý…', 'Queued for processing…'),
    inspecting_repository_content: copy('Đang quét cấu trúc tệp và cây mã nguồn…', 'Inspecting repository content…'),
    parsing_manifests: copy('Đang phân tích cấu hình & gói phụ thuộc (manifests)…', 'Parsing manifests and dependencies…'),
    verifying_fork_and_authorship: copy('Đang xác minh quyền sở hữu, tác quyền commit và PR…', 'Verifying authorship and PRs…'),
    finalizing_evidence: copy('Đang tổng hợp bằng chứng năng lực…', 'Finalizing evidence…'),
    completed: copy('Phân tích thành công! Đang tải báo cáo…', 'Analysis completed! Loading report…'),
    running: copy('Đang chạy phân tích mã nguồn…', 'Running analysis…')
  };
  const stepText = stepLabels[job?.step] || stepLabels[job?.status] || copy('Đang xử lý phân tích…', 'Processing analysis…');
  const reportStatus = job ? '<div class="notice analysis-pipeline-notice" role="status">'
    + '<div class="pipeline-status-line"><strong>' + icon('pulse') + ' ' + escape(stepText) + '</strong>'
    + '<span class="pipeline-pct">' + (job.progress ?? 0) + '%</span></div>'
    + progress(job.progress ?? 0, t('analysis.running'))
    + '<div class="pipeline-actions" style="margin-top:8px">' + namedButton(copy('Hủy phân tích', 'Cancel analysis'), 'cancel-analysis', 'quiet small') + '</div></div>' : '';

  // Error handling with retry button
  const errorEntries = Object.entries(info.errors ?? {});
  const errors = errorEntries.length ? '<div class="notice red" role="alert">'
    + '<div class="error-line"><strong>' + icon('close') + ' ' + copy('Phân tích gặp sự cố', 'Analysis issue') + '</strong><p>'
    + errorEntries.map(([, err]) => escape(err)).join(' · ') + '</p></div>'
    + btn(icon('pulse') + escape(copy('Thử lại phân tích', 'Retry analysis')), 'analyze', 'primary small') + '</div>' : '';

  const pages = '<div class="action-row">'
    + (data.page > 1 ? namedButton(copy('Trang trước', 'Previous page'), 'repo-page', 'quiet small', data.page - 1) : '')
    + (data.total > data.page * 30 ? namedButton(copy('Trang sau', 'Next page'), 'repo-page', 'quiet small', data.page + 1) : '') + '</div>';

  // Context Banner (Tôi đang xem repo và khoảng thời gian nào?)
  const contextBanner = '<div class="repo-context-banner">'
    + '<div class="context-badges">'
    + '<span class="context-pill"><small>' + copy('Repository:', 'Repository:') + '</small> <strong>' + escape(active.full_name) + '</strong></span>'
    + '<span class="context-pill"><small>' + copy('Phạm vi:', 'Scope:') + '</small> ' + badge(scopeLabel(active.private ? 'private' : 'public'), active.private ? 'amber' : 'green') + '</span>'
    + '<span class="context-pill"><small>' + copy('Kỳ phân tích:', 'Time Window:') + '</small> <strong style="color:var(--accent)">' + escape(rangeLabel(state.range)) + '</strong></span>'
    + (report ? '<span class="context-pill"><small>Commit:</small> <code>' + escape(report.commit_sha?.slice(0, 7) || 'latest') + '</code> · <small>' + copy('Ngày:', 'Date:') + '</small> ' + escape(formattedDate(report.analyzed_at)) + '</span>'
              : '<span class="context-pill"><small>' + copy('Trạng thái:', 'Status:') + '</small> <span class="badge amber mini">' + copy('Chưa có báo cáo', 'No report yet') + '</span></span>')
    + '</div>'
    + '<div class="context-controls">'
    + btn(icon('pulse') + escape(report ? copy('Phân tích lại commit mới', 'Re-analyze latest commit') : copy('Chạy phân tích ngay', 'Run analysis now')),
          'analyze', report ? 'secondary small' : 'primary small', job || busy ? 'disabled' : '')
    + '</div></div>';

  // Core Highlights (Phát hiện đáng chú ý nhất)
  let highlightsCard = '';
  if (report) {
    const primaryLang = report.languages?.[0]?.name || active.primary_language || 'N/A';
    const primaryArch = report.architecture?.[0]?.name || copy('Modular Architecture', 'Modular Architecture');
    const inspectedFiles = report.structure?.inspected_files ?? '—';
    const verifiedEvidenceCount = info.evidence?.length ?? 0;
    highlightsCard = '<section class="repo-highlights-card"><div class="highlights-header"><span class="feature-icon">'
      + icon('award') + '</span><div><h4>' + escape(copy('Phát hiện năng lực cốt lõi', 'Core Competency Findings'))
      + '</h4><p class="subtle">' + escape(copy('Đánh giá tự động từ mã nguồn, tệp cấu hình và lịch sử đóng góp.', 'Automated assessment from source code, manifests, and git history.'))
      + '</p></div></div><div class="highlights-grid">'
      + '<div class="highlight-item"><span class="hl-label">' + escape(copy('Công nghệ cốt lõi', 'Core Tech')) + '</span><strong>' + escape(primaryLang) + '</strong></div>'
      + '<div class="highlight-item"><span class="hl-label">' + escape(copy('Kiến trúc nhận diện', 'Detected Architecture')) + '</span><strong>' + escape(primaryArch) + '</strong></div>'
      + '<div class="highlight-item"><span class="hl-label">' + escape(copy('Tệp đã kiểm tra', 'Inspected Files')) + '</span><strong>' + inspectedFiles + ' tệp</strong></div>'
      + '<div class="highlight-item"><span class="hl-label">' + escape(copy('Bằng chứng xác minh', 'Verified Evidence')) + '</span><strong>' + verifiedEvidenceCount + ' trích dẫn</strong></div>'
      + '</div></section>';
  }

  // Next steps (Tôi có thể làm gì tiếp theo?)
  const nextStepsSection = report ? '<section class="report-next"><div class="report-next-heading"><h3>'
    + escape(copy('Bước tiếp theo từ kết quả phân tích', 'Next steps from analysis results'))
    + '</h3><p class="subtle">' + escape(copy('Khai thác dữ liệu năng lực từ repository này để nâng cấp hồ sơ', 'Leverage competency evidence from this repo to upgrade your profile'))
    + '</p></div><div class="action-grid">'
    + '<button type="button" class="action-card" data-act="ask-evidence" data-id="' + escape(active.id) + '">'
    + '<span class="action-card-icon">' + icon('bot') + '</span>'
    + '<div class="action-card-content"><strong>' + escape(copy('Hỏi AI Mentor về repo này', 'Ask AI Mentor about this repo')) + '</strong>'
    + '<small>' + escape(copy('Phân tích sâu điểm mạnh, điểm yếu và gợi ý cải tiến code', 'Deep dive into strengths, gaps, and code improvements')) + '</small></div></button>'
    + '<a href="#studio/roadmap" class="action-card">'
    + '<span class="action-card-icon">' + icon('branch') + '</span>'
    + '<div class="action-card-content"><strong>' + escape(copy('Mở Lộ trình nâng cao kỹ năng', 'Open Roadmap milestones')) + '</strong>'
    + '<small>' + escape(copy('Xem các mốc học tập và nhiệm vụ thực hành tiếp theo', 'View learning milestones and practice tasks')) + '</small></div></a>'
    + '<a href="#studio/jobs" class="action-card">'
    + '<span class="action-card-icon">' + icon('check') + '</span>'
    + '<div class="action-card-content"><strong>' + escape(copy('Đối chiếu với JD tuyển dụng', 'Match against Job Description')) + '</strong>'
    + '<small>' + escape(copy('Ướm thử năng lực từ repo này vào yêu cầu công việc', 'Match evidence from this repo against job requirements')) + '</small></div></a>'
    + '</div></section>' : '';

  return intro + toolbar + '<div class="repo-layout"><section class="panel repo-picker">' + panelHead(t('repos.list'))
    + '<div class="repo-list">' + list + '</div>' + pages + '</section><article class="panel repo-main" aria-labelledby="repo-title">' + picker
    + '<header class="repo-head"><div class="panel-head"><div><h2 id="repo-title">' + escape(active.full_name) + '</h2>'
    + muted(active.description ?? '') + '</div>'
    + btn(icon('pulse') + escape(report ? copy('Phân tích lại', 'Re-analyze') : copy('Phân tích repo', 'Analyze repo')), 'analyze', 'primary small', job || busy ? 'disabled' : '')
    + '</div>' + tags(Object.keys(active.languages ?? {})) + '</header>'
    + contextBanner + repoConsent(info) + reportStatus + errors + '<div class="repo-report">'
    + '<section class="report-activity"><header><h3>' + escape(t('repos.activity')) + '</h3><small>'
    + escape(rangeLabel(state.range)) + '</small></header><div class="report-counters">'
    + (counters ? tags(['Commits ' + counters.commits, 'PR ' + counters.pull_requests_created,
    '+' + counters.additions, '−' + counters.deletions]) : '')
    + btn(escape(copy('Tải hoạt động', 'Load activity')), 'repo-activity', 'secondary small', data.busy.has('activity') ? 'disabled' : '') + '</div></section>'
    + (report ? highlightsCard + tabs + '<div id="repo-details">' + reportContent(report, info, data.reportTab) + '</div>' + nextStepsSection
      : blank(t('repos.noReport'), t('repos.noReportCopy'), btn(icon('pulse') + escape(copy('Bắt đầu phân tích repo ngay', 'Start analyzing this repository')), 'analyze', 'primary', job || busy ? 'disabled' : '')))
    + '</div></article></div>';
}

const statusLabel = status => ({
  completed: copy('Đã hoàn thành', 'Completed'), in_progress: copy('Đang thực hiện', 'In progress'), pending: copy('Chưa bắt đầu', 'Pending')
})[status] ?? status;

export function liveRoadmap(data) {
  const { milestones, done, next, goal } = progressOverview(data);
  const selected = milestones.find(m => m.id === data.milestone) ?? milestones[0];
  const item = data.road?.milestones.find(m => m.skill === selected?.external_key);
  const picker = field(t('road.goal'), '<select id="road-goal">' + [
    ['backend', 'Backend'], ['frontend', 'Frontend'], ['fullstack', 'Full-stack'], ['devops', 'DevOps']
  ].map(([key, label]) => option(key, label, data.goal)).join('') + '</select>');
  const map = milestones.map(milestone => '<button type="button" class="node" data-act="milestone"' + attr('id', milestone.id)
    + attr('state', milestone.status === 'completed' ? 'done' : 'ready') + ' aria-pressed="' + (milestone === selected) + '">'
    + '<span class="map-icon">' + icon(milestone.status === 'completed' ? 'check' : 'branch') + '</span><strong>'
    + escape(milestone.title) + '</strong><small>' + escape(statusLabel(milestone.status)) + '</small></button>').join('');
  const history = '<details class="panel road-history"' + (data.history.length ? ' open' : '') + '><summary>' + escape(t('road.history')) + '</summary>'
    + namedButton(copy('Tải lịch sử', 'Load history'), 'road-history', 'quiet small') + '<ul class="audit-list">'
    + data.history.map(record => '<li><time>' + escape(formattedDate(record.created_at)) + '</time><span>'
      + escape(statusLabel(record.old_status) + ' → ' + statusLabel(record.new_status)) + '</span></li>').join('') + '</ul></details>';
  const pending = data.tracking?.suggestions.filter(suggestion => suggestion.state === 'pending' && suggestion.milestone_id === selected?.id) ?? [];
  const detail = selected && item ? '<article class="panel road-detail" id="milestone-detail"><div class="detail-top">'
    + badge(statusLabel(selected.status), selected.status === 'completed' ? 'green' : 'blue') + '</div>'
    + '<h2>' + escape(selected.title) + '</h2>' + paragraph(item.objective)
    + '<div class="milestone-proof"><span class="feature-icon">' + icon('award') + '</span><div><h3>'
    + escape(t('road.proof')) + '</h3>' + paragraph(item.metric) + refs(item.evidence) + '</div></div>'
    + '<div class="action-row">' + ['pending', 'in_progress', 'completed'].filter(status => status !== selected.status)
      .map(status => btn(escape(statusLabel(status)), 'road-status', 'secondary small', attr('id', selected.id) + attr('status', status))).join('')
    + namedButton(t('action.askMentor'), 'ask-step', 'secondary small') + '</div>'
    + pending.map(suggestion => '<div class="notice">' + paragraph(suggestion.explanation)
      + ['apply', 'reject'].map(decision => btn(escape(decision === 'apply' ? copy('Áp dụng', 'Apply') : copy('Bỏ qua', 'Dismiss')),
        'road-suggestion', 'secondary small', attr('id', suggestion.id) + attr('decision', decision))).join('') + '</div>').join('') + '</article>' : '';
  return heading(t('road.heading'), t('road.intro'), picker) + feedback(data, 'road')
    + '<div class="road-banner"><section class="panel road-next"><div><p class="eyebrow">' + escape(t('road.next')) + '</p><h2>'
    + escape(next?.title ?? (data.road ? t('road.finished') : copy('Chưa có lộ trình', 'No roadmap yet'))) + '</h2>'
    + (goal ? paragraph(goal.objective) : '') + '</div>'
    + btn(escape(copy('Tạo lộ trình', 'Generate roadmap')), 'road-create', 'primary', data.busy.has('road') ? 'disabled' : '') + '</section>'
    + '<section class="panel road-progress"><div><p class="eyebrow">' + escape(t('road.progress')) + '</p><strong>' + done.length + '<span> / ' + milestones.length
    + '</span></strong><p>' + escape(t('road.progressCount', { done: done.length, total: milestones.length })) + '</p></div>'
    + '<div class="milestone-pips" aria-hidden="true">' + milestones.map(m => '<i' + attr('state', m.status === 'completed' ? 'done' : 'ready') + '></i>').join('') + '</div></section></div>'
    + (data.road ? '<section class="road-update"><div>' + icon('pulse') + escape(copy('Cập nhật từ kết quả phân tích GitHub', 'Recheck GitHub evidence')) + '</div>'
      + btn(escape(copy('Đánh giá lại', 'Re-evaluate')), 'road-draft', 'secondary small', data.busy.has('road') ? 'disabled' : '') + '</section>' : '')
    + '<div class="road-layout"><section class="panel map-panel">' + panelHead(t('road.map'), copy('Chọn mốc để xem mục tiêu và bằng chứng.', 'Select a milestone to see its goal and evidence.'))
    + '<div class="map-legend">' + ['done', 'ready'].map(mode => '<span data-state="' + mode + '"><i></i>' + escape(t('road.' + mode)) + '</span>').join('') + '</div>'
    + (map ? '<div class="road-map"><canvas aria-hidden="true"></canvas>' + map + '</div>' : muted(copy('Chưa có cột mốc để hiển thị.', 'No milestones to display.')))
    + '</section>' + detail + (selected ? '<div class="road-records stack">'
      + (done.length ? '<section class="panel achievements">' + panelHead(t('road.trophies')) + '<div class="award-list">'
        + done.map(m => '<button class="award-card" type="button" data-act="milestone"' + attr('id', m.id) + '><span class="award-icon">'
          + icon('award') + '</span><span><strong>' + escape(m.title) + '</strong></span>' + icon('arrow') + '</button>').join('')
        + '</div></section>' : '') + history + '</div>' : '') + '</div>';
}

export function liveJobs(state, data) {
  const entries = data.jobResults?.jobs ?? [];
  const rows = entries.map(entry => {
    const url = safeLink(entry.url);
    return '<div class="job-row"><h3>' + escape(entry.title) + '</h3><p class="subtle">'
      + escape([entry.company, entry.location, entry.source].filter(Boolean).join(' · ')) + '</p><div class="action-row">'
      + (url ? '<a class="button secondary small" href="' + escape(url) + '" target="_blank" rel="noopener noreferrer">' + escape(copy('Xem tin gốc', 'Open listing')) + '</a>' : '')
      + (entry.description_preview ? namedButton(copy('Dùng mô tả công việc', 'Use job description'), 'use-live-job', 'quiet small', entry.id) : '')
      + '</div></div>';
  }).join('');
  const report = data.jobMatch;
  const comparison = report?.skills.map(item => '<li><div><strong>' + escape(item.skill_key) + '</strong>'
    + badge(t('jobs.' + ({ matched: 'has', partial: 'partial', unknown: 'missing' })[item.status]), item.status === 'matched' ? 'green' : '')
    + '</div>' + paragraph(item.reason) + refs(item.evidence) + '</li>').join('') ?? '';
  return heading(t('nav.jobs'), copy('Tìm tin tuyển dụng hoặc dán JD để đối chiếu với hồ sơ.', 'Find a job listing or paste a job description to match it against your profile.')) + feedback(data, 'jobs')
    + '<div class="columns"><div class="stack"><article class="panel">' + panelHead(t('jobs.search'), 'Remotive')
    + '<form id="job-search" class="field-row">' + field(t('jobs.keyword'), '<input name="query" value="' + escape(data.jobQuery ?? '')
      + '" maxlength="200" placeholder="Python, FastAPI, TypeScript" required>')
    + '<button class="button secondary" type="submit"' + (data.busy.has('jobs') ? ' disabled' : '') + '>' + escape(t('jobs.searchAction')) + '</button></form>'
    + '<div class="rows view-rows">' + (data.jobResults?.warnings ?? []).map(muted).join('')
    + (rows || (data.jobResults ? muted(t('jobs.noMatch')) : '')) + '</div></article>'
    + '<article class="panel">' + panelHead(t('jobs.paste')) + '<form id="jd-form" class="stack">'
    + field(t('jobs.description'), '<textarea name="jd" rows="4" maxlength="50000" placeholder="' + escape(t('jobs.placeholder'))
      + '">' + escape(data.jobText ?? '') + '</textarea>')
    + field(copy('Hoặc URL tuyển dụng', 'Or listing URL'), '<input name="jd-url" type="url" value="' + escape(data.jobURL ?? '') + '">')
    + '<button class="button primary" type="submit"' + (data.busy.has('jobs') ? ' disabled' : '') + '>' + escape(t('jobs.analyze')) + '</button></form></article></div>'
    + '<article class="panel">' + panelHead(t('jobs.compare'), scopeLabel(state.scope))
    + (report ? (report.required_matched_percent == null ? muted(t('profile.noEvidence'))
      : badge(number(report.required_matched_percent) + '%', 'green')) + muted(report.disclaimer)
      + '<ul class="job-evidence-list">' + comparison + '</ul>' + (report.limitations ?? []).map(muted).join('')
      : blank(t('jobs.none'), t('jobs.noneCopy'))) + '</article></div>';
}

export function liveCV(state, runtime, data) {
  const { cv } = data;
  const doc = data.document;
  const draft = runtime.cvDraft;
  const busy = data.busy.has('cv');
  const select = (label, id, options) => field(label, '<select id="' + id + '"><option value="">'
    + escape(copy('Chọn…', 'Select…')) + '</option>' + options + '</select>');
  const ats = data.ats;
  const references = data.references;
  const lookup = '<details class="panel stack"><summary>' + escape(copy('Mẫu CV tham khảo', 'CV references')) + '</summary>'
    + '<form class="field-row" id="cv-references-form">'
    + field(copy('Công ty', 'Company'), '<input name="company" required maxlength="100" value="' + escape(data.referencesQuery?.company) + '">')
    + field(copy('Vị trí', 'Role'), '<input name="role" required maxlength="100" value="' + escape(data.referencesQuery?.role) + '">')
    + '<button class="button secondary" type="submit">' + escape(copy('Tìm mẫu', 'Find references')) + '</button></form>'
    + (references ? muted(references.disclaimer) + '<ul class="audit-list">'
      + references.references.map(item => {
        const url = safeLink(item.source_url);
        return '<li><span>' + (url ? '<a href="' + escape(url) + '" target="_blank" rel="noopener noreferrer">' + escape(item.title) + '</a>' : escape(item.title))
          + '</span><small>' + escape(item.license) + '</small></li>';
      }).join('') + '</ul>' : '') + '</details>';
  return heading(t('nav.cv'), t('cv.intro')) + feedback(data, 'cv')
    + '<div class="columns"><article class="panel cv-editor">' + panelHead(t('cv.draft'))
    + '<fieldset class="cv-controls"' + (busy ? ' disabled' : '') + '><form id="cv-form" class="cv-controls">'
    + field(t('cv.name'), '<input name="name" maxlength="120" value="' + escape(draft.name) + '">')
    + field(t('cv.role'), '<input name="role" maxlength="70" value="' + escape(draft.role) + '">')
    + field(t('cv.content'), '<textarea name="body" rows="8" maxlength="20000" required>' + escape(draft.body) + '</textarea>')
    + field(t('cv.import'), '<input id="cv-upload" type="file" accept=".pdf,.docx">')
    + '<div class="action-row"><button class="button primary" type="submit">' + escape(t('cv.save')) + '</button>'
    + namedButton(copy('Tạo CV bằng AI', 'Generate with AI'), 'cv-generate', 'secondary small') + '</div></form>'
    + select(copy('CV đã tải lên', 'Uploaded CVs'), 'live-cv-picker', data.cvList.map(item => option(item.id, 'CV #' + item.id, item.id === cv?.id ? item.id : undefined)).join(''))
    + select(copy('CV Studio', 'CV Studio'), 'live-document-picker', data.documentList.map(item => option(item.document_id, item.title, doc?.document_id)).join(''))
    + (doc ? select(copy('Phiên bản', 'Version'), 'live-version-picker', data.versions.map(item => option(item.number, '#' + item.number, doc.number)).join('')) : '')
    + '</fieldset></article><article class="panel cv-preview">' + panelHead(t('cv.preview'), t('cv.previewCopy'))
    + '<div class="tabs" role="group">' + ['plain', 'tech'].map(key => btn(escape(t('cv.' + key)), 'cv-template', '',
      attr('id', key) + ' aria-pressed="' + (state.template === key) + '"')).join('') + '</div>'
    + '<div class="cv-paper" data-template="' + escape(state.template) + '"><h2 id="cv-name">' + escape(draft.name)
    + '</h2><p id="cv-role">' + escape(draft.role) + '</p><div class="cv-body" id="cv-body">' + escape(draft.body || t('cv.empty')) + '</div></div>'
    + '<div class="action-row cv-exports">' + (doc ? namedButton('PDF', 'cv-export', 'secondary small', 'pdf') + namedButton('DOCX', 'cv-export', 'secondary small', 'docx') : '')
    + namedButton(t('cv.print'), 'cv-print', 'secondary small') + '</div></article></div>'
    + '<article class="panel cv-feedback view-rows">' + panelHead(t('cv.ats'), t('cv.atsCopy'))
    + field(copy('Mô tả công việc (tùy chọn)', 'Job description (optional)'), '<textarea name="ats-jd" maxlength="20000" rows="4">'
      + escape(data.atsJD ?? '') + '</textarea>')
    + btn(escape(t('cv.check')), 'cv-check', 'secondary small', !cv || busy ? 'disabled' : '')
    + '<div id="ats-result" aria-live="polite">' + (ats ? muted(ats.disclaimer) + details([
      [copy('Điểm cấu trúc văn bản', 'Text structure'), number(ats.readability_score) + '/100'],
      [copy('Độ phủ từ khóa', 'Keyword coverage'), ats.keyword_coverage == null ? '—' : number(ats.keyword_coverage) + '%']])
      + '<ul class="cv-checks">' + ats.suggestions.map(suggestion => '<li>' + escape(suggestion.message) + '</li>').join('') + '</ul>' : '') + '</div></article>' + lookup;
}

function auditRows(items) {
  return items.length ? '<ul class="audit-list">' + items.map(item => '<li><time>' + escape(formattedDate(item.created_at))
    + '</time><span>' + escape([item.feature, item.source, item.status].filter(Boolean).join(' · ')) + '</span></li>').join('') + '</ul>' : muted(t('data.noLogs'));
}

export function liveData(state, data) {
  const share = data.shared;
  return heading(t('data.heading'), t('data.intro')) + feedback(data, 'data')
    + '<div class="columns"><article class="panel stack">' + panelHead(t('data.connection'))
    + details([[t('data.github'), badge(t('data.' + (state.access === 'none' ? 'disconnected' : state.access)))]])
    + muted(copy('Quyền xem mã riêng tư và quyền AI được xác nhận riêng trên repository đã chọn.', 'Manage private analysis and external AI consent on the relevant repository.'))
    + '<div class="action-row">' + (state.access === 'none'
      ? namedButton(t('repos.connect'), 'reconnect', 'secondary small')
      : namedButton(t('privacy.disconnect'), 'disconnect', 'quiet small') + link(escape(t('action.openRepo')), 'repos', 'secondary small')) + '</div></article>'
    + '<article class="panel stack">' + panelHead(t('data.share')) + muted(t('data.shareIntro'))
    + namedButton(copy('Tạo liên kết', 'Create link'), 'share-start', 'secondary small')
    + (share ? field(t('data.shareLink'), '<input id="share-link" value="' + escape(share.url) + '" readonly>')
      + '<div class="action-row"><a class="button secondary small" href="' + escape(share.url) + '" target="_blank" rel="noopener noreferrer">'
      + escape(t('data.shareOpen')) + '</a>' + namedButton(t('data.shareCopy'), 'copy-share', 'secondary small') + '</div>' : '')
    + '<ul class="audit-list">' + data.shares.map(item => '<li><span>#' + escape(item.id) + ' · '
      + escape(item.allowed_fields.map(key => key === 'full_name' ? copy('Tên hiển thị', 'Display name') : copy('Repository công khai', 'Public repositories')).join(', '))
      + '</span>' + namedButton(t('data.shareRevoke'), 'revoke-share', 'danger small', item.id) + '</li>').join('') + '</ul></article></div>'
    + '<article class="panel view-rows">' + panelHead(t('data.audit')) + auditRows(data.audit) + '</article>';
}

export function liveStatus(data) {
  const health = data.health;
  const checks = health?.checks ?? {};
  return heading(t('nav.status'), copy('Trạng thái lấy trực tiếp từ hệ thống.', 'Status from the running system.'))
    + feedback(data, 'status') + '<div class="columns"><article class="panel stack">' + panelHead(t('status.environment'))
    + details([[t('status.frontend'), badge(t('status.open'), 'green')], ['FastAPI', badge(fallback(health?.status), health?.httpStatus === 200 ? 'green' : 'amber')],
    ['PostgreSQL', escape(fallback(checks.database))], ['Redis', escape(fallback(checks.redis))]])
    + namedButton(copy('Kiểm tra lại', 'Refresh status'), 'status-refresh', 'secondary small') + '</article><article class="panel">'
    + panelHead(copy('Đồng bộ GitHub', 'GitHub sync')) + muted(data.sync?.message ?? data.sync?.status ?? copy('Chưa có thông tin đồng bộ.', 'No sync information yet.')) + '</article></div>';
}

export function livePublic(profile) {
  if (profile === undefined) return '<main class="share-view">' + muted(copy('Đang tải hồ sơ…', 'Loading profile…')) + '</main>';
  const back = '<a class="button secondary" href="#about">' + escape(t('action.back')) + '</a>';
  return '<main class="share-view"><header class="share-top">' + brand() + languagePicker() + '</header>' + heading(t('data.profile'), t('data.profileCopy'), back)
    + (profile ? '<article class="panel">' + (profile.full_name ? '<h2>' + escape(profile.full_name) + '</h2>' : '')
      + '<ul class="audit-list">' + (profile.public_repositories ?? []).map(repo => {
        const url = safeLink(repo.url);
        const label = escape(repo.name);
        return '<li>' + (url ? '<a href="' + escape(url) + '" target="_blank" rel="noopener noreferrer">' + label + '</a>' : label)
          + '<span>' + escape(repo.language ?? '') + '</span></li>';
      }).join('') + '</ul></article>' : '<article class="panel">' + blank(t('data.unavailable'), t('data.unavailableCopy')) + '</article>') + '</main>';
}
