import { dateLabel, getLanguage, rangeLabel, scopeLabel, t } from './i18n.js';
import { attr, badge, blank, brand, btn, details, escape, field, filterControls, formatSkillName, heading, icon, labelAttr, languagePicker, link, option, panelHead, progress, tags } from './ui.js';
import { radarView } from './radar.js';
import { safeLink } from './live-api.js';
import {currentEvaluationSuggestions} from './reevaluation.js';
import {submittedEvidenceLinks} from './roadmap-evidence.js';
import {numericScore, verifiedSkillScore} from './score-presentation.js';
import {githubRadarMetrics} from './dashboard-github-metrics.js';

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
      : data.busy.has(key) ? '<p class="ita-loading-status" role="status"><span class="ita-loading-spinner" aria-hidden="true"></span><span>' + escape(copy('Đang tải…', 'Loading…')) + '</span></p>' : '').join('');
}

function formatEvidenceItem(item, data) {
  const sha = item.commit_sha || (typeof item.evidence_id === 'string' && item.evidence_id.startsWith('verification-commit:') ? item.evidence_id.split(':').pop() : '');
  const repoName = item.repository_full_name || item.repository_name || (data?.repos?.find(r => r.id === item.repository_id)?.full_name) || (data?.repos?.find(r => r.id === item.repository_id)?.name) || '';
  const commitUrl = item.commit_url || (repoName && sha ? ('https://github.com/' + repoName + '/commit/' + sha) : '');

  const repoBadge = repoName
    ? '<span class="evidence-repo" title="' + escape(copy('Kho lưu trữ GitHub', 'GitHub repository')) + '">' + icon('branch') + ' <strong>' + escape(repoName) + '</strong></span>'
    : '';

  const fileBadge = item.file_path
    ? '<span class="evidence-file" title="' + escape(copy('File mã nguồn', 'Source file')) + '">' + icon('file') + ' ' + escape(item.file_path) + '</span>'
    : '';

  let commitBadge = '';
  if (sha) {
    const shortSha = sha.slice(0, 7);
    if (commitUrl) {
      commitBadge = '<a href="' + escape(commitUrl) + '" target="_blank" rel="noopener noreferrer" class="evidence-commit-link" title="'
        + escape(copy('Mở commit ' + sha + ' trên GitHub', 'Open commit ' + sha + ' on GitHub')) + '">'
        + icon('git-commit') + ' ' + escape(copy('Commit', 'Commit')) + ': <code>' + escape(shortSha) + '</code> <span class="ext-icon" aria-hidden="true">↗</span></a>';
    } else {
      commitBadge = '<span class="evidence-commit-label">' + icon('git-commit') + ' ' + escape(copy('Commit', 'Commit')) + ': <code>' + escape(shortSha) + '</code></span>';
    }
  }

  const prNumber = Number(item.pr_number);
  const safeRepo = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repoName);
  const prUrl = safeRepo && Number.isSafeInteger(prNumber) && prNumber > 0
    ? 'https://github.com/' + repoName + '/pull/' + prNumber : '';
  const prBadge = prUrl
    ? '<a href="' + escape(prUrl) + '" target="_blank" rel="noopener noreferrer" class="evidence-commit-link">'
      + icon('branch') + ' PR #' + prNumber + ' <span class="ext-icon" aria-hidden="true">↗</span></a>'
    : '';

  const label = item.label || item.target_identifier || item.evidence_id || '';
  const generalBadge = (!repoBadge && !fileBadge && !commitBadge && label)
    ? '<span class="evidence-general">' + icon('check') + ' ' + escape(label) + '</span>'
    : '';

  const infoRow = [repoBadge, fileBadge].filter(Boolean).join(' · ');

  return '<li class="evidence-item">'
    + '<div class="evidence-info">' + (infoRow || generalBadge || '<span class="evidence-general">' + icon('check') + ' ' + escape(copy('Minh chứng mã nguồn GitHub', 'GitHub source evidence')) + '</span>') + '</div>'
    + (commitBadge || prBadge ? '<div class="evidence-action">' + (commitBadge || prBadge) + '</div>' : '')
    + '</li>';
}

function refs(items = [], data = null) {
  return items.length ? '<ul class="audit-list evidence-list">' + items.slice(0, 20).map(item => formatEvidenceItem(item, data)).join('') + '</ul>' : '';
}

export function orderedTrackingMilestones(data) {
  const tracking = Array.isArray(data?.tracking?.milestones) ? data.tracking.milestones : [];
  const stored = Array.isArray(data?.road?.milestones) ? data.road.milestones : [];
  const positions = new Map();
  stored.forEach((item, index) => {
    const key = String(item?.skill ?? '').trim().toLowerCase();
    if (key && !positions.has(key)) positions.set(key, index);
  });
  return tracking.slice().sort((a, b) => {
    const indexA = positions.get(String(a?.external_key ?? '').trim().toLowerCase()) ?? stored.length;
    const indexB = positions.get(String(b?.external_key ?? '').trim().toLowerCase()) ?? stored.length;
    return indexA - indexB || (Number(a?.id) || 0) - (Number(b?.id) || 0);
  });
}

function progressOverview(data) {
  const milestones = orderedTrackingMilestones(data);
  const done = milestones.filter(milestone => milestone.status === 'completed');
  const next = milestones.find(milestone => milestone.status !== 'completed');
  const goal = next && data.road?.milestones?.find(item => item?.skill === next.external_key);
  return { milestones, done, next, goal };
}

function scorePill(value) {
  return value === null
    ? '<strong class="evidence-score-pill is-unavailable" title="' + escape(copy('Chưa đủ bằng chứng để chấm điểm', 'Insufficient evidence to score')) + '">—<span>' + escape(copy('Chưa chấm', 'Not scored')) + '</span></strong>'
    : '<strong class="evidence-score-pill">' + number(value) + '<span>/100</span></strong>';
}

function scoreStatusLabel(status) {
  if (status === 'Scored' || status === 'SCORED') return copy('Đã chấm điểm', 'Scored');
  if (status === 'Insufficient' || status === 'INSUFFICIENT') return copy('Chưa đủ bằng chứng', 'Insufficient evidence');
  if (status === 'Unknown' || status === 'UNKNOWN') return copy('Chưa xác định', 'Unknown');
  if (status === 'Conflicting' || status === 'CONFLICTING') return copy('Bằng chứng mâu thuẫn', 'Conflicting evidence');
  return status || '—';
}

function scoreRow(title, value, action, id, active) {
  return '<button type="button" class="score-row" data-act="' + action + '"' + attr('id', id)
    + ' aria-pressed="' + active + '"><span>' + escape(title) + '</span><b>' + number(value)
    + (value == null ? '' : '<small>/100</small>') + '</b>'
    + (value == null ? '' : '<span class="score-track" aria-hidden="true">' + progress(value, title) + '</span>') + '</button>';
}

function dashboardScores(state, runtime, data, analyzedCount = 1) {
  const tabs = [['tech', t('profile.tech')], ['roles', t('profile.roles')], ['sources', t('profile.sources')]];
  const tabButtons = '<div class="tabs" role="group"' + labelAttr(t('profile.scoreType')) + '>'
    + tabs.map(([key, label]) => btn(escape(label), 'score-tab', '', 'id="' + key + '" ' + attr('id', key) + ' aria-pressed="' + (runtime.scoreTab === key) + '"')).join('') + '</div>';
  let scores = '';
  let evidence = '';

  const emptySkillState = '<div class="pixel-empty-card">'
    + '<div class="empty-pixel-icon">' + icon('search') + '</div>'
    + '<h3>' + copy('Chưa có điểm kỹ năng nào được tính toán', 'No skill scores calculated yet') + '</h3>'
    + '<p class="empty-reason">' + (analyzedCount ? copy(
      'Đã tải báo cáo GitHub nhưng chưa có bản ghi điểm kỹ năng trong phạm vi này. Kiểm tra quá trình xác minh đóng góp và cảnh báo tải dữ liệu.',
      'GitHub reports were loaded but no skill scores are available in this scope. Check contribution verification and data-loading warnings.'
    ) : copy(
      'Chưa có báo cáo GitHub trong phạm vi <strong>' + scopeLabel(state.scope) + '</strong> và kỳ <strong>' + rangeLabel(state.range) + '</strong>.',
      'No GitHub reports were found in scope <strong>' + scopeLabel(state.scope) + '</strong> and window <strong>' + rangeLabel(state.range) + '</strong>.'
    )) + '</p>'
    + '<div class="empty-steps-guide">'
    + '<div class="guide-step"><span class="step-num">1</span><span>' + copy('Chuyển sang trang Phân tích GitHub', 'Go to GitHub Analysis') + '</span></div>'
    + '<div class="guide-step"><span class="step-num">2</span><span>' + copy('Chọn repository của bạn và bấm Phân tích', 'Select your repository and click Analyze') + '</span></div>'
    + '<div class="guide-step"><span class="step-num">3</span><span>' + copy('Quay lại Dashboard để xem điểm Radar & Kỹ năng', 'Return to Dashboard to view Radar & Skill scores') + '</span></div>'
    + '</div>'
    + link(icon('pulse') + ' ' + copy('Đến trang Phân tích GitHub để chọn repo ngay →', 'Go to GitHub Analysis to pick a repo now →'), 'repos', 'primary')
    + '</div>';

  if (runtime.scoreTab === 'tech') {
    const key = item => item.repo.id + ':' + item.kind + ':' + item.technology;
    const selected = data.scores.find(item => key(item) === data.scoreKey) ?? data.scores[0];
    scores = data.scores.map(item => {
      const isSelected = selected === item;
      return scoreRow(item.technology + ' · ' + (item.repo.full_name || item.repo.name), verifiedSkillScore(item.score, item.status), 'score', key(item), isSelected);
    }).join('');

    if (selected) {
      const selectedValue = verifiedSkillScore(selected.score, selected.status);
      const confidence = selected.breakdown?.find(item => item.criterion === 'confidence')?.normalized_value;
      const confPct = Number.isFinite(confidence) ? Math.round(confidence * 100) : '—';
      evidence = '<div class="evidence-header-block"><div><h3>' + escape(selected.technology) + '</h3>'
        + '<span class="tag-badge ' + (selectedValue === null ? 'yellow' : 'green') + '">' + (selectedValue === null
          ? copy('Chưa đủ bằng chứng xác minh', 'Insufficient verified evidence')
          : copy('Đủ bằng chứng xác minh', 'Verified evidence')) + '</span></div>'
        + scorePill(selectedValue) + '</div>'
        + paragraph(selected.explanation)
        + details([
          [copy('Repository nguồn', 'Source Repository'), escape(selected.repo.full_name || selected.repo.name)],
          [copy('Độ tin cậy', 'Confidence'), confPct + (confPct === '—' ? '' : '/100')],
          [copy('Trạng thái xác minh', 'Verification Status'), escape(scoreStatusLabel(selected.status))]
        ])
        + '<div class="evidence-action-row" style="margin-top:14px">'
        + btn(icon('file') + ' ' + copy('Xem mã nguồn & bằng chứng tại repo ', 'Inspect code & evidence in ') + escape(selected.repo.full_name || selected.repo.name) + ' ↗',
          'evidence', 'primary small', attr('id', selected.repo.id))
        + '</div>';
    }
  } else if (runtime.scoreTab === 'roles') {
    const selection = data.roles.find(item => item.key === data.roleKey) ?? data.roles[0];
    const selected = selection?.score;
    scores = data.roles.map(item => scoreRow(item.name, numericScore(item.score?.role_score), 'role-score', item.key, selection === item)).join('');
    if (selected) {
      const selectedValue = selected.status === 'SCORED' ? numericScore(selected.role_score) : null;
      const coverage = Number.isFinite(selected.coverage)
        ? Math.round(selected.coverage * 100) + '%' : '—';
      const confidence = Number.isFinite(selected.confidence)
        ? number(selected.confidence) + '/100' : '—';
      const criteria = Array.isArray(selected.criteria) ? selected.criteria : [];
      const blockers = criteria.filter(item => item.status !== 'SCORED');
      const refsUsed = Array.isArray(selected.evidence_refs) ? selected.evidence_refs : [];
      const blockersList = blockers.length
        ? '<div class="role-score-audit"><h4>' + copy('Tiêu chí chưa đạt hoặc chưa xác định', 'Unmet or unknown criteria') + '</h4>'
          + '<ul class="audit-list">' + blockers.map(item => '<li><strong>' + escape(item.name || item.key) + '</strong>'
            + (item.required ? ' <span class="tag-badge yellow">' + copy('Bắt buộc', 'Required') + '</span>' : '')
            + muted(item.rationale || scoreStatusLabel(item.status)) + '</li>').join('') + '</ul></div>'
        : '';
      evidence = '<div class="evidence-header-block"><div><h3>' + escape(selected.role_name || selection.name) + '</h3>'
        + '<span class="tag-badge ' + (selectedValue === null ? 'yellow' : 'green') + '">' + (selectedValue === null
          ? escape(scoreStatusLabel(selected.status))
          : copy('Đã chấm điểm vai trò', 'Role score available')) + '</span></div>'
        + scorePill(selectedValue) + '</div>'
        + paragraph(selected.rationale)
        + details([
          [copy('Độ phủ tiêu chí', 'Criterion coverage'), coverage],
          [copy('Độ tin cậy bằng chứng', 'Evidence confidence'), confidence],
          [copy('Trạng thái', 'Status'), escape(scoreStatusLabel(selected.status))],
          [copy('Rubric vai trò', 'Role rubric'), escape(selected.rubric_version ?? '—')]
        ])
        + blockersList
        + (selected.limitations ?? []).map(item => muted(item.message ?? item.label ?? item.code)).join('')
        + '<h4>' + copy('Bằng chứng được xem xét', 'Evidence considered') + ': ' + refsUsed.length + '</h4>'
        + (refs(refsUsed, data) || muted(copy('Không có bằng chứng được dùng để chấm vai trò.', 'No evidence was used to score this role.')))
        + (refsUsed.length > 20 ? muted(copy('Chỉ hiển thị 20 bằng chứng đầu tiên.', 'Showing the first 20 evidence references.')) : '')
        + '<div class="evidence-action-row" style="margin-top:12px">'
        + [...new Set(refsUsed.map(ref => ref.repository_id).filter(Boolean))]
          .map(id => namedButton(copy('Mở repo #', 'Open repo #') + id + ' ↗', 'evidence', 'secondary small', id)).join(' ')
        + '</div>';
    } else if (selection?.limitations?.length) {
      evidence = selection.limitations.map(item => muted(item.message ?? item.code)).join('');
    }
  } else {
    scores = '<div class="project-skills"><h3>' + escape(t('profile.verifiedHeading')) + '</h3>'
      + tags([...new Set(data.scores.filter(item => verifiedSkillScore(item.score, item.status) !== null &&
        item.breakdown?.some(part => Array.isArray(part.evidence_ids) &&
          part.evidence_ids.some(id => Number.isSafeInteger(id) && id > 0)))
        .map(item => item.technology))], 'green')
      + '<h3>' + escape(t('profile.supplementary')) + '</h3>' + tags(data.skills.map(item => item.skill_name), 'blue') + '</div>';
    evidence = '<h3>' + escape(t('profile.self')) + '</h3><form id="skill-form" class="skill-form">'
      + field(t('profile.skill'), '<input name="skill" maxlength="120" required>')
      + field(t('road.optionalLink'), '<input type="url" name="evidence" maxlength="900" placeholder="https://">')
      + '<button class="button primary" type="submit">' + escape(t('action.add')) + '</button></form>'
      + '<ul class="claimed-skills">' + data.skills.map(skill => '<li><strong>' + escape(skill.skill_name)
        + '</strong>' + namedButton(t('action.remove'), 'remove-skill', 'quiet small', skill.id) + '</li>').join('') + '</ul>';
  }

  const scoresContent = scores || emptySkillState;
  const evidenceContent = evidence || (data.scores.length === 0 ? '' : blank(t('profile.noEvidence'), t('profile.noEvidenceCopy'), link(escape(t('action.openRepo')), 'repos', 'secondary small')));

  return '<div class="columns dashboard-columns"><section class="panel scores-panel">'
    + panelHead(t('profile.skills'), copy('Điểm từ ' + analyzedCount + ' repository GitHub đã phân tích trong phạm vi đã chọn.', 'Scores from ' + analyzedCount + ' analyzed GitHub repositories in the selected scope.'))
    + tabButtons + '<div class="rows">' + scoresContent + '</div></section>'
    + '<section class="panel evidence-card">' + panelHead(t(runtime.scoreTab === 'sources' ? 'profile.origins' : 'profile.evidence'))
    + (evidenceContent || blank(t('profile.noEvidence'), t('profile.noEvidenceCopy'), link(escape(t('action.openRepo')), 'repos', 'secondary small')))
    + '</section></div>';
}

function getLiveRadar(state, data) {
  const availableRepos = data.dashboardRepos ?? data.repos;
  const analyzedRepos = availableRepos.filter(repo =>
    Boolean(data.repoData?.[repo.id]?.report?.id)
  );
  const analyzedIds = new Set(analyzedRepos.map(repo => repo.id));
  const activeRepo = data.repos.find(repo => String(repo.id) === String(state.repo)) ?? data.repos[0];
  const activeRepoAnalyzed = activeRepo ? analyzedIds.has(activeRepo.id) : false;
  const rawMetrics = githubRadarMetrics({
    roles: data.roles,
    scores: data.scores,
    roleKey: data.roleKey
  });
  const hasVerifiedScores = rawMetrics.some(item => item.score !== null);
  const metrics = analyzedRepos.length || hasVerifiedScores
    ? rawMetrics.map(item => ({...item, label: t('metric.' + item.key)}))
    : [];

  // Snapshot comparisons are unavailable unless the backend supplies a real
  // historical score with matching rubric and scope. Never invent deltas.
  const comparison = {};
  const metricDetails = metrics.map(item => {
    const source = item.evidence;
    const repo = source?.repository_id != null
      ? availableRepos.find(repo => repo.id === source.repository_id) : null;
    const sourceDescription = source ? source.origin === 'role'
      ? copy('Tiêu chí đã chấm từ rubric vai trò: ', 'Scored role criterion: ') + source.source
      : copy('Điểm kỹ năng đã chấm từ GitHub: ', 'Scored GitHub skill: ') + source.source
      : copy('Chưa có điểm được xác minh cho nhóm này. Đây không phải 0 điểm.',
        'No verified score for this category. This does not mean zero.');
    return '<section id="radar-detail-' + item.key + '" class="radar-insight"'
      + ' aria-labelledby="radar-label-' + item.key + '" hidden>'
      + '<div class="radar-insight-head"><h3 id="radar-label-' + item.key + '">'
      + escape(item.label) + '</h3><b>'
      + (item.score === null ? '—' : number(item.score) + '<small>/100</small>') + '</b></div>'
      + '<p>' + escape(sourceDescription) + '</p>'
      + (source?.detail ? paragraph(source.detail) : '')
      + '<p class="subtle">' + escape(t('analysis.noComparison')) + '</p>'
      + (repo ? '<div class="radar-evidence-line"><div><strong>'
        + escape(repo.full_name || repo.name) + '</strong></div>'
        + btn(icon('file') + escape(t('radar.openEvidence')), 'evidence', 'secondary small',
          attr('id', repo.id)) + '</div>' : '')
      + '<div class="radar-next-actions">'
      + btn(icon('bot') + escape(t('radar.askMetric')), 'ask-metric', 'secondary small',
        attr('id', item.key)) + '</div></section>';
  }).join('');

  return {
    metrics, comparison, metricDetails, count: analyzedRepos.length,
    analyzedRepos, activeRepo, activeRepoAnalyzed
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
    + '<div><h2>' + copy('Điểm kỹ năng từ báo cáo GitHub', 'GitHub Evidence-backed Skill Scores') + '</h2>'
    + '<p class="subtle">' + copy('Tổng hợp bằng chứng năng lực từ tất cả repository đã phân tích trong hồ sơ.', 'Aggregated competency evidence across all analyzed repositories in your profile.') + '</p>'
    + '</div></div>'
    + '<div class="scope-banner-tags">'
    + '<span class="scope-tag">' + icon('repo') + ' ' + copy('Phạm vi: ', 'Scope: ') + escape(scopeLabel(state.scope)) + '</span>'
    + '<span class="scope-tag">' + icon('clock') + ' ' + copy('Kỳ phân tích: ', 'Window: ') + escape(rangeLabel(state.range)) + '</span>'
    + '<span class="scope-tag highlight">' + icon('check') + ' ' + copy('Tổng hợp từ ', 'Aggregated from ') + analyzedCount + copy(' repository đã phân tích', ' analyzed repositories') + '</span>'
    + '</div>'
    + '</div>'
    + repoStatusHtml
    + (data.dashboardPartial ? '<p class="notice yellow" role="status">'
      + copy('Một số repository chưa tải được; số liệu chỉ tính từ các báo cáo đã tải thành công.',
        'Some repositories could not be loaded; metrics include only successfully loaded reports.')
      + '</p>' : '')
    + (data.dashboardLoadErrors?.length ? '<p class="notice yellow" role="status">'
      + escape(copy('Có lỗi khi tải ', 'Failed to load '))
      + data.dashboardLoadErrors.length
      + copy(' nguồn dữ liệu. Không tự tạo số thay thế.',
        ' data sources. No substitute scores were generated.')
      + '</p>' : '')
    + '<div class="dashboard-scope-notice">'
    + '<span class="notice-icon">' + icon('info') + '</span>'
    + '<p>' + copy(
      'Radar chỉ hiển thị những điểm kỹ năng hoặc tiêu chí vai trò đã được chấm từ bằng chứng GitHub thực tế trong phạm vi ' + scopeLabel(state.scope) + ' (' + rangeLabel(state.range) + '). Trục chưa đủ dữ liệu sẽ hiển thị dấu —, không coi là 0 điểm. Các chỉ số kiểm thử, cộng tác và CI/CD chỉ có điểm khi backend có rubric và bằng chứng tương ứng. Chọn repository để mở báo cáo chi tiết tại trang <em>Phân tích GitHub</em>.',
      'The Radar displays only scored GitHub skills or role criteria for scope ' + scopeLabel(state.scope) + ' (' + rangeLabel(state.range) + '). Missing axes display —, not zero. Testing, collaboration, and CI/CD require their own verified rubric evidence. Select a repository to inspect its report under <em>GitHub Analysis</em>.'
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
    + escape(next ? displayMilestoneTitle(next.title, next.external_key) : (milestones.length ? t('road.finished') : copy('Chưa có lộ trình', 'No roadmap yet'))) + '</h2></div></div>'
    + (goal ? paragraph(displayObjective(goal.objective, next?.external_key)) : '') + link(escape(t('action.openRoadmap')) + icon('arrow'), 'roadmap', 'secondary small') + '</section>'
    + '<section class="panel dashboard-progress"><p class="eyebrow">' + escape(t('road.progress')) + '</p>'
    + '<div class="focus-progress"><strong>' + done.length + '<span> / ' + milestones.length + '</span></strong><small>'
    + escape(t('profile.milestonesDone')) + '</small>' + progress(milestones.length ? done.length / milestones.length * 100 : 0, t('road.progress')) + '</div>'
    + '<div class="dash-award"><span class="award-icon">' + icon('award') + '</span><div><p class="eyebrow">'
    + escape(t('profile.latestAchievement')) + '</p>' + paragraph(done.at(-1) ? displayMilestoneTitle(done.at(-1).title, done.at(-1).external_key) : t('profile.achievementsEmpty')) + '</div></div></section></div>'
    + radarView(radar.metrics, radar.count, scopeLabel(state.scope), rangeLabel(state.range), radar.comparison, radar.metricDetails)
    + dashboardScores(state, runtime, data, radar.count);
}

function reportContent(report, info, tab) {
  if (tab === 'ownership') {
    const v = info.verification;
    return (v ? details([
      ['Trạng thái xác minh', escape(v.verification_status)],
      ['Quyền sở hữu', escape(v.ownership_status)],
      ['Loại nguồn gốc', escape(v.provenance_type) + (v.is_fork ? ' (Fork từ ' + escape(v.parent_repo_name || 'gốc') + ')' : ' (Repository gốc)')],
      ['Commits đã xác minh', escape(v.verified_commits_count)],
      ['Commits chưa xác minh', escape(v.unverified_commits_count ?? 0)],
      ['PR đã xác minh', escape(v.verified_prs_count)],
      ['PR chưa xác minh', escape(v.unverified_prs_count ?? 0)],
      ['Dòng thêm (Additions)', '+' + escape(v.verified_additions ?? 0)],
      ['Dòng xóa (Deletions)', '−' + escape(v.verified_deletions ?? 0)],
      ['Cờ chống thổi phồng', v.anti_inflation_flag ? copy('Đã phát hiện bất thường', 'Inflation detected') : copy('Bình thường', 'Normal')],
      ['Độ tin cậy', escape(v.confidence ?? '—')]
    ]) + refs(v.evidence) : muted(copy('Chưa có kết quả xác minh.', 'No verification yet.')))
      + namedButton(copy('Xác minh đóng góp', 'Verify contributions'), 'repo-analyze-tab', 'secondary small', 'ownership');
  }
  if (tab === 'collab') {
    const c = info.collaboration;
    if (!c) {
      return muted(copy('Chưa có kết quả PR, Review và CI.', 'No PR, review or CI results yet.'))
        + namedButton(copy('Phân tích PR, Review và CI', 'Analyze PR, reviews and CI'), 'repo-analyze-tab', 'secondary small', 'collab');
    }
    const prDetails = details([
      ['Tổng PR phân tích', escape(c.total_prs_analyzed)],
      ['PR đã merge', escape(c.merged_prs_count)],
      ['PR đang mở', escape(c.open_prs_count)],
      ['PR đã đóng (chưa merge)', escape(c.closed_unmerged_prs_count)],
      ['PR do user tạo', escape(c.user_prs_count)],
      ['PR từ bên ngoài', escape(c.external_prs_count)]
    ]);
    const reviewDetails = details([
      ['Tổng review phân tích', escape(c.total_reviews_analyzed)],
      ['Review đã approve', escape(c.approved_reviews_count)],
      ['Review yêu cầu sửa đổi', escape(c.changes_requested_count)],
      ['Review đóng góp nhận xét', escape(c.commented_reviews_count)],
      ['Review bị bác bỏ', escape(c.dismissed_reviews_count)],
      ['Review do user thực hiện', escape(c.user_reviews_conducted_count)],
      ['Review user nhận được', escape(c.user_reviews_received_count)]
    ]);
    const ciDetails = details([
      ['Tổng kiểm tra CI', escape(c.total_checks_analyzed)],
      ['CI thành công', escape(c.successful_checks_count)],
      ['CI thất bại', escape(c.failed_checks_count)],
      ['CI đang chạy/chờ', escape(c.pending_checks_count)],
      ['CI trạng thái khác', escape(c.other_checks_count)],
      ['Chu kỳ giải quyết vấn đề', escape(c.problem_solving_sequences_count)]
    ]);
    const seqs = (c.problem_solving_sequences ?? []).map(s =>
      '<div class="observation-card"><strong>' + icon('pulse') + ' ' + escape(s.explanation) + '</strong>'
      + '<small>' + copy('Thời gian chu kỳ: ', 'Cycle duration: ') + (s.cycle_duration_seconds ? Math.round(s.cycle_duration_seconds / 60) + ' phút' : 'N/A') + '</small></div>'
    ).join('');
    const obs = (c.collaboration_observations ?? []).map(o =>
      '<div class="observation-card"><strong>' + icon('check') + ' ' + escape(o.title) + '</strong><p>' + escape(o.description) + '</p></div>'
    ).join('');
    return '<div class="collab-breakdown">'
      + '<h4>' + copy('Phân tích Pull Requests', 'Pull Request Metrics') + '</h4>' + prDetails
      + '<h4>' + copy('Phân tích Code Reviews', 'Code Review Metrics') + '</h4>' + reviewDetails
      + '<h4>' + copy('Phân tích CI Checks & Tự động hóa', 'CI Checks & Automation') + '</h4>' + ciDetails
      + (seqs ? '<h4>' + copy('Chuỗi giải quyết sự cố (Problem Solving)', 'Problem Solving Sequences') + '</h4>' + seqs : '')
      + (obs ? '<h4>' + copy('Quan sát cộng tác (Observations)', 'Collaboration Observations') + '</h4>' + obs : '')
      + (c.limitations ?? []).map(muted).join('')
      + '</div>'
      + refs(c.evidence)
      + namedButton(copy('Phân tích lại PR, Review và CI', 'Re-analyze PR, reviews and CI'), 'repo-analyze-tab', 'secondary small', 'collab');
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
    [copy('Tổng số tệp quét', 'Total files in tree'), escape(report.structure?.total_files ?? '—')],
    [copy('Tệp đã kiểm tra', 'Inspected files'), escape(report.structure?.inspected_files ?? '—')],
    [copy('Tệp bỏ qua (vendor/binary)', 'Ignored files'), escape(report.structure?.ignored_files ?? '—')],
    [copy('Bằng chứng xác minh', 'Evidence records'), escape(report.evidence_count ?? (info.evidence?.length ?? '—'))],
    [copy('Giới hạn quét (Budget)', 'Scan budget'), report.budget ? (report.budget.bytes_analyzed ? Math.round(report.budget.bytes_analyzed / 1024) + ' KB' : 'Tiêu chuẩn') : 'Tiêu chuẩn'],
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
  const busy = data.busy.has('repos') || data.busy.has('sync') || data.busy.has('bulk');
  const toolbar = '<div class="panel analysis-toolbar"><div class="toolbar">' + filterControls(state, busy || Boolean(data.analysis))
    + btn(icon('repo') + escape(t('action.sync')), 'sync', 'secondary' + (data.busy.has('sync') ? ' is-loading' : ''), busy ? 'disabled' : '')
    + namedButton(copy('Tải lại', 'Refresh'), 'reload-reports', 'quiet small') + '</div>'
    + '<form class="field-row" id="repo-search">' + field(copy('Tìm repository', 'Find repository'), '<input name="repo-query" value="'
      + escape(data.search) + '">')
    + '<button class="button secondary" type="submit">' + escape(copy('Tìm', 'Search')) + '</button>'
    + (data.search ? btn(icon('close') + ' ' + copy('Xóa bộ lọc', 'Clear search'), 'clear-repo-search', 'quiet small') : '')
    + '</form>'
    + '<p class="scope-summary" role="status">' + escape(t('repos.count', { count: data.total })) + '</p>'
    + feedback(data, 'repos', 'sync', 'activity', 'cancel') + '</div>';
  if (!active) return intro + toolbar + (data.busy.has('repos')
    ? '<section class="panel ita-list-skeleton" role="status"><span class="ita-visually-hidden">' + escape(copy('Đang tải repository…', 'Loading repositories…')) + '</span>' + Array.from({length:3}, () => '<div class="ita-skeleton-row" aria-hidden="true"><i class="ita-skeleton-line ita-skeleton-line--wide"></i><i class="ita-skeleton-line ita-skeleton-line--short"></i></div>').join('') + '</section>'
    : '<div class="panel">' + blank(t('repos.noRepo'), t('repos.noRepoCopy')) + '</div>');
  const info = data.repoData[active.id] ?? { errors: {} };
  const report = info.report;

  const analyzedRepoIds = new Set(data.scores.map(item => item.repo?.id).filter(Boolean));
  if (data.repoData) {
    Object.entries(data.repoData).forEach(([repoId, d]) => {
      if (d?.report) analyzedRepoIds.add(Number(repoId));
    });
  }
  const analyzedCount = analyzedRepoIds.size;
  const hasRep = Boolean(report);

  const selectedRepoCount = data.selectedRepos?.size || 0;
  const isAllPageSelected = data.repos.length > 0 && data.repos.every(r => data.selectedRepos?.has(r.id));
  const bulkBar = '<div class="repo-bulk-bar">'
    + '<label class="repo-bulk-select-all"><input type="checkbox" data-act="toggle-all-page-repos" ' + (isAllPageSelected ? 'checked' : '') + '> '
    + copy('Chọn tất cả trên trang', 'Select all on page') + '</label>'
    + (selectedRepoCount > 0
      ? btn(icon('pulse') + ' ' + copy(`Phân tích ${selectedRepoCount} repo đã chọn`, `Analyze ${selectedRepoCount} selected repos`), 'analyze-selected', 'primary small pulse-button', busy || data.analysis ? 'disabled' : '')
      : '')
    + '</div>';

  const batch = data.bulkAnalysis;

  const bulkStatus = batch
    ? '<section class="notice" role="status" aria-live="polite">' +
    "<strong>" +
    escape(
      copy(
        `Phân tích hàng loạt: ${batch.done}/${batch.total} đã xử lý`,
        `Bulk analysis: ${batch.done}/${batch.total} processed`,
      ),
    ) +
    "</strong>" +
    '<progress max="' +
    batch.total +
    '" value="' +
    batch.done +
    '" aria-label="Bulk analysis progress"></progress>' +
    '<ul class="audit-list">' +
    batch.results
      .map((item) => {
        const labels = {
          preparing: copy("Đang chuẩn bị", "Preparing"),
          queued: copy("Đang chờ", "Queued"),
          running: copy("Đang phân tích", "Running"),
          cancel_requested: copy("Đang yêu cầu hủy", "Cancelling"),
          succeeded: copy("Thành công", "Succeeded"),
          failed: copy("Thất bại", "Failed"),
          cancelled: copy("Đã hủy", "Cancelled"),
          request_error: copy("Lỗi gửi yêu cầu", "Request error"),
          unknown: copy("Cần kiểm tra trạng thái", "Check job status"),
          not_started: copy('Chưa bắt đầu', 'Not started'),
        };

        return (
          "<li><strong>" +
          escape(item.name || `Repository #${item.repo_id}`) +
          "</strong> — " +
          escape(labels[item.status] || item.status) +
          (item.progress != null ? " (" + escape(item.progress) + "%)" : "") +
          (item.error ? "<small>" + escape(item.error) + "</small>" : "") +
          "</li>"
        );
      })
      .join("") +
    "</ul></section>"
    : "";

  const list = data.repos.map(repo => {
    const isCur = repo.id === active.id;
    const hasRepItem = Boolean(data.repoData[repo.id]?.report);
    const isChecked = Boolean(data.selectedRepos?.has(repo.id));
    return '<button type="button" class="repo-item' + (isCur ? ' is-selected' : '') + '" data-act="repo"' + attr('id', repo.id)
      + ' aria-pressed="' + isCur + '">'
      + '<input type="checkbox" class="repo-select-check" data-id="' + repo.id + '" ' + (isChecked ? 'checked' : '') + ' onclick="event.stopPropagation()">'
      + '<span><strong>' + escape(repo.full_name) + '</strong>'
      + (isCur ? ' <span class="tag-badge blue mini">' + copy('Đang xem', 'Selected') + '</span>' : '')
      + ' ' + badge(scopeLabel(repo.private ? 'private' : 'public'), repo.private ? 'amber' : 'green')
      + (hasRepItem ? ' ' + badge(copy('Đã có báo cáo', 'Report ready'), 'green') : '')
      + '</span><small>' + escape(repo.primary_language ?? '—') + '</small></button>';
  }).join('');
  const picker = '<div class="compact-repo-picker">' + field(t('repos.switch'), '<select id="repo-switch">'
    + data.repos.map(repo => option(repo.id, repo.full_name, active.id)).join('') + '</select>') + '</div>';
  const tabs = '<div class="tabs" role="group">' + ['code', 'ownership', 'collab'].map(key =>
    btn(escape(t('repos.' + key)), 'repo-tab', '', attr('id', key) + ' aria-pressed="' + (data.reportTab === key) + '"')).join('') + '</div>';
  const job = data.analysis && (!data.analysis.repo_id || data.analysis.repo_id === active.id) ? data.analysis : null;
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

  const totalPages = Math.max(1, Math.ceil(data.total / 30));
  const currentPage = data.page || 1;
  const pageOptions = Array.from({ length: totalPages }, (_, i) => i + 1).map(p =>
    option(p, copy(`Trang ${p} / ${totalPages}`, `Page ${p} / ${totalPages}`), currentPage)
  ).join('');

  const pages = '<div class="repo-pagination-bar">'
    + '<div class="repo-page-nav">'
    + (currentPage > 1 ? namedButton(copy('« Đầu', '« First'), 'repo-page', 'quiet small', 1) : '')
    + (currentPage > 1 ? namedButton(copy('‹ Trước', '‹ Prev'), 'repo-page', 'quiet small', currentPage - 1) : '')
    + '<span class="repo-page-info">' + copy(`Trang <strong>${currentPage}</strong> / ${totalPages}`, `Page <strong>${currentPage}</strong> / ${totalPages}`) + '</span>'
    + (currentPage < totalPages ? namedButton(copy('Sau ›', 'Next ›'), 'repo-page', 'quiet small', currentPage + 1) : '')
    + (currentPage < totalPages ? namedButton(copy('Cuối »', 'Last »'), 'repo-page', 'quiet small', totalPages) : '')
    + '</div>'
    + (totalPages > 1 ? '<div class="repo-page-jump">'
      + '<label><small>' + copy('Chuyển trang:', 'Jump to:') + '</small> '
      + '<select class="repo-page-select" data-act="repo-page-select">' + pageOptions + '</select></label>'
      + '</div>' : '')
    + '</div>';

  // Sticky/Prominent Repo Command Bar (Tôi đang xem repo và khoảng thời gian nào? Bấm nút nào bắt đầu phân tích?)
  const commandBar = '<section class="panel repo-command-bar" aria-label="' + copy('Bảng điều khiển phân tích repository', 'Repository analysis command bar') + '">'
    + '<div class="command-bar-inner">'
    + '<div class="command-repo-info">'
    + '<div class="command-kicker"><span class="badge-dot ' + (hasRep ? 'green' : 'yellow') + '"></span><small>'
    + copy('ĐANG CHỌN REPO ĐỂ PHÂN TÍCH', 'SELECTED FOR ANALYSIS') + '</small></div>'
    + '<h2 class="command-repo-title">' + escape(active.full_name) + '</h2>'
    + '<div class="command-meta-tags">'
    + '<span class="command-tag highlight-tag">' + icon('clock') + ' ' + copy('Kỳ: ', 'Window: ') + '<strong>' + escape(rangeLabel(state.range)) + '</strong></span>'
    + '<span class="command-tag">' + icon('repo') + ' ' + copy('Phạm vi: ', 'Scope: ') + escape(scopeLabel(active.private ? 'private' : 'public')) + '</span>'
    + '<span class="command-tag ' + (hasRep ? 'green' : 'amber') + '">' + icon(hasRep ? 'check' : 'pulse') + ' '
    + (hasRep ? copy('Đã có báo cáo năng lực', 'Analysis report available') : copy('Chưa phân tích mã nguồn', 'Not analyzed yet')) + '</span>'
    + '<span class="command-tag stats-tag">' + copy('Tổng hồ sơ: ', 'Profile total: ') + '<strong>' + analyzedCount + '/' + data.total + copy(' repo đã phân tích', ' analyzed') + '</strong></span>'
    + '</div>'
    + '</div>'
    + '<div class="command-cta-area">'
    + (job
      ? '<div class="command-job-status"><span class="spinner" aria-hidden="true"></span> <span>' + escape(stepText) + ' (' + (job.progress ?? 0) + '%)</span>'
      + namedButton(copy('Hủy', 'Cancel'), 'cancel-analysis', 'quiet small') + '</div>'
      : btn(icon('pulse') + ' ' + escape(hasRep ? copy('Phân tích lại commit mới', 'Re-analyze latest commit') : copy('BẮT ĐẦU PHÂN TÍCH REPO NÀY', 'START ANALYZING THIS REPO')),
        'analyze', hasRep ? 'secondary' : 'primary pulse-button', busy ? 'disabled' : '')
    )
    + '</div>'
    + '</div>'
    + '</section>';

  // Context Banner nhỏ trong main panel
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
    const primaryArch = report.architecture?.[0]?.name || copy('Chưa đủ bằng chứng', 'Insufficient evidence');
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
    + '<a href="#studio/dashboard" class="action-card highlight-card">'
    + '<span class="action-card-icon">' + icon('pulse') + '</span>'
    + '<div class="action-card-content"><strong>' + escape(copy('Xem điểm tổng hợp tại Dashboard →', 'View aggregated scores on Dashboard →')) + '</strong>'
    + '<small>' + escape(copy('Đối chiếu điểm Radar năng lực và xếp hạng vai trò kỹ sư', 'Check Radar competency scores and role ranking')) + '</small></div></a>'
    + '<a href="#studio/cv" class="action-card highlight-card">'
    + '<span class="action-card-icon">' + icon('file') + '</span>'
    + '<div class="action-card-content"><strong>' + escape(copy('Chèn dự án & kỹ năng này vào CV →', 'Insert project & skills into CV →')) + '</strong>'
    + '<small>' + escape(copy('Soạn thảo và xuất bản CV chứng minh bằng mã nguồn thật', 'Draft and export proof-backed resume')) + '</small></div></a>'
    + '<button type="button" class="action-card" data-act="ask-evidence" data-id="' + escape(active.id) + '">'
    + '<span class="action-card-icon">' + icon('bot') + '</span>'
    + '<div class="action-card-content"><strong>' + escape(copy('Hỏi AI Mentor về repo này', 'Ask AI Mentor about this repo')) + '</strong>'
    + '<small>' + escape(copy('Phân tích sâu điểm mạnh, điểm yếu và gợi ý cải tiến code', 'Deep dive into strengths, gaps, and code improvements')) + '</small></div></button>'
    + '<a href="#studio/jobs" class="action-card">'
    + '<span class="action-card-icon">' + icon('check') + '</span>'
    + '<div class="action-card-content"><strong>' + escape(copy('Đối chiếu với JD tuyển dụng', 'Match against Job Description')) + '</strong>'
    + '<small>' + escape(copy('Ướm thử năng lực từ repo này vào yêu cầu công việc', 'Match evidence from this repo against job requirements')) + '</small></div></a>'
    + '</div></section>' : '';

  return intro + toolbar + commandBar + '<div class="repo-layout"><section class="panel repo-picker">' + panelHead(t('repos.list'))
    + bulkBar + bulkStatus + '<div class="repo-list">' + list + '</div>' + pages + '</section><article class="panel repo-main" aria-labelledby="repo-title">' + picker
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

const SKILL_NAMES_VI = {
  docker: 'Docker & Container hóa',
  fastapi: 'FastAPI Web Framework',
  postgresql: 'Cơ sở dữ liệu PostgreSQL',
  testing: 'Kiểm thử phần mềm (Testing)',
  python: 'Lập trình Python chuyên sâu',
  react: 'Phát triển giao diện React',
  typescript: 'Ngôn ngữ TypeScript',
  javascript: 'Lập trình JavaScript',
  'ci/cd': 'Quy trình CI/CD tự động',
  linux: 'Quản trị hệ thống Linux',
  rabbitmq: 'Hàng đợi tin nhắn RabbitMQ',
  redis: 'Bộ nhớ đệm Redis (Caching)',
  redis_cache: 'Bộ nhớ đệm Redis Cache',
  system_design: 'Thiết kế hệ thống phân tán (System Design)',
  'system design': 'Thiết kế hệ thống phân tán (System Design)'
};

function displayMilestoneTitle(rawTitle, skillKey) {
  if (getLanguage() !== 'vi') return rawTitle;
  const key = String(skillKey || rawTitle || '').trim().toLowerCase();
  return SKILL_NAMES_VI[key] || rawTitle;
}

function displayObjective(objective, skillKey) {
  if (getLanguage() !== 'vi') return objective;
  if (!objective) return '';
  const key = String(skillKey || '').trim().toLowerCase();
  const skillName = SKILL_NAMES_VI[key] || key || 'kỹ năng này';
  if (/^Create and document a .* project with reviewable commits and tests$/i.test(objective.trim())) {
    return `Xây dựng và hoàn thiện dự án thực tế về ${skillName} với mã nguồn, commit rõ ràng và bộ kiểm thử hoàn chỉnh.`;
  }
  return objective;
}

function displayMetric(metric, skillKey) {
  if (getLanguage() !== 'vi') return metric;
  if (!metric) return '';
  const key = String(skillKey || '').trim().toLowerCase();
  const skillName = SKILL_NAMES_VI[key] || key || 'kỹ năng này';
  const match = metric.match(/^Reach verified .* assessment >= (\d+)\/100 with at least one accessible evidence reference$/i);
  if (match) {
    return `Đạt điểm đánh giá năng lực xác minh ${skillName} >= ${match[1]}/100 kèm ít nhất 1 minh chứng đóng góp mã nguồn hợp lệ trên GitHub.`;
  }
  return metric;
}

const statusLabel = status => ({
  completed: copy('Đã hoàn thành', 'Completed'), in_progress: copy('Đang thực hiện', 'In progress'), pending: copy('Chưa bắt đầu', 'Pending')
})[status] ?? status;

export function displayRoadmapTitle(title, goal) {
  if (getLanguage() !== 'vi') return title || (goal ? `${goal.charAt(0).toUpperCase() + goal.slice(1)} Career Roadmap` : '');
  const roleLabels = {
    backend: 'Backend',
    frontend: 'Frontend',
    fullstack: 'Full-stack',
    devops: 'DevOps'
  };
  if (title && /Career Roadmap/i.test(title)) {
    const roleMatch = title.match(/(\w+)\s+Career\s+Roadmap/i);
    const roleKey = roleMatch ? roleMatch[1].toLowerCase() : (goal || '').toLowerCase();
    const roleName = roleLabels[roleKey] || (roleMatch ? roleMatch[1] : (goal || ''));
    return `Lộ trình sự nghiệp ${roleName}`;
  }
  if (goal && roleLabels[goal.toLowerCase()]) {
    return `Lộ trình sự nghiệp ${roleLabels[goal.toLowerCase()]}`;
  }
  return title || (goal || '');
}

function roadmapLoadingSkeleton() {
  const label = escape(copy('Đang tải lộ trình và bản đồ kỹ năng…', 'Loading roadmap and skill map…'));
  const lines = '<span class="ita-skeleton-line ita-skeleton-line--wide"></span><span class="ita-skeleton-line"></span><span class="ita-skeleton-line ita-skeleton-line--short"></span>';
  return '<div class="ita-roadmap-skeleton" role="status" aria-label="' + label + '">'
    + '<span class="ita-visually-hidden">' + label + '</span>'
    + '<div class="road-banner"><section class="panel road-next ita-skeleton-card" aria-hidden="true">' + lines + '</section>'
    + '<section class="panel road-progress ita-skeleton-card" aria-hidden="true">' + lines + '</section></div>'
    + '<div class="road-layout"><section class="panel map-panel ita-skeleton-card ita-skeleton-map" aria-hidden="true">'
    + lines + '<div class="ita-skeleton-map-grid">'
    + Array.from({length:6}, () => '<span class="ita-skeleton-node"></span>').join('') + '</div></section>'
    + '<section class="panel road-detail ita-skeleton-card ita-skeleton-detail" aria-hidden="true">' + lines + lines + '</section></div></div>';
}

export function liveRoadmap(data) {
  const { milestones, done, next, goal } = progressOverview(data);
  const selected = milestones.find(m => m.id === data.milestone) ?? milestones[0];
  const item = data.road?.milestones?.find(m =>
    String(m.skill || '').toLowerCase() === String(selected?.external_key || '').toLowerCase()
  ) ?? (selected ? {
    objective: selected.title,
    metric: copy('Hoàn thành mục tiêu của cột mốc này và nộp minh chứng.', 'Complete the objective of this milestone and submit evidence.'),
    evidence: selected.evidence || []
  } : null);
  const picker = field(t('road.goal'), '<select id="road-goal">' + [
    ['backend', 'Backend'], ['frontend', 'Frontend'], ['fullstack', 'Full-stack'], ['devops', 'DevOps']
  ].map(([key, label]) => option(key, label, data.goal)).join('') + '</select>');
  const roadPicker = (data.roadmaps && data.roadmaps.length > 1)
    ? field(copy('Đổi lộ trình', 'Switch roadmap'), '<select id="road-select">'
      + data.roadmaps.map(r => option(r.id, `${displayRoadmapTitle(r.title, r.goal)} (#${r.id})`, data.road?.id)).join('')
      + '</select>')
    : '';

  if (data.busy.has('road') && data.roadmaps === undefined) {
    return heading(t('road.heading'), t('road.intro'), '<div class="road-pickers-row" style="display:flex;gap:12px;flex-wrap:wrap">' + picker + roadPicker + '</div>') + roadmapLoadingSkeleton();
  }

  const map = milestones.map(milestone => '<button type="button" class="node" data-act="milestone"' + attr('id', milestone.id)
    + attr('state', milestone.status === 'completed' ? 'done' : 'ready') + ' aria-pressed="' + (milestone === selected) + '">'
    + '<span class="map-icon">' + icon(milestone.status === 'completed' ? 'check' : 'branch') + '</span><strong>'
    + escape(displayMilestoneTitle(milestone.title, milestone.external_key)) + '</strong><small>' + escape(statusLabel(milestone.status)) + '</small></button>').join('');

  const sourceLabel = src => ({
    manual: copy('Thủ công', 'Manual'),
    mentor: copy('Đề xuất AI Mentor', 'AI Mentor proposal'),
    suggestion: copy('Đề xuất hệ thống', 'System suggestion'),
    submission: copy('Nộp minh chứng', 'Evidence submission'),
    verified: copy('Xác minh Git', 'Git verified')
  })[src] ?? src;

  const history = '<details class="panel road-history"' + (data.history.length ? ' open' : '') + '><summary>' + escape(t('road.history')) + '</summary>'
    + btn(escape(copy('Tải lịch sử', 'Load history')), 'road-history', 'quiet small' + (data.busy.has('road') ? ' is-loading' : ''), data.busy.has('road') ? 'disabled' : '') + '<ul class="audit-list">'
    + data.history.map(record => '<li><time>' + escape(formattedDate(record.created_at)) + '</time>'
      + '<span>' + escape(statusLabel(record.old_status) + ' → ' + statusLabel(record.new_status)) + '</span>'
      + (record.source ? ' ' + badge(sourceLabel(record.source), record.source === 'verified' ? 'green' : record.source === 'mentor' ? 'blue' : '') : '')
      + (record.note ? '<div class="history-note-text"><small>' + escape(record.note) + '</small></div>' : '')
      + '</li>').join('') + '</ul></details>';

  const evaluation = data.reevaluation;
  const evaluationSuggestions = currentEvaluationSuggestions(evaluation, data.tracking);
  const pending = evaluation ? [] : (data.tracking?.suggestions.filter(
    suggestion => suggestion.state === 'pending' && suggestion.milestone_id === selected?.id
  ) ?? []);

  const evaluationTitle = evaluation?.kind === 'suggestions'
    ? copy('Đã tìm thấy bằng chứng GitHub xác minh hợp lệ', 'Verified GitHub evidence found')
    : evaluation?.kind === 'no-verified-evidence'
      ? copy('Chưa có bằng chứng GitHub được xác minh', 'No verified GitHub evidence yet')
      : evaluation?.kind === 'all-completed'
        ? copy('Các mốc hiện tại đều đã hoàn thành', 'All milestones are already completed')
        : copy('Chưa có mốc mới đáp ứng đủ điều kiện', 'No additional milestones meet the criteria');
  const evaluationDescription = !evaluation ? '' : evaluation.kind === 'suggestions'
    ? copy('Có ' + evaluationSuggestions.length + ' đề xuất từ dữ liệu đã xác minh. Chọn Áp dụng hoặc Bỏ qua cho từng mốc.',
      evaluationSuggestions.length + ' verified suggestions. Apply or dismiss each one.')
    : evaluation?.kind === 'no-verified-evidence'
      ? copy('Các link tự khai báo không được tính là bằng chứng xác minh. Hãy đồng bộ và chạy phân tích GitHub, sau đó quay lại đánh giá.',
        'Self-reported links are not verified evidence. Sync and analyze GitHub first, then re-evaluate.')
      : evaluation?.kind === 'all-completed'
        ? copy('Không còn mốc đang chờ đánh giá trong lộ trình này.', 'There are no unfinished milestones in this roadmap.')
        : copy('Đã đối chiếu ' + evaluation.verifiedSkills + ' kỹ năng có minh chứng được xác minh; chưa có mốc mới thỏa tất cả yêu cầu.',
          'Checked ' + evaluation.verifiedSkills + ' evidence-backed skills; no additional milestone meets every requirement.');
  const evaluationCards = evaluationSuggestions.map(suggestion => {
    const milestone = milestones.find(m => m.id === suggestion.milestone_id);
    const name = milestone ? displayMilestoneTitle(milestone.title, milestone.external_key)
      : copy('Cột mốc #', 'Milestone #') + suggestion.milestone_id;
    const evidenceCount = Array.isArray(suggestion.evidence) ? suggestion.evidence.length : 0;
    return '<article class="road-review-suggestion"><h4>' + icon('check') + ' ' + escape(name) + '</h4>'
      + '<p>' + escape(copy('Đã tìm thấy ' + evidenceCount + ' tham chiếu bằng chứng đã xác minh.',
        evidenceCount + ' verified evidence references found.')) + '</p>'
      + '<p class="subtle">' + escape(suggestion.explanation || '') + '</p>'
      + '<div class="action-row">'
      + btn(escape(copy('Áp dụng', 'Apply')), 'road-suggestion', 'primary small' + (data.busy.has('road') ? ' is-loading' : ''),
        attr('id', suggestion.id) + attr('decision', 'apply') + (data.busy.has('road') ? ' disabled' : ''))
      + btn(escape(copy('Bỏ qua', 'Dismiss')), 'road-suggestion', 'secondary small' + (data.busy.has('road') ? ' is-loading' : ''),
        attr('id', suggestion.id) + attr('decision', 'reject') + (data.busy.has('road') ? ' disabled' : ''))
      + '</div></article>';
  }).join('');
  const evaluationHtml = evaluation ? '<section class="panel road-review-result" role="status" aria-live="polite">'
    + '<h3>' + icon(evaluationSuggestions.length ? 'check' : 'info') + ' ' + escape(evaluationTitle) + '</h3>'
    + '<p>' + escape(evaluationDescription) + '</p>'
    + '<p class="subtle">' + escape(copy('Đánh giá dựa trên kết quả phân tích đã lưu, không quét commit mới trực tiếp.',
      'Based on stored analysis; this action does not fetch new commits.')) + '</p>'
    + (evaluationSuggestions.length ? '<div class="road-review-suggestions">' + evaluationCards + '</div>' : '')
    + '<a class="button secondary small" href="#studio/repos">'
    + icon('repo') + ' ' + escape(copy('Đồng bộ / Phân tích GitHub', 'Sync / Analyze GitHub')) + '</a>'
    + '</section>' : '';


  // Proof checkmarks represent submitted links, never scoring references.
  const evidenceItems = submittedEvidenceLinks(selected?.evidence);
  const verifiedLinkCount = evidenceItems.filter(ev => ev.verified).length;
  const proofLinksHtml = '<div class="milestone-proof-evidence">'
    + '<div class="milestone-proof-summary"><strong>'
    + escape(copy('Đã nộp ' + evidenceItems.length + ' liên kết', evidenceItems.length + ' submitted links'))
    + '</strong><span>'
    + escape(copy(verifiedLinkCount + ' đã xác minh', verifiedLinkCount + ' verified'))
    + '</span></div>'
    + (evidenceItems.length ? '<ul class="milestone-proof-link-list">'
      + evidenceItems.map(ev => {
        const parsed = new URL(ev.url);
        const label = parsed.hostname + parsed.pathname + parsed.search;
        return '<li class="milestone-proof-link ' + (ev.verified ? 'is-verified' : 'is-self-reported') + '">'
          + '<span class="milestone-proof-tick" aria-hidden="true">' + icon('check') + '</span>'
          + '<a href="' + escape(ev.url) + '" title="' + escape(ev.url)
          + '" target="_blank" rel="noopener noreferrer">' + escape(label) + '</a>'
          + '<small>' + escape(ev.verified
            ? copy('Đã xác minh', 'Verified')
            : copy('Tự khai báo', 'Self-reported')) + '</small></li>';
      }).join('') + '</ul>'
      : '<p class="milestone-proof-empty">'
        + escape(copy('Chưa có liên kết bằng chứng được nộp.', 'No evidence links submitted yet.'))
        + '</p>')
    + '<small class="milestone-proof-help">'
    + escape(copy('✓ = liên kết đã nộp; chỉ liên kết xác minh mới có trạng thái Đã xác minh.',
      '✓ = submitted link; only verified links are marked Verified.'))
    + '</small></div>';
  const evidenceListHtml = evidenceItems.length ? '<div class="milestone-evidence-block"><h4>'
    + icon('award') + ' ' + copy('Bằng chứng đã nộp & xác minh', 'Submitted & Verified Evidence') + '</h4>'
    + '<ul class="milestone-evidence-list">' + evidenceItems.map(ev => {
      return '<li><div class="evidence-link-row">'
        + '<a href="' + escape(ev.url) + '" target="_blank" rel="noopener noreferrer" class="evidence-anchor">'
        + icon('branch') + ' ' + escape(ev.url) + '</a>'
        + badge(ev.verified ? copy('Đã xác minh (Verified)', 'Verified') : copy('Tự khai báo', 'Self-reported'), ev.verified ? 'green' : 'amber')
        + '</div>' + (ev.note ? '<p class="evidence-subnote">' + escape(ev.note) + '</p>' : '') + '</li>';
    }).join('') + '</ul></div>' : '';
  // Existing skill-assessment references remain accessible but are not
  // counted as user-submitted URLs or interpreted as verified submissions.
  const assessmentRefsHtml = Array.isArray(item?.evidence) && item.evidence.length
    ? '<details class="milestone-analysis-refs"><summary>'
      + escape(copy('Tham chiếu phân tích năng lực (không tính là link đã nộp)',
        'Assessment references (not submitted links)'))
      + '</summary>' + refs(item.evidence) + '</details>'
    : '';

  const isCompleted = selected?.status === 'completed';
  const evidenceFormHtml = selected ? '<form class="stack road-evidence-form" id="milestone-evidence-form" data-milestone="' + selected.id + '">'
    + '<input type="hidden" name="milestone_id" value="' + selected.id + '">'
    + '<h4>' + icon('pulse') + ' ' + (isCompleted ? copy('Bổ sung thêm minh chứng', 'Submit additional evidence') : copy('Nộp minh chứng hoàn thành mốc', 'Submit milestone evidence')) + '</h4>'
    + '<p class="subtle">' + (isCompleted
      ? copy('Cột mốc này đã hoàn thành. Bạn có thể nộp thêm liên kết Commit/PR để làm phong phú bằng chứng cho portfolio và CV.', 'This milestone is completed. You can submit more Commit/PR links to enrich your evidence.')
      : copy('Chỉ nộp URL HTTPS trực tiếp đến Commit hoặc Pull Request trên github.com. Link Issue hoặc trang repository sẽ bị từ chối.', 'Submit only direct HTTPS GitHub Commit or Pull Request URLs. Issue and repository page links are rejected.')) + '</p>'
    + '<div class="field-row">'
    + '<input name="evidence_url" type="url" aria-describedby="road-evidence-validation" placeholder="https://github.com/owner/repo/pull/123" required>'
    + '<input name="evidence_note" placeholder="' + copy('Ghi chú (tùy chọn)', 'Short note (optional)') + '">'
    + '<button type="submit" class="button primary small' + (data.busy.has('road') ? ' is-loading' : '') + '"' + (data.busy.has('road') ? ' disabled aria-busy="true"' : '') + '>' + copy('Nộp minh chứng', 'Submit') + '</button>'
    + '</div><p id="road-evidence-validation" class="road-evidence-validation" role="alert" hidden></p></form>' : '';

  let actionButtonsHtml = '';
  if (selected) {
    if (selected.status === 'completed') {
      actionButtonsHtml = btn(icon('arrow') + ' ' + copy('Mở lại mốc này (Chuyển về Đang thực hiện)', 'Reopen milestone (In progress)'),
        'road-status', 'secondary small', attr('id', selected.id) + attr('status', 'in_progress'));
    } else if (selected.status === 'in_progress') {
      actionButtonsHtml = btn(icon('check') + ' ' + copy('Xác nhận đã hoàn thành', 'Mark as completed'),
        'road-status', 'primary small', attr('id', selected.id) + attr('status', 'completed'))
        + btn(copy('Quay lại: Chưa bắt đầu', 'Revert to Pending'),
          'road-status', 'quiet small', attr('id', selected.id) + attr('status', 'pending'));
    } else {
      actionButtonsHtml = btn(icon('play') + ' ' + copy('Bắt đầu thực hiện mốc này', 'Start this milestone'),
        'road-status', 'primary small', attr('id', selected.id) + attr('status', 'in_progress'))
        + btn(icon('check') + ' ' + copy('Đánh dấu đã hoàn thành', 'Mark as completed'),
          'road-status', 'secondary small', attr('id', selected.id) + attr('status', 'completed'));
    }
  }

  const detailTitle = selected ? displayMilestoneTitle(selected.title, selected.external_key) : '';
  const detailObjective = item ? displayObjective(item.objective, selected?.external_key) : '';
  const detailMetric = item ? displayMetric(item.metric, selected?.external_key) : '';

  const detail = selected && item ? '<article class="panel road-detail" id="milestone-detail"><div class="detail-top">'
    + badge(statusLabel(selected.status), selected.status === 'completed' ? 'green' : 'blue') + '</div>'
    + '<h2>' + escape(detailTitle) + '</h2>' + paragraph(detailObjective)
    + '<div class="milestone-proof"><span class="feature-icon">' + icon('award') + '</span><div><h3>'
    + escape(t('road.proof')) + '</h3>' + paragraph(detailMetric) + proofLinksHtml + '</div></div>'
    + evidenceListHtml
    + assessmentRefsHtml
    + evidenceFormHtml
    + '<div class="action-row" style="margin-top:14px">'
    + actionButtonsHtml
    + btn(icon('bot') + ' ' + copy('Hỏi AI Mentor về mốc này', 'Ask AI Mentor about this milestone'), 'ask-milestone', 'secondary small', attr('id', selected.id) + attr('title', detailTitle)) + '</div>'
    + pending.map(suggestion => '<div class="notice">' + paragraph(suggestion.explanation)
      + ['apply', 'reject'].map(decision => btn(escape(decision === 'apply' ? copy('Áp dụng', 'Apply') : copy('Bỏ qua', 'Dismiss')),
        'road-suggestion', 'secondary small', attr('id', suggestion.id) + attr('decision', decision))).join('') + '</div>').join('') + '</article>' : '';
  return heading(t('road.heading'), t('road.intro'), '<div class="road-pickers-row" style="display:flex;gap:12px;flex-wrap:wrap">' + picker + roadPicker + '</div>') + feedback(data, 'road')
    + '<div class="road-banner"><section class="panel road-next"><div><p class="eyebrow">' + escape(t('road.next')) + '</p><h2>'
    + escape(next ? displayMilestoneTitle(next.title, next.external_key) : (data.road ? t('road.finished') : copy('Chưa có lộ trình', 'No roadmap yet'))) + '</h2>'
    + (goal ? paragraph(goal.objective) : '') + '</div>'
    + btn(escape(copy('Tạo lộ trình', 'Generate roadmap')), 'road-create', 'primary' + (data.busy.has('road') ? ' is-loading' : ''), data.busy.has('road') ? 'disabled' : '') + '</section>'
    + '<section class="panel road-progress"><div><p class="eyebrow">' + escape(t('road.progress')) + '</p><strong>' + done.length + '<span> / ' + milestones.length
    + '</span></strong><p>' + escape(t('road.progressCount', { done: done.length, total: milestones.length })) + '</p></div>'
    + '<div class="milestone-pips" aria-hidden="true">' + milestones.map(m => '<i' + attr('state', m.status === 'completed' ? 'done' : 'ready') + '></i>').join('') + '</div></section></div>'
    + (data.road ? '<section class="road-update"><div>' + icon('pulse') + escape(copy('Cập nhật từ kết quả phân tích GitHub', 'Recheck GitHub evidence')) + '</div>'
      + btn(escape(copy('Đánh giá lại', 'Re-evaluate')), 'road-draft', 'secondary small' + (data.busy.has('road') ? ' is-loading' : ''), data.busy.has('road') ? 'disabled' : '') + '</section>' : '')
    + evaluationHtml
    + '<div class="road-layout"><section class="panel map-panel">' + panelHead(t('road.map'), copy('Chọn mốc để xem mục tiêu và bằng chứng.', 'Select a milestone to see its goal and evidence.'))
    + '<div class="map-legend">' + ['done', 'ready'].map(mode => '<span data-state="' + mode + '"><i></i>' + escape(t('road.' + mode)) + '</span>').join('') + '</div>'
    + (map ? '<div class="road-map"><svg class="road-map-lines" aria-hidden="true" focusable="false"></svg><canvas aria-hidden="true"></canvas>' + map + '</div>' : muted(copy('Chưa có cột mốc để hiển thị.', 'No milestones to display.')))
    + '</section>' + detail + (selected ? '<div class="road-records stack">'
      + (done.length ? '<section class="panel achievements">' + panelHead(t('road.trophies')) + '<div class="award-list">'
        + done.map(m => '<button class="award-card" type="button" data-act="milestone"' + attr('id', m.id) + '><span class="award-icon">'
          + icon('award') + '</span><span><strong>' + escape(displayMilestoneTitle(m.title, m.external_key)) + '</strong><small>'
          + escape(m.verification_status === 'verified' ? copy('Đã xác minh Git', 'Git Verified') : copy('Đã hoàn thành', 'Completed'))
          + '</small></span>' + icon('arrow') + '</button>').join('')
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

  let comparisonHtml = '';
  if (report?.skills?.length) {
    const matchedSkills = report.skills.filter(s => s.status === 'matched');
    const gapSkills = report.skills.filter(s => s.status !== 'matched');
    const reqSkills = report.skills.filter(s => s.level === 'required');
    const matchedReqSkills = reqSkills.filter(s => s.status === 'matched');
    const pct = report.required_matched_percent != null ? Math.round(report.required_matched_percent) : 0;

    const summaryBlock = '<div class="job-match-summary">'
      + '<div class="match-summary-head"><div><p class="eyebrow">' + copy('Độ phù hợp hồ sơ', 'Profile Match Rate') + '</p>'
      + '<h3>' + copy('Đáp ứng ', 'Matching ') + matchedSkills.length + '/' + report.skills.length + copy(' kỹ năng', ' skills')
      + (reqSkills.length ? '<small style="font-size:12px;font-weight:normal;color:var(--muted);margin-left:6px">(' + matchedReqSkills.length + '/' + reqSkills.length + copy(' bắt buộc)', ' required)') + '</small>' : '')
      + '</h3>'
      + '</div>' + badge(pct + '%', pct >= 70 ? 'green' : pct >= 40 ? 'amber' : '') + '</div>'
      + progress(pct, copy('Độ phù hợp yêu cầu', 'Match rate'))
      + (report.disclaimer ? '<p class="subtle" style="margin-top:6px">' + escape(report.disclaimer) + '</p>' : '')
      + '</div>';

    const matchedHtml = '<div class="job-group-block"><h4 class="job-group-title green">'
      + icon('check') + ' ' + copy('Kỹ năng đã đáp ứng từ GitHub (Matching)', 'Matching Skills from GitHub') + ' (' + matchedSkills.length + ')</h4>'
      + (matchedSkills.length
        ? '<ul class="job-evidence-list">' + matchedSkills.map(item => '<li><div><strong>' + escape(formatSkillName(item.skill_key)) + '</strong>'
          + badge(t('jobs.has'), 'green') + '</div>' + paragraph(item.reason) + refs(item.evidence, data) + '</li>').join('') + '</ul>'
        : '<p class="subtle" style="padding:10px 12px;background:rgba(255,255,255,0.02);border-radius:6px;border:1px dashed var(--line);margin:6px 0;">'
          + escape(copy('Chưa có kỹ năng nào đạt ngưỡng đối chiếu từ mã nguồn GitHub của bạn trong phạm vi này.', 'No skills reached matching threshold from your GitHub source code in this scope.')) + '</p>')
      + '</div>';

    const gapHtml = gapSkills.length ? '<div class="job-group-block"><h4 class="job-group-title amber">'
      + icon('pulse') + ' ' + copy('Khoảng cách kỹ năng cần bổ sung (Skill Gaps)', 'Skill Gaps to Address') + ' (' + gapSkills.length + ')</h4>'
      + '<ul class="job-evidence-list">' + gapSkills.map(item => '<li><div><strong>' + escape(formatSkillName(item.skill_key)) + '</strong>'
        + badge(t('jobs.' + ({ partial: 'partial', unknown: 'missing' })[item.status]), 'amber')
        + '</div>' + paragraph(item.reason)
        + '<div class="gap-action-row" style="margin-top:6px">'
        + btn(icon('branch') + ' ' + copy('Xem gợi ý lộ trình', 'View in roadmap'), 'view-skill-roadmap', 'quiet small', attr('skill', item.skill_key))
        + btn(icon('bot') + ' ' + copy('Hỏi AI Mentor cách học', 'Ask AI Mentor'), 'ask-gap-skill', 'quiet small', attr('skill', item.skill_key))
        + '</div>'
        + '</li>').join('') + '</ul></div>' : '';

    comparisonHtml = summaryBlock + matchedHtml + gapHtml + (report.limitations ?? []).map(muted).join('');
  }

  return heading(t('nav.jobs'), copy('Tìm tin tuyển dụng hoặc dán JD để đối chiếu với hồ sơ.', 'Find a job listing or paste a job description to match it against your profile.')) + feedback(data, 'jobs')
    + '<div class="columns"><div class="stack"><article class="panel">' + panelHead(t('jobs.search'), 'Remotive')
    + '<form id="job-search" class="field-row">' + field(t('jobs.keyword'), '<input name="query" value="' + escape(data.jobQuery ?? '')
      + '" maxlength="200" placeholder="Python, FastAPI, TypeScript" required>')
    + '<button class="button secondary' + (data.busy.has('jobs') ? ' is-loading' : '') + '" type="submit"' + (data.busy.has('jobs') ? ' disabled' : '') + '>' + escape(t('jobs.searchAction')) + '</button></form>'
    + '<div class="rows view-rows">' + (data.jobResults?.warnings ?? []).map(muted).join('')
    + (rows || (data.jobResults ? muted(t('jobs.noMatch')) : '')) + '</div></article>'
    + '<article class="panel">' + panelHead(t('jobs.paste')) + '<form id="jd-form" class="stack">'
    + field(t('jobs.description'), '<textarea name="jd" id="jd-textarea" rows="4" maxlength="50000" class="auto-scale-textarea" placeholder="' + escape(t('jobs.placeholder'))
      + '">' + escape(data.jobText ?? '') + '</textarea>')
    + field(copy('Hoặc URL tuyển dụng', 'Or listing URL'), '<input name="jd-url" type="url" value="' + escape(data.jobURL ?? '') + '">')
    + '<button class="button primary' + (data.busy.has('jobs') ? ' is-loading' : '') + '" type="submit"' + (data.busy.has('jobs') ? ' disabled' : '') + '>' + escape(t('jobs.analyze')) + '</button></form></article></div>'
    + '<article class="panel">' + panelHead(t('jobs.compare'), scopeLabel(state.scope))
    + (comparisonHtml || (data.busy.has('jobs') ? '<div class="ita-compare-skeleton" role="status"><span class="ita-visually-hidden">' + escape(copy('Đang đối chiếu yêu cầu công việc…', 'Matching job requirements…')) + '</span><span class="ita-skeleton-line ita-skeleton-line--wide" aria-hidden="true"></span><span class="ita-skeleton-meter" aria-hidden="true"></span><span class="ita-skeleton-line" aria-hidden="true"></span><span class="ita-skeleton-line ita-skeleton-line--short" aria-hidden="true"></span></div>' : blank(t('jobs.none'), t('jobs.noneCopy')))) + '</article></div>';
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

  const isSaved = doc && draft.name === doc.title && draft.body === doc.lines.map(l => l.text).join('\n');
  const saveStatusBadge = isSaved
    ? '<span class="status-pill green">' + icon('check') + ' ' + copy('Đã lưu bản mới nhất (#' + doc.number + ')', 'Saved latest (#' + doc.number + ')') + '</span>'
    : '<span class="status-pill amber">' + icon('pulse') + ' ' + copy('Bản nháp có thay đổi chưa lưu', 'Unsaved draft changes') + '</span>';

  // CV Command Bar: Đặt các thao tác quan trọng nhất (Lưu, Chèn từ Git, Xuất tệp) ngay đầu trang
  const cvCommandBar = '<section class="panel cv-command-bar" aria-label="' + copy('Thanh công cụ CV', 'CV Action Bar') + '">'
    + '<div class="cv-command-inner">'
    + '<div class="cv-command-status">'
    + saveStatusBadge
    + '<small class="cv-command-doc-info">'
    + (doc ? copy('Tài liệu CV Studio: ', 'CV Studio Doc: ') + '<strong>' + escape(doc.title) + ' (#' + doc.number + ')</strong>'
      : (cv ? copy('CV tải lên: #', 'Uploaded CV: #') + cv.id : copy('Bản nháp tự do (Chưa liên kết tài liệu máy chủ)', 'Freeform draft (Not linked to server doc)')))
    + '</small>'
    + '</div>'
    + '<div class="cv-command-actions">'
    + btn(icon('pulse') + ' ' + escape(copy('Chèn kỹ năng có bằng chứng từ GitHub', 'Insert evidence-backed GitHub skills')), 'cv-insert-github', 'secondary small pulse-button')
    + namedButton(copy('Tạo CV bằng AI', 'Generate with AI'), 'cv-generate', 'secondary small')
    + '<div class="cv-export-group">'
    + namedButton('PDF', 'cv-export', 'secondary small', 'pdf')
    + namedButton('DOCX', 'cv-export', 'secondary small', 'docx')
    + namedButton(t('cv.print'), 'cv-print', 'secondary small')
    + '</div>'
    + '</div>'
    + '</div>'
    + '</section>';

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
    + cvCommandBar
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
