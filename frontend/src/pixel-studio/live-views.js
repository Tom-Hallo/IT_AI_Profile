import { dateLabel, getLanguage, rangeLabel, scopeLabel, t } from './i18n.js';
import { attr, badge, blank, brand, btn, details, escape, field, filterControls, formatSkillName, heading, icon, labelAttr, languagePicker, link, option, panelHead, progress, tags } from './ui.js';
import { radarView } from './radar.js';
import {renderAnalysisFeedback} from './analysis-feedback.js';
import { safeLink } from './live-api.js';
import {currentEvaluationSuggestions} from './reevaluation.js';
import {submittedEvidenceLinks} from './roadmap-evidence.js';
import {reportBackedSkillScore, verifiedCVSkills, cvSkillKey, verifiedRoleScore, skillEvidenceSummary} from './score-presentation.js';
import {githubRadarMetrics, RADAR_RUBRIC_VERSION} from './dashboard-github-metrics.js';
import { renderReferenceCV, parseCVForReference, getSectionIcon } from './cv-renderer.js';

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
  return keys.map(key => data.errors[key] ? '<div class="notice red notice-error" role="alert"><span class="notice-icon">⚠</span> <span>' + escape(data.errors[key]) + '</span></div>'
    : data.messages[key] ? '<div class="notice green notice-success" role="status"><span class="notice-icon">✓</span> <span>' + escape(data.messages[key]) + '</span></div>'
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

function scoreRow(title, value, action, id, active, unavailableLabel = '') {
  return '<button type="button" class="score-row" data-act="' + action + '"' + attr('id', id)
    + ' aria-pressed="' + active + '"><span>' + escape(title) + '</span><b>'
    + (value == null && unavailableLabel ? '<small>' + escape(unavailableLabel) + '</small>' : number(value))
    + (value == null ? '' : '<small>/100</small>') + '</b>'
    + (value == null ? '' : '<span class="score-track" aria-hidden="true">' + progress(value, title) + '</span>') + '</button>';
}

const skillCriterionLabels = {
  code_contribution:['Đóng góp mã nguồn','Source contributions'],
  commit_frequency:['Commit cá nhân','Personal commits'],
  pr_contribution:['Đóng góp qua PR','PR contributions'],
  complexity:['Phạm vi tệp thay đổi','Changed file scope'],
  verified_activity:['Hoạt động đã xác minh','Verified activity'],
  confidence:['Độ tin cậy','Confidence']
};

function skillEvidenceDetails(item, audit) {
  if (audit.snapshotMissing) return muted(copy('Chưa có snapshot điểm cho báo cáo này.', 'No score snapshot exists for this report.'));
  if (!audit.available) return muted(copy('Báo cáo cũ chưa lưu chẩn đoán chi tiết. Phân tích lại để xem tiêu chí và số minh chứng.', 'Older reports lack detailed diagnostics. Reanalyze to see criteria and evidence counts.'));
  const count = value => value === null ? '—' : String(value);
  const rows = [
    [copy('Commit khớp công nghệ','Matching commits'), count(audit.matchedCommits)],
    [copy('PR khớp công nghệ','Matching PRs'), count(audit.matchedPRs)],
    [copy('File khớp minh chứng','Matching files'), count(audit.matchedFiles)],
    [copy('Sự kiện dùng để chấm điểm','Events used for scoring'), count(audit.usedEvents)],
    [copy('File dùng để chấm điểm','Files used for scoring'), count(audit.usedFiles)]
  ];
  if (audit.sourceFiles !== null) rows.push([copy('File có import framework','Files importing framework'), count(audit.sourceFiles)]);
  if (audit.eligiblePRFiles !== null && audit.completedPRFiles !== null) rows.push([
    copy('PR đã lấy đủ chi tiết file (repo)','PR file collection (repository)'), audit.completedPRFiles + '/' + audit.eligiblePRFiles
  ]);
  const missing = audit.missing.length ? '<div class="role-score-audit"><h4>'
    + copy('Tiêu chí chưa đủ minh chứng','Missing evidence criteria') + '</h4><ul class="audit-list">'
    + audit.missing.map(key => '<li>' + escape(copy(...(skillCriterionLabels[key] ?? [key,key]))) + '</li>').join('')
    + '</ul></div>' : '';
  const warnings = (audit.collectionIncomplete ? muted(copy(
    'Quá trình thu thập hoặc phân tích chưa đầy đủ; chưa thể kết luận về kỹ năng.',
    'Collection or analysis is incomplete; skill cannot be assessed.'
  )) : '') + (audit.filesPartial ? muted(item.kind === 'framework' ? copy(
    'Chi tiết file GitHub còn thiếu. Rubric framework đang áp dụng hệ số giảm độ tin cậy.',
    'Some GitHub file details are missing. The framework rubric applies a confidence reduction.'
  ) : copy('Chi tiết file GitHub còn thiếu; phạm vi minh chứng có thể chưa đầy đủ.', 'Some GitHub file details are missing; evidence coverage may be incomplete.')) : '');
  return details(rows) + missing + warnings;
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
      return scoreRow(item.technology + ' · ' + (item.repo.full_name || item.repo.name), reportBackedSkillScore(item), 'score', key(item), isSelected);
    }).join('');

    if (selected) {
      const selectedValue = reportBackedSkillScore(selected);
      const audit = skillEvidenceSummary(selected);
      const confPct = audit.confidence === null ? '—' : number(audit.confidence);
      const evidenceLabel = audit.snapshotMissing ? copy('Chưa có kết quả chấm điểm','No score snapshot')
        : audit.collectionIncomplete ? copy('Dữ liệu chưa đầy đủ','Incomplete collection')
          : selectedValue === null ? copy('Chưa đủ bằng chứng xác minh','Insufficient verified evidence')
            : copy('Đã có điểm từ minh chứng','Evidence-backed score');
      evidence = '<div class="evidence-header-block"><div><h3>' + escape(selected.technology) + '</h3>'
        + '<span class="tag-badge ' + (selectedValue === null ? 'yellow' : 'green') + '">' + escape(evidenceLabel) + '</span></div>'
        + scorePill(selectedValue) + '</div>'
        + paragraph(selected.explanation)
        + details([
          [copy('Repository nguồn', 'Source Repository'), escape(selected.repo.full_name || selected.repo.name)],
          [copy('Độ tin cậy', 'Confidence'), confPct + (confPct === '—' ? '' : '/100')],
          [copy('Trạng thái chấm điểm', 'Scoring status'), escape(scoreStatusLabel(selected.status))]
        ])
        + skillEvidenceDetails(selected, audit)
        + '<div class="evidence-action-row modal-action-footer">'
        + btn(icon('file') + ' ' + copy('Xem mã nguồn & bằng chứng tại repo ', 'Inspect code & evidence in ') + escape(selected.repo.full_name || selected.repo.name) + ' ↗',
          'evidence', 'primary small', attr('id', selected.repo.id))
        + '</div>';
    }
  } else if (runtime.scoreTab === 'roles') {
    const selection = data.roles.find(item => item.key === data.roleKey) ?? data.roles[0];
    const selected = selection?.score;
    scores = data.roles.map(item => {
      const value = verifiedRoleScore(item.score);
      const label = item.loadError ? copy('Lỗi tải điểm', 'Score load failed')
        : item.available === false ? copy('Không khả dụng', 'Unavailable')
          : item.score ? scoreStatusLabel(item.score.status) : copy('Chưa có dữ liệu', 'No data');
      return scoreRow(item.name, value, 'role-score', item.key, selection === item, label);
    }).join('');
    if (selected) {
      const selectedValue = verifiedRoleScore(selected);
      const coverage = Number.isFinite(selected.coverage)
        ? Math.round(selected.coverage * 100) + '%' : '—';
      const confidence = Number.isFinite(selected.confidence)
        ? number(selected.confidence) + '/100' : '—';
      const criteria = Array.isArray(selected.criteria) ? selected.criteria : [];
      const requiredUnmet = new Set(selected.required_unmet ?? []);
      const blockers = criteria.filter(item => item.status !== 'SCORED' || requiredUnmet.has(item.key));
      const refsUsed = Array.isArray(selected.evidence_refs) ? selected.evidence_refs : [];
      const blockersList = blockers.length
        ? '<div class="role-score-audit"><h4>' + copy('Tiêu chí chưa đạt hoặc chưa xác định', 'Unmet or unknown criteria') + '</h4>'
          + '<ul class="audit-list">' + blockers.map(item => '<li><strong>' + escape(item.name || item.key) + '</strong>'
            + (item.required ? ' <span class="tag-badge yellow">' + copy('Bắt buộc', 'Required') + '</span>' : '')
            + muted(item.rationale || scoreStatusLabel(item.status))
            + (Number.isFinite(item.confidence) ? muted(copy('Độ tin cậy: ', 'Confidence: ') + number(item.confidence) + '/100') : '')
            + '</li>').join('') + '</ul></div>'
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
        + '<div class="evidence-action-row modal-action-footer">'
        + [...new Set(refsUsed.map(ref => ref.repository_id).filter(Boolean))]
          .map(id => namedButton(copy('Mở repo #', 'Open repo #') + id + ' ↗', 'evidence', 'secondary small', id)).join(' ')
        + '</div>';
    } else if (selection?.loadError) {
      evidence = muted(copy('Không tải được điểm vai trò từ máy chủ. Hãy thử tải lại Dashboard.', 'Unable to load the role score from the server. Reload the Dashboard and try again.'));
    } else if (selection?.limitations?.length) {
      evidence = selection.limitations.map(item => muted(item.message ?? item.code)).join('');
    }
  } else {
    scores = '<div class="project-skills"><h3>' + escape(t('profile.verifiedHeading')) + '</h3>'
      + tags([...new Set(data.scores.filter(item => reportBackedSkillScore(item) !== null)
        .map(item => item.technology))], 'green')
      + '<h3>' + escape(t('profile.supplementary')) + '</h3>' + tags(data.skills.map(item => item.skill_name), 'blue') + '</div>';
    evidence = '<h3>' + escape(t('profile.self')) + '</h3><form id="skill-form" class="skill-form" novalidate>'
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

const radarCriterionNames = {
  source_change:['Thay đổi tệp mã nguồn','Source file changes'],
  framework_source:['Thay đổi tệp có bằng chứng framework','Changes to framework source files'],
  service_design:['Tệp API / worker','API / worker files'],
  data_design:['Tệp tích hợp dữ liệu / schema','Data integration / schema files'],
  structure_design:['Tệp trong cấu trúc đã phát hiện','Files in detected architecture structure'],
  test_change:['Thay đổi tệp kiểm thử','Test file changes'],
  test_config:['Thay đổi cấu hình kiểm thử','Test configuration changes'],
  authored_pr:['PR do người dùng tạo','Authored pull request'],
  merged_pr:['PR của người dùng đã merge','Merged authored pull request'],
  peer_review:['Review PR của người khác','Review on another contributor’s PR'],
  workflow_change:['Thay đổi cấu hình workflow CI','CI workflow configuration changes'],
  completed_check:['Check đã hoàn tất trên PR của người dùng','Completed check on authored PR']
};

function getLiveRadar(state, data) {
  const availableRepos = data.dashboardRepos ?? data.repos;
  const analyzedRepos = availableRepos.filter(repo =>
    Boolean(data.repoData?.[repo.id]?.report?.id || data.repoData?.[repo.id]?.report?.report_id)
  );
  const analyzedIds = new Set(analyzedRepos.map(repo => repo.id));
  const activeRepo = data.repos.find(repo => String(repo.id) === String(state.repo)) ?? data.repos[0];
  const activeRepoAnalyzed = activeRepo ? analyzedIds.has(activeRepo.id) : false;
  const metrics = analyzedRepos.length
    ? githubRadarMetrics(data.dashboardRadar ?? []).map(item => ({...item,
      label:item.key === 'architecture' ? copy('Kiến trúc','Architecture') : t('metric.' + item.key)}))
    : [];
  const metricDetails = metrics.map(item => {
    const entries = item.criteria.map(criterion => {
      const label = radarCriterionNames[criterion.key] ?? [criterion.key,criterion.key];
      const ref = criterion.evidence;
      const repo = ref && availableRepos.find(r => r.id === ref.repository_id);
      const tab = ref?.kind === 'collaboration' ? 'collab' : 'ownership';
      return '<li><strong>' + escape(copy(...label)) + '</strong> '
        + '<span class="tag-badge ' + (ref ? 'green' : 'yellow') + '">'
        + escape(ref ? copy('Đã ghi nhận','Observed') : copy('Chưa có minh chứng','Not observed')) + '</span>'
        + (ref ? muted((ref.kind === 'collaboration' ? 'PBI-014' : 'PBI-013') +
          ' #' + ref.evidence_id + ' · ' + (ref.target || '') + (ref.path ? ' · ' + ref.path : '')
          + (ref.finding_id ? ' · PBI-012 #' + ref.finding_id : '')
          + ' · ' + copy('Báo cáo #','Report #') + ref.report_id) : '')
        + (repo ? btn(escape(repo.full_name || repo.name), 'metric-evidence', 'secondary small',
          attr('id', repo.id) + attr('tab', tab)) : '') + '</li>';
    }).join('');
    return '<section id="radar-detail-' + item.key + '" class="radar-insight"'
      + ' aria-labelledby="radar-label-' + item.key + '" hidden>'
      + '<div class="radar-insight-head"><h3 id="radar-label-' + item.key + '">'
      + escape(item.label) + '</h3><b>'
      + (item.score === null ? '—' : number(item.score) + '<small>%</small>') + '</b></div>'
      + paragraph(copy('Đã ghi nhận ', 'Observed ') + item.observed + '/' + item.total
        + copy(' tiêu chí minh chứng. Không phải điểm thành thạo.', ' evidence criteria. Not proficiency.'))
      + '<ul class="audit-list">' + entries + '</ul>'
      + muted(copy('Rubric đề xuất, chưa hiệu chuẩn: ', 'Proposed, uncalibrated rubric: ') + RADAR_RUBRIC_VERSION)
      + (['testing','collaboration','ci'].includes(item.key) ? muted(copy(
        'Nếu thiếu dữ liệu, mở repository và chạy phân tích PR, Review và CI hoặc phân tích lại mã nguồn.',
        'If evidence is missing, open a repository and analyze PRs, reviews and CI or reanalyze code.')) : '')
      + '<div class="radar-next-actions">'
      + btn(icon('bot') + escape(t('radar.askMetric')), 'ask-metric', 'secondary small',
        attr('id', item.key)) + '</div></section>';
  }).join('');
  return {metrics, comparison:{}, metricDetails, count:analyzedRepos.length,
    analyzedRepos, activeRepo, activeRepoAnalyzed};
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
    + (radar.analyzedRepos?.length > 0 ? '<div class="dashboard-analyzed-chips">'
      + '<span class="analyzed-chips-label">' + icon('repo') + ' ' + copy('Repository đã phân tích:', 'Analyzed repositories:') + '</span>'
      + '<div class="analyzed-chips-list">'
      + radar.analyzedRepos.map(r => '<span class="repo-chip-badge" title="' + escape(r.full_name || r.name) + '">' + icon('branch') + ' ' + escape(r.full_name || r.name) + '</span>').join('')
      + '</div></div>' : '')
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
      'Radar đo độ phủ tiêu chí minh chứng GitHub đã ghi nhận trong phạm vi ' + scopeLabel(state.scope) + ' (' + rangeLabel(state.range) + '). Trục chưa đủ dữ liệu sẽ hiển thị dấu —, không coi là 0 điểm. Đây không phải điểm thành thạo; điểm kỹ năng và vai trò vẫn hiển thị riêng bên dưới. Chọn repository để mở báo cáo chi tiết tại trang <em>Phân tích GitHub</em>.',
      'The Radar measures observed GitHub evidence criterion coverage for scope ' + scopeLabel(state.scope) + ' (' + rangeLabel(state.range) + '). Missing axes display —, not zero. This is not proficiency; skill and role scores remain separate below. Select a repository to inspect its report under <em>GitHub Analysis</em>.'
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
    + radarView(radar.metrics, radar.count, scopeLabel(state.scope), rangeLabel(state.range), radar.comparison, radar.metricDetails, true)
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
    + '<form class="field-row" id="repo-search" novalidate>' + field(copy('Tìm repository', 'Find repository'), '<input name="repo-query" value="'
      + escape(data.search) + '">')
    + '<button class="button secondary" type="submit">' + escape(copy('Tìm', 'Search')) + '</button>'
    + (data.search ? btn(icon('close') + ' ' + copy('Xóa bộ lọc', 'Clear search'), 'clear-repo-search', 'quiet small') : '')
    + '</form>'
    + '<p class="scope-summary" role="status">' + escape(t('repos.count', { count: data.total })) + '</p>'
    + renderAnalysisFeedback(data.analysisOutcome, getLanguage())
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

  let pageButtons = '';
  if (totalPages <= 5) {
    for (let p = 1; p <= totalPages; p++) {
      pageButtons += namedButton(String(p), 'repo-page', 'small' + (p === currentPage ? ' primary repo-page-active' : ' quiet'), p);
    }
  } else {
    pageButtons += namedButton('1', 'repo-page', 'small' + (1 === currentPage ? ' primary repo-page-active' : ' quiet'), 1);
    if (currentPage > 3) pageButtons += '<span class="repo-page-dots">…</span>';
    const start = Math.max(2, currentPage - 1);
    const end = Math.min(totalPages - 1, currentPage + 1);
    for (let p = start; p <= end; p++) {
      pageButtons += namedButton(String(p), 'repo-page', 'small' + (p === currentPage ? ' primary repo-page-active' : ' quiet'), p);
    }
    if (currentPage < totalPages - 2) pageButtons += '<span class="repo-page-dots">…</span>';
    pageButtons += namedButton(String(totalPages), 'repo-page', 'small' + (totalPages === currentPage ? ' primary repo-page-active' : ' quiet'), totalPages);
  }

  const pages = '<div class="repo-pagination-bar">'
    + '<div class="repo-page-nav">'
    + (currentPage > 1 ? namedButton('«', 'repo-page', 'quiet small', 1, 'title="' + escape(copy('Trang đầu', 'First page')) + '"') : '')
    + (currentPage > 1 ? namedButton('‹', 'repo-page', 'quiet small', currentPage - 1, 'title="' + escape(copy('Trang trước', 'Previous page')) + '"') : '')
    + '<div class="repo-page-numbers">' + pageButtons + '</div>'
    + (currentPage < totalPages ? namedButton('›', 'repo-page', 'quiet small', currentPage + 1, 'title="' + escape(copy('Trang sau', 'Next page')) + '"') : '')
    + (currentPage < totalPages ? namedButton('»', 'repo-page', 'quiet small', totalPages, 'title="' + escape(copy('Trang cuối', 'Last page')) + '"') : '')
    + '</div>'
    + (totalPages > 1 ? '<div class="repo-page-jump">'
      + '<label><small>' + copy('Đến:', 'Go:') + '</small> '
      + '<select class="repo-page-select-styled" data-act="repo-page-select">' + pageOptions + '</select></label>'
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

function renderCustomPicker(label, currentId, currentLabel, items, action, glyph = 'file', copy) {
  const displayText = currentLabel || (copy ? copy('Chọn…', 'Select…') : 'Chọn…');
  const title = '<span class="filter-glyph">' + icon(glyph) + '</span>'
    + '<span class="filter-value">' + escape(displayText) + '</span>'
    + '<span class="filter-chevron" aria-hidden="true"></span>';
  const menuItems = items.map(item => {
    const isSelected = String(item.id) === String(currentId);
    return '<button type="button" class="filter-option" data-act="' + action + '" data-id="' + escape(item.id) + '" aria-pressed="' + isSelected + '">'
      + '<span>' + escape(item.title) + '</span>'
      + (isSelected ? icon('check') : '')
      + '</button>';
  }).join('');

  return '<div class="filter-field cv-filter-field">'
    + '<span class="filter-label">' + escape(label) + '</span>'
    + '<details class="filter-dropdown cv-picker-dropdown">'
    + '<summary class="filter-trigger" aria-label="' + escape(label + ': ' + displayText) + '">' + title + '</summary>'
    + '<div class="filter-menu" role="group" aria-label="' + escape(label) + '">'
    + (items.length > 0
      ? menuItems
      : '<div class="cv-picker-empty" style="padding:8px 12px;font-size:12px;color:var(--muted)">' + (copy ? copy('Chưa có dữ liệu', 'No items yet') : 'Chưa có dữ liệu') + '</div>')
    + '</div>'
    + '</details>'
    + '</div>';
}

export function liveRoadmap(data) {
  const { milestones, done, next, goal } = progressOverview(data);
  const busy = data.busy.has('road');
  const loading = action => busy && data.roadAction === action;
  const disabled = busy ? ' disabled' : '';
  const busyAttr = action => disabled + (loading(action) ? ' aria-busy="true"' : '');
  const busyStyle = (style, action) => style + (loading(action) ? ' is-loading' : '');
  const roadButton = (label, act, style, action, attributes='') =>
    btn(label, act, busyStyle(style, action), attributes + busyAttr(action));
  const nodeState = m => m.status === 'completed' ? 'done' : m.status === 'in_progress' ? 'in-progress' : 'ready';
  const nodeIcon = m => m.status === 'completed' ? 'check' : m.status === 'in_progress' ? 'play' : 'branch';
  const suggestionText = suggestion => suggestion?.action === 'complete'
    ? copy('Minh chứng đã xác minh đáp ứng yêu cầu của mốc.', 'Verified evidence meets the milestone requirements.')
    : suggestion?.explanation || '';
  const selected = milestones.find(m => m.id === data.milestone) ?? milestones[0];
  const item = data.road?.milestones?.find(m =>
    String(m.skill || '').toLowerCase() === String(selected?.external_key || '').toLowerCase()
  ) ?? (selected ? {
    objective: selected.title,
    metric: copy('Hoàn thành mục tiêu của cột mốc này và nộp minh chứng.', 'Complete the objective of this milestone and submit evidence.'),
    evidence: selected.evidence || []
  } : null);
  const goalEntries = [
    ['backend', 'Backend'], ['frontend', 'Frontend'], ['fullstack', 'Full-stack'], ['devops', 'DevOps']
  ];
  const currentGoalLabel = goalEntries.find(([k]) => k === data.goal)?.[1] || 'Backend';
  const picker = renderCustomPicker(
    t('road.goal'),
    data.goal,
    currentGoalLabel,
    goalEntries.map(([key, label]) => ({ id: key, title: label })),
    'road-goal-select',
    'branch',
    copy
  );
  const roadPicker = (data.roadmaps && data.roadmaps.length > 1)
    ? renderCustomPicker(
        copy('Đổi lộ trình', 'Switch roadmap'),
        data.road?.id,
        data.road ? `${displayRoadmapTitle(data.road.title, data.road.goal)} (#${data.road.id})` : undefined,
        data.roadmaps.map(r => ({ id: r.id, title: `${displayRoadmapTitle(r.title, r.goal)} (#${r.id})` })),
        'road-select-option',
        'repo',
        copy
      )
    : '';

  if (data.busy.has('road') && data.roadmaps === undefined) {
    return heading(t('road.heading'), t('road.intro')) + '<div class="road-pickers-row">' + picker + roadPicker + '</div>' + roadmapLoadingSkeleton();
  }

  const map = milestones.map(milestone => '<button type="button" class="node" data-act="milestone"' + attr('id', milestone.id)
    + attr('state', nodeState(milestone)) + ' aria-pressed="' + (milestone === selected) + '">'
    + '<span class="map-icon">' + icon(nodeIcon(milestone)) + '</span><strong>'
    + escape(displayMilestoneTitle(milestone.title, milestone.external_key)) + '</strong><small>' + escape(statusLabel(milestone.status)) + '</small></button>').join('');

  const historyNote = record => {
    const note = String(record.note || '');
    if (record.source === 'suggestion' && /^Applied suggestion/.test(note)) return note.replace('Applied suggestion',copy('Đã áp dụng đề xuất','Applied suggestion')).replace(' from snapshot ',copy(' từ snapshot ',' from snapshot '));
    return note.replace(/^\[SELF_REPORTED\]/,copy('[Tự khai báo]','[Self-reported]')).replace(/^\[VERIFIED\]/,copy('[Đã xác minh lúc nộp]','[Verified at submission]'));
  };
  const sourceLabel = src => ({
    manual: copy('Thủ công', 'Manual'),
    mentor: copy('Đề xuất AI Mentor', 'AI Mentor proposal'),
    suggestion: copy('Đề xuất hệ thống', 'System suggestion'),
    submission: copy('Nộp minh chứng', 'Evidence submission'),
    verified: copy('Xác minh Git', 'Git verified')
  })[src] ?? src;

  const history = '<details class="panel road-history"' + (data.historyLoaded || loading('history') ? ' open' : '') + '><summary>' + escape(t('road.history')) + '</summary>'
    + roadButton(escape(copy('Tải lịch sử', 'Load history')), 'road-history', 'quiet small', 'history') + '<ul class="audit-list">'
    + data.history.map(record => '<li><time>' + escape(formattedDate(record.created_at)) + '</time>'
      + '<span>' + escape(statusLabel(record.old_status) + ' → ' + statusLabel(record.new_status)) + '</span>'
      + (record.source ? ' ' + badge(sourceLabel(record.source), record.source === 'verified' ? 'green' : record.source === 'mentor' ? 'blue' : '') : '')
      + (record.note ? '<div class="history-note-text"><small>' + escape(historyNote(record)) + '</small></div>' : '')
      + '</li>').join('') + '</ul>' + (data.historyLoaded && !data.history.length ? muted(copy('Chưa có hoạt động nào được ghi nhận cho mốc này.', 'No activity has been recorded for this milestone.')) : '') + '</details>';

  const evaluation = data.reevaluation;
  const evaluationSuggestions = currentEvaluationSuggestions(evaluation, data.tracking);
  const pending = evaluation ? [] : (data.tracking?.suggestions.filter(
    suggestion => suggestion.state === 'pending' && suggestion.milestone_id === selected?.id
  ) ?? []);

  const staleEvaluation = evaluation && data.tracking?.suggestions?.some(s => s.snapshot_id === evaluation.snapshotId && s.state === 'stale');
  const resolvedEvaluation = evaluation?.kind === 'suggestions' && !evaluationSuggestions.length && !staleEvaluation;
  const evaluationTitle = staleEvaluation ? copy('Kết quả đánh giá đã cũ', 'Evaluation is outdated') : resolvedEvaluation ? copy('Đã xử lý tất cả đề xuất', 'All suggestions resolved') : evaluation?.kind === 'suggestions'
    ? copy('Đã tìm thấy bằng chứng GitHub xác minh hợp lệ', 'Verified GitHub evidence found')
    : evaluation?.kind === 'no-verified-evidence'
      ? copy('Chưa có bằng chứng GitHub được xác minh', 'No verified GitHub evidence yet')
      : evaluation?.kind === 'all-completed'
        ? copy('Các mốc hiện tại đều đã hoàn thành', 'All milestones are already completed')
        : copy('Chưa có mốc mới đáp ứng đủ điều kiện', 'No additional milestones meet the criteria');
  const evaluationDescription = !evaluation ? '' : staleEvaluation ? copy('Dữ liệu phân tích đã thay đổi. Hãy đánh giá lại trước khi áp dụng đề xuất.', 'Analysis data changed. Re-evaluate before applying suggestions.') : resolvedEvaluation ? copy('Không còn đề xuất đang chờ. Bạn có thể đánh giá lại khi có dữ liệu phân tích mới.', 'No pending suggestions remain. Re-evaluate when new analysis is available.') : evaluation.kind === 'suggestions'
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
      + '<p class="subtle">' + escape(suggestionText(suggestion)) + '</p>'
      + '<div class="action-row">'
      + roadButton(escape(copy('Áp dụng', 'Apply')), 'road-suggestion', 'primary small', 'suggestion:' + suggestion.id + ':apply', attr('id', suggestion.id) + attr('decision', 'apply'))
      + roadButton(escape(copy('Bỏ qua', 'Dismiss')), 'road-suggestion', 'secondary small', 'suggestion:' + suggestion.id + ':reject', attr('id', suggestion.id) + attr('decision', 'reject'))
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
          + '<span class="milestone-proof-tick" aria-hidden="true">' + icon(ev.verified ? 'check' : 'file') + '</span>'
          + '<a href="' + escape(ev.url) + '" title="' + escape(ev.url)
          + '" target="_blank" rel="noopener noreferrer">' + escape(label) + '</a>'
          + '<small>' + escape(ev.verified
            ? copy('Đã xác minh', 'Verified')
            : copy('Tự khai báo', 'Self-reported')) + '</small>' + (ev.note ? '<p class="evidence-subnote">' + escape(ev.note) + '</p>' : '') + '</li>';
      }).join('') + '</ul>'
      : '<p class="milestone-proof-empty">'
        + escape(copy('Chưa có liên kết bằng chứng được nộp.', 'No evidence links submitted yet.'))
        + '</p>')
    + '<small class="milestone-proof-help">'
    + escape(copy('Chỉ minh chứng đáp ứng tiêu chí năng lực mới được xác minh.', 'Only evidence meeting skill criteria is verified.'))
    + '</small></div>';
  const assessmentRefs = Array.isArray(item?.evidence)
    ? item.evidence.filter(ref => ref && typeof ref === 'object' && ref.source !== 'submission' && !ref.url && !ref.evidence_url)
    : [];
  const assessmentRefsHtml = assessmentRefs.length
    ? '<details class="milestone-analysis-refs"><summary>'
      + escape(copy('Tham chiếu phân tích năng lực', 'Skill assessment references'))
      + '</summary>' + refs(assessmentRefs, data) + '</details>'
    : '';

  const isCompleted = selected?.status === 'completed';
  const evidenceDraft = data.roadEvidenceDraft?.roadId === data.road?.id
    && data.roadEvidenceDraft?.milestoneId === selected?.id ? data.roadEvidenceDraft : null;
  const evidenceNotice = data.roadNotice ? '<div class="notice road-evidence-result' + (data.roadNotice.verified ? ' green' : '') + '" role="status"><strong>'
    + escape(data.roadNotice.title) + '</strong><p>' + escape(data.roadNotice.detail) + '</p>'
    + (data.roadNotice.verified ? '' : '<a class="button secondary small" href="#studio/repos">' + escape(copy('Đến phân tích GitHub','Go to GitHub analysis')) + '</a>') + '</div>' : '';
  const evidenceFormHtml = selected ? '<form class="stack road-evidence-form" id="milestone-evidence-form" data-milestone="' + selected.id + '" novalidate>'
    + '<input type="hidden" name="milestone_id" value="' + selected.id + '">'
    + '<h4>' + icon('pulse') + ' ' + (isCompleted ? copy('Bổ sung thêm minh chứng', 'Submit additional evidence') : copy('Nộp minh chứng hoàn thành mốc', 'Submit milestone evidence')) + '</h4>'
    + '<p class="subtle">' + (isCompleted
      ? copy('Cột mốc này đã hoàn thành. Bạn có thể nộp thêm liên kết Commit/PR để làm phong phú bằng chứng cho portfolio và CV.', 'This milestone is completed. You can submit more Commit/PR links to enrich your evidence.')
      : copy('Chỉ nộp URL HTTPS trực tiếp đến Commit hoặc Pull Request trên github.com. Link Issue hoặc trang repository sẽ bị từ chối.', 'Submit only direct HTTPS GitHub Commit or Pull Request URLs. Issue and repository page links are rejected.')) + '</p>'
    + '<div class="field-row">'
    + '<input name="evidence_url" type="url" aria-describedby="road-evidence-validation" placeholder="https://github.com/owner/repo/pull/123" maxlength="2000" value="' + escape(evidenceDraft?.url || '') + '"' + disabled + ' required>'
    + '<input name="evidence_note" maxlength="2000" placeholder="' + copy('Ghi chú (tùy chọn)', 'Short note (optional)') + '" value="' + escape(evidenceDraft?.note || '') + '"' + disabled + '>'
    + '<button type="submit" class="button primary small' + (loading('evidence') ? ' is-loading' : '') + '"' + busyAttr('evidence') + '>' + copy('Nộp minh chứng', 'Submit') + '</button>'
    + '</div><p id="road-evidence-validation" class="road-evidence-validation" role="alert" hidden></p></form>' : '';

  const statusButton = (label, style, status) => roadButton(label, 'road-status', style, 'status:' + selected.id + ':' + status, attr('id', selected.id) + attr('status', status));
  let actionButtonsHtml = '';
  if (selected) {
    if (selected.status === 'completed') {
      actionButtonsHtml = statusButton(icon('arrow') + ' ' + copy('Mở lại mốc này (Chuyển về Đang thực hiện)', 'Reopen milestone (In progress)'), 'secondary small', 'in_progress');
    } else if (selected.status === 'in_progress') {
      actionButtonsHtml = statusButton(icon('check') + ' ' + copy('Xác nhận đã hoàn thành', 'Mark as completed'), 'primary small', 'completed')
        + statusButton(copy('Quay lại: Chưa bắt đầu', 'Revert to Pending'), 'quiet small', 'pending');
    } else {
      actionButtonsHtml = statusButton(icon('play') + ' ' + copy('Bắt đầu thực hiện mốc này', 'Start this milestone'), 'primary small', 'in_progress')
        + statusButton(icon('check') + ' ' + copy('Đánh dấu đã hoàn thành', 'Mark as completed'), 'secondary small', 'completed');
    }
  }

  const detailTitle = selected ? displayMilestoneTitle(selected.title, selected.external_key) : '';
  const detailObjective = item ? displayObjective(item.objective, selected?.external_key) : '';
  const detailMetric = item ? displayMetric(item.metric, selected?.external_key) : '';

  const detail = selected && item ? '<article class="panel road-detail" id="milestone-detail"><div class="detail-top">'
    + badge(statusLabel(selected.status), selected.status === 'completed' ? 'green' : selected.status === 'in_progress' ? 'blue' : '') + (isCompleted ? badge(selected.verification_status === 'verified' ? copy('Đã xác minh năng lực', 'Skill verified') : copy('Chưa xác minh năng lực', 'Skill not verified'), selected.verification_status === 'verified' ? 'green' : 'amber') : '') + '</div>'
    + '<h2>' + escape(detailTitle) + '</h2>' + paragraph(detailObjective)
    + '<div class="milestone-proof"><span class="feature-icon">' + icon('award') + '</span><div><h3>'
    + escape(t('road.proof')) + '</h3>' + paragraph(detailMetric) + proofLinksHtml + '</div></div>'
    + assessmentRefsHtml
    + evidenceFormHtml + evidenceNotice
    + '<div class="action-row" style="margin-top:14px">'
    + actionButtonsHtml
    + btn(icon('bot') + ' ' + copy('Hỏi AI Mentor về mốc này', 'Ask AI Mentor about this milestone'), 'ask-milestone', 'secondary small', attr('id', selected.id) + attr('title', detailTitle)) + '</div>'
    + pending.map(suggestion => '<div class="notice">' + paragraph(suggestionText(suggestion))
      + ['apply', 'reject'].map(decision => roadButton(escape(decision === 'apply' ? copy('Áp dụng', 'Apply') : copy('Bỏ qua', 'Dismiss')), 'road-suggestion', 'secondary small', 'suggestion:' + suggestion.id + ':' + decision, attr('id', suggestion.id) + attr('decision', decision))).join('') + '</div>').join('') + '</article>' : '';
  return heading(t('road.heading'), t('road.intro')) + '<div class="road-pickers-row">' + picker + roadPicker + '</div>' + (data.errors.road || data.messages.road || loading('load') ? feedback(data, 'road') : '')
    + '<div class="road-banner"><section class="panel road-next"><div><p class="eyebrow">' + escape(t('road.next')) + '</p><h2>'
    + escape(next ? displayMilestoneTitle(next.title, next.external_key) : (data.road ? t('road.finished') : copy('Chưa có lộ trình', 'No roadmap yet'))) + '</h2>'
    + (goal ? paragraph(displayObjective(goal.objective, next?.external_key)) : '') + '</div>'
    + roadButton(escape(copy('Tạo lộ trình', 'Generate roadmap')), 'road-create', 'primary', 'create') + '</section>'
    + '<section class="panel road-progress"><div><p class="eyebrow">' + escape(t('road.progress')) + '</p><strong>' + done.length + '<span> / ' + milestones.length
    + '</span></strong><p>' + escape(t('road.progressCount', { done: done.length, total: milestones.length })) + '</p></div>'
    + '<div class="milestone-pips" aria-hidden="true">' + milestones.map(m => '<i' + attr('state', nodeState(m)) + '></i>').join('') + '</div></section></div>'
    + (data.road ? '<section class="road-update"><div>' + icon('pulse') + escape(copy('Cập nhật từ kết quả phân tích GitHub', 'Recheck GitHub evidence')) + '</div>'
      + roadButton(escape(copy('Đánh giá lại', 'Re-evaluate')), 'road-draft', 'secondary small', 'reevaluate') + '</section>' : '')
    + evaluationHtml
    + '<div class="road-layout"><section class="panel map-panel">' + panelHead(t('road.map'), copy('Chọn mốc để xem mục tiêu và bằng chứng.', 'Select a milestone to see its goal and evidence.'))
    + '<div class="map-legend">' + [['done',copy('Hoàn thành','Completed')],['in-progress',copy('Đang thực hiện','In progress')],['ready',copy('Chưa bắt đầu','Pending')]].map(([mode,label]) => '<span data-state="' + mode + '"><i></i>' + escape(label) + '</span>').join('') + '</div>'
    + (map ? '<div class="road-map"><svg class="road-map-lines" aria-hidden="true" focusable="false"></svg><canvas aria-hidden="true"></canvas>' + map + '</div>' : muted(copy('Chưa có cột mốc để hiển thị.', 'No milestones to display.')))
    + '</section>' + detail + (selected ? '<div class="road-records stack">'
      + (done.length ? '<section class="panel achievements">' + panelHead(t('road.trophies')) + '<div class="award-list">'
        + done.map(m => '<button class="award-card" type="button" data-act="milestone"' + attr('id', m.id) + '><span class="award-icon">'
          + icon('award') + '</span><span><strong>' + escape(displayMilestoneTitle(m.title, m.external_key)) + '</strong><small>'
          + escape(m.verification_status === 'verified' ? copy('Đã xác minh Git', 'Git Verified') : copy('Hoàn thành / chưa xác minh', 'Completed / not verified'))
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
    + '<form id="job-search" class="field-row" novalidate>' + field(t('jobs.keyword'), '<input name="query" value="' + escape(data.jobQuery ?? '')
      + '" maxlength="200" placeholder="Python, FastAPI, TypeScript" required>')
    + '<button class="button secondary' + (data.busy.has('jobs') ? ' is-loading' : '') + '" type="submit"' + (data.busy.has('jobs') ? ' disabled' : '') + '>' + escape(t('jobs.searchAction')) + '</button></form>'
    + '<div class="rows view-rows">' + (data.jobResults?.warnings ?? []).map(muted).join('')
    + (rows || (data.jobResults ? muted(t('jobs.noMatch')) : '')) + '</div></article>'
    + '<article class="panel">' + panelHead(t('jobs.paste')) + '<form id="jd-form" class="stack" novalidate>'
    + field(t('jobs.description'), '<textarea name="jd" id="jd-textarea" rows="4" maxlength="50000" class="auto-scale-textarea" placeholder="' + escape(t('jobs.placeholder'))
      + '">' + escape(data.jobText ?? '') + '</textarea>')
    + field(copy('Hoặc URL tuyển dụng', 'Or listing URL'), '<input name="jd-url" type="url" value="' + escape(data.jobURL ?? '') + '">')
    + '<button class="button primary' + (data.busy.has('jobs') ? ' is-loading' : '') + '" type="submit"' + (data.busy.has('jobs') ? ' disabled' : '') + '>' + escape(t('jobs.analyze')) + '</button></form></article></div>'
    + '<article class="panel">' + panelHead(t('jobs.compare'), scopeLabel(state.scope))
    + (comparisonHtml || (data.busy.has('jobs') ? '<div class="ita-compare-skeleton" role="status"><span class="ita-visually-hidden">' + escape(copy('Đang đối chiếu yêu cầu công việc…', 'Matching job requirements…')) + '</span><span class="ita-skeleton-line ita-skeleton-line--wide" aria-hidden="true"></span><span class="ita-skeleton-meter" aria-hidden="true"></span><span class="ita-skeleton-line" aria-hidden="true"></span><span class="ita-skeleton-line ita-skeleton-line--short" aria-hidden="true"></span></div>' : blank(t('jobs.none'), t('jobs.noneCopy')))) + '</article></div>';
}

function renderStructuredSections(structured, copy, escape, activeSecIdx) {
  if (!structured || !Array.isArray(structured.sections) || !structured.sections.length) {
    return '<div class="cv-struct-empty cv-struct-container">'
      + '<div class="cv-empty-state">'
      + '<span class="cv-empty-icon" aria-hidden="true">📄</span>'
      + '<strong>' + escape(copy(
          'CV của bạn chưa có nội dung',
          'Your CV has no sections yet'
        )) + '</strong>'
      + '<p>' + escape(copy(
          'Chọn một mục bên dưới để bắt đầu xây dựng hồ sơ.',
          'Choose a section below to start building your resume.'
        )) + '</p>'
      + '</div>'
      + '<div class="cv-add-sec-bar">'
      + '<button type="button" class="button secondary small" data-act="cv-add-section" data-type="Experience">💼 ' + copy('Kinh nghiệm', 'Experience') + ' <span aria-hidden="true">＋</span></button>'
      + '<button type="button" class="button secondary small" data-act="cv-add-section" data-type="Projects">🚀 ' + copy('Dự án', 'Projects') + ' <span aria-hidden="true">＋</span></button>'
      + '<button type="button" class="button secondary small" data-act="cv-add-section" data-type="Skills">⚡ ' + copy('Kỹ năng', 'Skills') + ' <span aria-hidden="true">＋</span></button>'
      + '<button type="button" class="button secondary small" data-act="cv-add-section" data-type="Education">🎓 ' + copy('Học vấn', 'Education') + ' <span aria-hidden="true">＋</span></button>'
      + '</div></div>';
  }


  // FOCUSED SECTION VIEW (Chỉ mở form của section đang chọn)
  if (activeSecIdx !== null && activeSecIdx !== undefined && structured.sections[activeSecIdx]) {
    const sIdx = Number(activeSecIdx);
    const sec = structured.sections[sIdx];
    const secIcon = getSectionIcon(sec.title);
    const entriesHtml = (sec.entries || []).map((entry, eIdx) => {
      const delBtn = '<button type="button" class="cv-entry-del-btn" data-act="cv-del-entry" data-sec="' + sIdx + '" data-entry="' + eIdx + '" title="' + escape(copy('Xóa mục này', 'Remove entry')) + '">✕</button>';
      if (entry.type === 'dated') {
        return '<div class="cv-struct-entry" data-type="dated">'
          + '<div class="cv-struct-entry-header"><span class="cv-entry-num">#' + (eIdx + 1) + '</span>' + delBtn + '</div>'
          + '<div class="field-row">'
          + '<input class="cv-struct-field" data-sec="' + sIdx + '" data-entry="' + eIdx + '" data-field="date" placeholder="' + escape(copy('Thời gian (VD: 2022 - Hiện tại)', 'Date (e.g. 2022 - Present)')) + '" value="' + escape(entry.date || '') + '">'
          + '<input class="cv-struct-field" data-sec="' + sIdx + '" data-entry="' + eIdx + '" data-field="org" placeholder="' + escape(copy('Tên công ty / Cơ quan', 'Company / School')) + '" value="' + escape(entry.org || '') + '">'
          + '</div>'
          + '<div class="field-row">'
          + '<input class="cv-struct-field" data-sec="' + sIdx + '" data-entry="' + eIdx + '" data-field="role" placeholder="' + escape(copy('Chức danh / Vai trò', 'Role / Job title')) + '" value="' + escape(entry.role || '') + '">'
          + '<input class="cv-struct-field" data-sec="' + sIdx + '" data-entry="' + eIdx + '" data-field="loc" placeholder="' + escape(copy('Địa điểm (VD: TP. Hồ Chí Minh)', 'Location')) + '" value="' + escape(entry.loc || '') + '">'
          + '</div>'
          + '<textarea class="cv-struct-field cv-struct-bullets" data-sec="' + sIdx + '" data-entry="' + eIdx + '" data-field="bullets" rows="3" placeholder="' + escape(copy('Gạch đầu dòng kết quả / thành tựu (mỗi dòng một ý)...', 'Bullets / achievements (one per line)...')) + '">' + escape((entry.bullets || []).join('\n')) + '</textarea>'
          + '</div>';
      } else if (entry.type === 'labeled') {
        return '<div class="cv-struct-entry" data-type="labeled">'
          + '<div class="cv-struct-entry-header"><span class="cv-entry-num">#' + (eIdx + 1) + '</span>' + delBtn + '</div>'
          + '<input class="cv-struct-field" data-sec="' + sIdx + '" data-entry="' + eIdx + '" data-field="label" placeholder="' + escape(copy('Nhãn (VD: Kỹ năng:)', 'Label (e.g. Skills:)')) + '" value="' + escape(entry.label || '') + '">'
          + '<textarea class="cv-struct-field" data-sec="' + sIdx + '" data-entry="' + eIdx + '" data-field="content" rows="2" placeholder="' + escape(copy('Nội dung chi tiết...', 'Details...')) + '">' + escape(entry.content || '') + '</textarea>'
          + '</div>';
      } else {
        return '<div class="cv-struct-entry" data-type="text">'
          + '<div class="cv-struct-entry-header"><span class="cv-entry-num">#' + (eIdx + 1) + '</span>' + delBtn + '</div>'
          + '<textarea class="cv-struct-field" data-sec="' + sIdx + '" data-entry="' + eIdx + '" data-field="text" rows="3" placeholder="' + escape(copy('Nội dung chi tiết...', 'Section content...')) + '">' + escape(entry.text || '') + '</textarea>'
          + '</div>';
      }
    }).join('');

    return '<div class="cv-focused-sec-editor cv-struct-container">'
      + '<div class="cv-focused-sec-nav-bar">'
      + '<button type="button" class="button quiet small cv-nav-back-btn" data-act="cv-nav-back">'
      + '← ' + escape(copy('Quay lại danh sách mục', 'All Sections'))
      + '</button>'
      + '<button type="button" class="button danger-subtle small cv-del-sec-btn" data-act="cv-del-section" data-sec="' + sIdx + '" title="' + escape(copy('Xóa phần này khỏi CV', 'Delete section from CV')) + '">'
      + '🗑️ ' + copy('Xóa phần này', 'Delete section')
      + '</button>'
      + '</div>'
      + '<div class="cv-focused-sec-title">'
      + '<span class="cv-sec-icon">' + secIcon + '</span>'
      + '<input class="cv-struct-title cv-struct-field" data-sec="' + sIdx + '" value="' + escape(sec.title || '') + '" placeholder="' + escape(copy('Tên phần...', 'Section title...')) + '">'
      + '<span class="cv-sec-count-badge">' + (sec.entries?.length || 0) + ' ' + copy('mục', 'items') + '</span>'
      + '</div>'
      + '<div class="cv-struct-body">'
      + entriesHtml
      + '<div class="cv-sec-add-row">'
      + '<button type="button" class="button secondary small cv-add-entry-btn" data-act="cv-add-entry" data-sec="' + sIdx + '">+ ' + copy('Thêm mục', 'Add item') + '</button>'
      + '</div>'
      + '</div></div>';
  }

  // DEFAULT VIEW: Section Navigator (Reactive Resume v6 Layout)
  return '<div class="cv-sec-nav-wrap cv-struct-container">'
    + '<div class="cv-sec-nav-head">'
    + '<h4>' + copy('Mục nội dung CV', 'Resume Sections') + '</h4>'
    + '<small>' + copy('Chọn mục để chỉnh sửa chi tiết', 'Select section to edit') + '</small>'
    + '</div>'
    + '<div class="cv-sec-nav-container">'
    + structured.sections.map((sec, sIdx) => {
      const secIcon = getSectionIcon(sec.title);
      return '<div class="cv-struct-section cv-sec-nav-card" data-act="cv-open-sec" data-sec="' + sIdx + '">'
        + '<div class="cv-sec-nav-main">'
        + '<span class="cv-sec-icon">' + secIcon + '</span>'
        + '<div class="cv-sec-nav-text">'
        + '<strong class="cv-sec-nav-title">' + escape(sec.title || copy('Mục nội dung', 'Section')) + '</strong>'
        + '<span class="cv-sec-nav-meta">' + (sec.entries?.length || 0) + ' ' + copy('mục', 'items') + '</span>'
        + '</div></div>'
        + '<div class="cv-sec-nav-actions">'
        + '<button type="button" class="button secondary small cv-add-entry-btn" data-act="cv-add-entry" data-sec="' + sIdx + '" title="' + escape(copy('Thêm mục vào phần này', 'Add item')) + '">+ ' + copy('Thêm mục', 'Add item') + '</button>'
        + '<button type="button" class="button quiet small cv-open-sec-btn" data-act="cv-open-sec" data-sec="' + sIdx + '">' + copy('Sửa →', 'Edit →') + '</button>'
        + '<button type="button" class="button quiet small cv-del-sec-btn" data-act="cv-del-section" data-sec="' + sIdx + '" title="' + escape(copy('Xóa phần này khỏi CV', 'Delete section')) + '">✕</button>'
        + '</div></div>';
    }).join('')
    + '</div>'
    + '<div class="cv-add-sec-bar">'
    + '<span class="cv-add-sec-label">' + copy('+ Thêm phần:', '+ Add section:') + '</span>'
    + '<button type="button" class="button secondary small" data-act="cv-add-section" data-type="Experience">💼 ' + copy('Kinh nghiệm', 'Experience') + '</button>'
    + '<button type="button" class="button secondary small" data-act="cv-add-section" data-type="Projects">🚀 ' + copy('Dự án', 'Projects') + '</button>'
    + '<button type="button" class="button secondary small" data-act="cv-add-section" data-type="Skills">⚡ ' + copy('Kỹ năng', 'Skills') + '</button>'
    + '<button type="button" class="button secondary small" data-act="cv-add-section" data-type="Education">🎓 ' + copy('Học vấn', 'Education') + '</button>'
    + '</div></div>';
}

export function liveCV(state, runtime, data) {
  const { cv } = data;
  const doc = data.document;
  const draft = runtime.cvDraft;
  const busy = data.busy.has('cv');
  const select = (label, id, options) => field(label, '<select id="' + id + '"><option value="">'
    + escape(copy('Chọn…', 'Select…')) + '</option>' + options + '</select>');
  const customPicker = (label, currentId, currentLabel, items, action, glyph = 'file') =>
    renderCustomPicker(label, currentId, currentLabel, items, action, glyph, copy);
  const ats = data.ats;
  const references = data.references;

  const editorMode = data.editorMode || 'structured';
  const intelTab = data.intelTab || 'design';
  const zoom = data.zoomLevel || 'fit';
  const hasMentor = (typeof document !== 'undefined' && (document.body?.classList.contains('has-mentor') || document.querySelector('.workspace-body')?.classList.contains('has-mentor'))) || Boolean(runtime.mentorOpen);
  const intelExplicitOpen = data.rightPanelExplicitOpen === true;
  const intelCollapsed = hasMentor ? !intelExplicitOpen : (data.rightPanelCollapsed !== undefined ? Boolean(data.rightPanelCollapsed) : false);

  const normalize = s => (s || '').replace(/\r\n/g, '\n').trim();
  const isSaved = doc && (draft.name || '').trim() === (doc.title || '').trim() && normalize(draft.body) === normalize(doc.lines.map(l => l.text).join('\n'));
  let saveStatusBadge = '';
  if (doc) {
    saveStatusBadge = isSaved
      ? '<span class="status-pill green">' + icon('check') + ' ' + copy('Đã lưu bản mới nhất (#' + doc.number + ')', 'Saved latest (#' + doc.number + ')') + '</span>'
      : '<span class="status-pill amber">' + icon('pulse') + ' ' + copy('Bản nháp có thay đổi chưa lưu', 'Unsaved draft changes') + '</span>';
  } else if (cv) {
    saveStatusBadge = '<span class="status-pill green">' + icon('check') + ' ' + copy('Đã tải lên CV #' + cv.id, 'Uploaded CV #' + cv.id) + '</span>';
  } else if (!draft.body.trim()) {
    saveStatusBadge = '<span class="status-pill subtle">' + icon('file') + ' ' + copy('Bản nháp mới', 'New draft') + '</span>';
  } else {
    saveStatusBadge = '<span class="status-pill amber">' + icon('pulse') + ' ' + copy('Bản nháp chưa lưu', 'Unsaved draft') + '</span>';
  }

  // CV Top Toolbar (Reactive Resume v6 Style)
  const cvDocTitle = doc ? doc.title : (draft.name ? draft.name + ' - CV' : copy('Bản CV mới', 'New CV'));
  const cvCommandBar = '<section class="panel cv-command-bar cv-top-toolbar" aria-label="' + copy('Thanh công cụ CV', 'CV Action Bar') + '">'
    + '<div class="cv-command-inner">'
    + '<div class="cv-command-status">'
    + '<span class="cv-toolbar-doc-icon">📄</span>'
    + '<div class="cv-toolbar-title-wrap">'
    + '<span class="cv-toolbar-title" title="' + escape(copy('Tiêu đề CV', 'CV Title')) + '">' + escape(cvDocTitle) + '</span>'
    + '</div>'
    + saveStatusBadge
    + (doc && data.versions?.length ? '<span class="cv-command-sep">·</span><span class="cv-version-tag">' + copy('Phiên bản: ', 'Version: ') + '<strong>#' + doc.number + '</strong></span>' : '')
    + '<small class="cv-command-doc-info" style="display:none">' + (doc ? escape(doc.title) : 'draft') + '</small>'
    + '</div>'
    + '<div class="cv-command-actions">'
    + btn(icon('pulse') + ' ' + escape(copy('Chèn từ Git', 'Git Skills')), 'cv-insert-github', 'secondary small pulse-button', undefined, 'title="' + escape(copy('Chèn kỹ năng có bằng chứng từ GitHub', 'Insert evidence-backed GitHub skills')) + '"')
    + namedButton('✨ ' + copy('Tạo CV bằng AI', 'AI Generate'), 'cv-generate', 'secondary small', undefined, 'title="' + escape(copy('Tạo CV tối ưu theo JD từ dữ kiện thực tế', 'Generate CV matching JD with verified facts')) + '"')
    + '<div class="cv-export-group">'
    + (doc ? namedButton('PDF', 'cv-export', 'secondary small', 'pdf') + namedButton('DOCX', 'cv-export', 'secondary small', 'docx') : '')
    + namedButton(t('cv.print'), 'cv-print', 'secondary small')
    + '</div>'
    + btn(icon('check') + ' ' + escape(copy('Lưu CV', 'Save CV')), 'cv-save-bar', 'primary small cv-save-btn', undefined, 'title="' + escape(copy('Lưu CV (Ctrl+S)', 'Save CV (Ctrl+S)')) + '"')
    + '<button type="button" class="button secondary small cv-toggle-intel-btn' + (!intelCollapsed ? ' active' : '') + '" data-act="cv-toggle-intel" title="' + escape(copy('Bật/tắt Bảng thiết kế & công cụ', 'Toggle design & tools hub')) + '">'
    + '⚙️ ' + escape(copy(intelCollapsed ? 'Thiết kế & Công cụ' : 'Thu gọn', intelCollapsed ? 'Design & Tools' : 'Collapse')) + '</button>'
    + '</div>'
    + '</div>'
    + '</section>';

  const loadingNotice = busy
    ? '<div class="cv-loading-notice">' + icon('pulse') + ' '
      + copy('Đang xử lý tệp CV qua API máy chủ, vui lòng đợi trong giây lát…', 'Processing CV file via server API, please wait…') + '</div>'
    : '';

  const structured = parseCVForReference(draft.body, draft.name, draft.role);

  // LEFT PANEL: EDITOR (Reactive Resume v6 Accordion Layout)
  const editorPanel = '<article class="panel cv-editor cv-panel-editor">'
    + '<div class="panel-head cv-editor-header" style="margin-bottom:6px">'
    + '<h2 class="panel-title">' + copy('Nội dung CV', 'Resume Content') + '</h2>'
    + '</div>'
    + '<div class="cv-mode-tabs" role="tablist">'
    + '<button type="button" class="button' + (editorMode === 'structured' ? ' active' : '') + '" data-act="cv-editor-mode" data-id="structured">' + copy('📋 Form cấu trúc', '📋 Form Sections') + '</button>'
    + '<button type="button" class="button' + (editorMode === 'raw' ? ' active' : '') + '" data-act="cv-editor-mode" data-id="raw">' + copy('📝 Văn bản thô', '📝 Raw Markdown') + '</button>'
    + '</div>'
    + '<fieldset class="cv-controls"' + (busy ? ' disabled' : '') + '><form id="cv-form" class="cv-controls">'
    + '<div class="cv-basics-card">'
    + '<div class="field-row">'
    + field(t('cv.name'), '<input name="name" maxlength="120" placeholder="' + escape(copy('Họ và tên', 'Full Name')) + '" value="' + escape(draft.name) + '">')
    + field(t('cv.role'), '<input name="role" maxlength="70" placeholder="' + escape(copy('Chức danh chuyên môn', 'Professional Title')) + '" value="' + escape(draft.role) + '">')
    + '</div>'
    + (editorMode === 'structured'
      ? field(copy('Thông tin liên hệ', 'Contact info'), '<input name="cv-struct-contact" maxlength="150" placeholder="'
          + escape(copy('Email | Số điện thoại | GitHub | Địa điểm...', 'Email | Phone | GitHub | Location...')) + '" value="' + escape(structured.contact || '') + '">')
      : '')
    + '</div>'
    + (editorMode === 'structured'
      ? renderStructuredSections(structured, copy, escape, data.activeSection)
        + '<div class="cv-raw-sync-wrap">'
        + '<div class="cv-raw-sync-header">'
        + '<span>📝 ' + copy('Đồng bộ văn bản thô (Markdown)', 'Raw Markdown Sync') + '</span>'
        + '<small>' + copy('Tự động cập nhật hai chiều', 'Bidirectional sync') + '</small>'
        + '</div>'
        + '<textarea name="body" rows="3" class="cv-raw-sync-input" maxlength="20000" placeholder="' + escape(t('cv.placeholder')) + '" required>' + escape(draft.body) + '</textarea>'
        + '</div>'
      : field(t('cv.content'), '<textarea name="body" rows="14" maxlength="20000" placeholder="' + escape(t('cv.placeholder')) + '" required>' + escape(draft.body) + '</textarea>'))
    + '<details class="cv-drawer-card">'
    + '<summary class="cv-drawer-head">📁 ' + copy('Tải lên CV & Chọn bản đã lưu', 'Import File & Saved CVs') + '</summary>'
    + '<div class="cv-drawer-body">'
    + '<div class="field cv-file-field">'
    + '<span class="filter-label">' + escape(t('cv.import')) + '</span>'
    + '<label class="cv-file-upload-box" for="cv-upload">'
    + '<input id="cv-upload" type="file" accept=".pdf,.docx" class="cv-file-input-hidden">'
    + '<span class="filter-glyph">' + icon('file') + '</span>'
    + '<span class="cv-upload-info">'
    + '<strong>' + copy('Tải tệp CV lên (.pdf, .docx)', 'Upload CV file (.pdf, .docx)') + '</strong>'
    + '<small>' + copy('Bấm để chọn tệp từ máy tính của bạn', 'Click to choose file from your computer') + '</small>'
    + '</span>'
    + '<span class="button secondary small cv-upload-browse-btn">' + copy('Chọn tệp', 'Browse') + '</span>'
    + '</label>'
    + '</div>'
    + customPicker(
        copy('CV đã tải lên', 'Uploaded CVs'),
        cv?.id,
        cv ? 'CV #' + cv.id : undefined,
        data.cvList.map(item => ({ id: item.id, title: 'CV #' + item.id })),
        'live-cv-select',
        'file'
      )
    + customPicker(
        copy('CV Studio', 'CV Studio'),
        doc?.document_id,
        doc?.title,
        data.documentList.map(item => ({ id: item.document_id, title: item.title })),
        'live-document-select',
        'file'
      )
    + (doc ? customPicker(
        copy('Phiên bản', 'Version'),
        doc.number,
        '#' + doc.number,
        data.versions.map(item => ({ id: item.number, title: '#' + item.number })),
        'live-version-select',
        'clock'
      ) : '')
    + '</div></details>'
    + '</form>'
    + '</fieldset></article>';

  // CENTER PANEL: PREVIEW (Reactive Resume v6 Centered A4 Canvas)
  const previewPanel = '<article class="panel cv-preview cv-panel-preview">'
    + '<div class="cv-preview-header-bar">'
    + '<div class="tabs" role="group" aria-label="' + copy('Chọn mẫu CV', 'Select template') + '">' + ['plain', 'tech', 'reference'].map(key => btn(escape(t('cv.' + key)), 'cv-template', '',
      attr('id', key) + ' aria-pressed="' + (state.template === key) + '"')).join('') + '</div>'
    + '<div class="cv-zoom-controls">'
    + '<button type="button" class="button' + (zoom === '85' ? ' active' : '') + '" data-act="cv-zoom" data-id="85">85%</button>'
    + '<button type="button" class="button' + (zoom === '100' ? ' active' : '') + '" data-act="cv-zoom" data-id="100">100%</button>'
    + '<button type="button" class="button' + (zoom === '115' ? ' active' : '') + '" data-act="cv-zoom" data-id="115">115%</button>'
    + '<button type="button" class="button' + (zoom === 'fit' ? ' active' : '') + '" data-act="cv-zoom" data-id="fit" title="' + copy('Vừa chiều rộng màn hình', 'Fit to width') + '">' + copy('Vừa', 'Fit') + '</button>'
    + '</div>'
    + '<span class="cv-page-indicator">📄 ' + copy('A4 Chuẩn', 'Standard A4') + '</span>'
    + '<span class="cv-direct-edit-tip">' + copy('✏️ Sửa trực tiếp trên CV', '✏️ Click on CV to edit') + '</span>'
    + '</div>'
    + '<div class="cv-preview-viewport cv-zoom-' + escape(zoom) + '">'
    + (state.template === 'reference'
      ? renderReferenceCV(draft)
      : '<div class="cv-paper" data-template="' + escape(state.template) + '"><h2 id="cv-name" contenteditable="true" spellcheck="false">' + escape(draft.name)
        + '</h2><p id="cv-role" contenteditable="true" spellcheck="false">' + escape(draft.role) + '</p><div class="cv-body" id="cv-body" contenteditable="true" spellcheck="false">' + escape(draft.body || t('cv.empty')) + '</div></div>')
    + '</div>'
    + '<div class="action-row cv-exports">' + (doc ? namedButton('PDF', 'cv-export', 'secondary small', 'pdf') + namedButton('DOCX', 'cv-export', 'secondary small', 'docx') : '')
    + namedButton(t('cv.print'), 'cv-print', 'secondary small') + '</div></article>';

  // RIGHT PANEL: DESIGN & TOOLS (Thiết kế & Công cụ)
  const atsEnabled = (draft.body.trim().length > 0 || cv) && !busy;

  let intelBody = '';
  if (intelTab === 'design') {
    intelBody = '<div class="cv-intel-content cv-design-tab">'
      + '<div class="cv-design-section">'
      + '<h4>' + copy('Mẫu giao diện CV', 'Resume Templates') + '</h4>'
      + '<div class="cv-template-cards">'
      + '<div class="cv-tpl-card' + (state.template === 'reference' ? ' selected' : '') + '" data-act="cv-template" data-id="reference">'
      + '<div class="cv-tpl-badge">★ Recommended</div>'
      + '<strong>' + copy('Theo mẫu (Executive 2 Cột)', 'Executive 2-Column') + '</strong>'
      + '<p>' + copy('Chuẩn Executive quốc tế, chia cột thời gian & công ty tinh gọn, chống tràn trang khi xuất PDF.', 'Modern 2-column layout, clear timeline, prevents page overflow.') + '</p>'
      + '</div>'
      + '<div class="cv-tpl-card' + (state.template === 'tech' ? ' selected' : '') + '" data-act="cv-template" data-id="tech">'
      + '<strong>' + copy('Kỹ thuật (Tech Modern)', 'Tech Modern') + '</strong>'
      + '<p>' + copy('Điểm nhấn hiện đại, font sans-serif & monospace dành cho lập trình viên.', 'Modern border accent, mono labels, designed for software engineers.') + '</p>'
      + '</div>'
      + '<div class="cv-tpl-card' + (state.template === 'plain' ? ' selected' : '') + '" data-act="cv-template" data-id="plain">'
      + '<strong>' + copy('Tối giản (Classic Plain)', 'Classic Plain') + '</strong>'
      + '<p>' + copy('Phong cách truyền thống, font có chân (Serif), chuẩn mực và trang nhã.', 'Traditional serif typography, clean and elegant.') + '</p>'
      + '</div>'
      + '</div></div>'
      + '<div class="cv-design-section">'
      + '<h4>' + copy('Thu phóng trang giấy', 'Canvas Zoom') + '</h4>'
      + '<div class="cv-zoom-btn-group">'
      + '<button type="button" class="button secondary small' + (zoom === '85' ? ' active' : '') + '" data-act="cv-zoom-panel" data-id="85">85%</button>'
      + '<button type="button" class="button secondary small' + (zoom === '100' ? ' active' : '') + '" data-act="cv-zoom-panel" data-id="100">100%</button>'
      + '<button type="button" class="button secondary small' + (zoom === '115' ? ' active' : '') + '" data-act="cv-zoom-panel" data-id="115">115%</button>'
      + '<button type="button" class="button secondary small' + (zoom === 'fit' ? ' active' : '') + '" data-act="cv-zoom-panel" data-id="fit">' + copy('Vừa màn hình', 'Fit Width') + '</button>'
      + '</div></div>'
      + '<div class="cv-ai-guide-card">'
      + '<strong>💡 ' + copy('Mẹo xuất PDF chuẩn A4', 'A4 Export Tip') + '</strong>'
      + '<p>' + copy('Dùng nút In/Lưu PDF trên thanh công cụ và chọn "Lưu dưới dạng PDF" với khổ giấy A4, tỷ lệ mặc định để có bản in sắc nét nhất.', 'Use Print to PDF and choose A4 size for the crispest output.') + '</p>'
      + '</div>'
      + '</div>';
  } else if (intelTab === 'github') {
    const verifiedScores = verifiedCVSkills(data.scores);
    intelBody = '<div class="cv-intel-content">'
      + '<div class="cv-evidence-header">'
      + '<span><strong>' + verifiedScores.length + '</strong> ' + copy('kỹ năng có minh chứng', 'evidence-backed skills') + '</span>'
      + btn(icon('pulse') + ' ' + copy('Chèn tất cả', 'Insert all'), 'cv-insert-github', 'secondary small')
      + '</div>'
      + (verifiedScores.length > 0
        ? '<div class="cv-evidence-list">' + verifiedScores.map(item => {
            return '<div class="cv-evidence-card">'
              + '<div class="cv-evidence-card-head">'
              + '<div class="cv-evidence-tech"><strong>' + escape(formatSkillName(item.technology)) + '</strong><span class="cv-score-pill">' + number(item.score) + '/100</span></div>'
              + '<span class="status-pill green">' + copy('Đã xác minh','Verified') + '</span>'
              + '</div>'
              + '<div class="cv-evidence-meta">'
              + '<span class="cv-evidence-repo" title="' + escape(item.repo?.full_name || item.repo?.name || '') + '">📁 ' + escape(item.repo?.full_name || item.repo?.name || 'GitHub') + '</span>'
              + '</div>'
              + '<div class="cv-evidence-actions">'
              + '<button type="button" class="button secondary small" data-act="cv-insert-single-skill" data-id="' + escape(cvSkillKey(item)) + '">'
              + copy('+ Chèn vào CV', '+ Add to CV') + '</button>'
              + '</div></div>';
          }).join('') + '</div>'
        : '<div class="cv-intel-empty"><div class="empty-icon">📁</div><h4>' + copy('Chưa có bằng chứng GitHub', 'No GitHub evidence yet') + '</h4>'
          + '<p>' + copy('Kết nối GitHub và phân tích repository để trích xuất bằng chứng kỹ thuật vào CV.', 'Connect GitHub and analyze repositories to extract verified technical skills.') + '</p>'
          + '<a href="#studio/repos" class="button secondary small">' + copy('Mở Phân tích GitHub', 'Open GitHub Analysis') + '</a></div>')
      + '</div>';
  } else if (intelTab === 'ats') {
    intelBody = '<div class="cv-intel-content">'
      + field(copy('Mô tả công việc (JD)', 'Job description (JD)'), '<textarea name="ats-jd" maxlength="20000" rows="4" placeholder="'
        + escape(copy('Dán mô tả công việc (JD) để đối chiếu độ phủ từ khóa với nội dung CV bên cạnh…', 'Paste JD to match keyword coverage against CV…')) + '">'
        + escape(data.atsJD ?? '') + '</textarea>')
      + '<div class="action-row cv-ats-actions">'
      + btn(icon('pulse') + ' ' + copy('Kiểm tra ATS', 'Check ATS'), 'cv-check', 'primary small' + (busy ? ' disabled' : ''), busy ? 'disabled' : '')
      + (!atsEnabled && !busy ? '<span class="subtle cv-ats-hint">' + copy('💡 Nhập nội dung CV hoặc tải tệp lên để bắt đầu kiểm tra ATS.', '💡 Enter CV content or upload a file to check ATS.') + '</span>' : '')
      + '</div>'
      + '<div id="ats-result" aria-live="polite">' + (ats
        ? '<div class="cv-ats-metrics">'
          + '<div class="cv-ats-metric-box"><div class="cv-ats-metric-val">' + number(ats.readability_score) + '<span style="font-size:12px;color:var(--muted)">/100</span></div><div class="cv-ats-metric-lbl">' + copy('Cấu trúc văn bản', 'Readability') + '</div></div>'
          + '<div class="cv-ats-metric-box"><div class="cv-ats-metric-val">' + (ats.keyword_coverage == null ? '—' : number(ats.keyword_coverage) + '%') + '</div><div class="cv-ats-metric-lbl">' + copy('Độ phủ từ khóa', 'Keyword Match') + '</div></div>'
          + '</div>'
          + muted(ats.disclaimer)
          + '<ul class="cv-checks">' + ats.suggestions.map(suggestion => '<li>' + escape(suggestion.message) + '</li>').join('') + '</ul>'
        : '') + '</div></div>';
  } else if (intelTab === 'ai') {
    intelBody = '<div class="cv-intel-content">'
      + '<div style="margin-bottom:8px">' + namedButton(copy('✨ Tạo CV bằng AI', '✨ Generate CV with AI'), 'cv-generate', 'primary') + '</div>'
      + '<div class="cv-ai-guide-card">'
      + '<strong>🛡️ ' + copy('Nguyên tắc Anti-Hallucination', 'Anti-Hallucination Policy') + '</strong>'
      + '<p>' + copy('Hệ thống chỉ tổng hợp kinh nghiệm từ CV nguồn đã lưu hoặc bằng chứng commit thực tế từ GitHub của bạn. AI không tự tạo thành tích giả.', 'The AI only synthesizes facts from your verified source CV or actual GitHub commits.') + '</p>'
      + '</div>'
      + '<div class="cv-ai-guide-card">'
      + '<strong>💡 ' + copy('Công thức STAR viết Bullet Point', 'STAR Framework for Bullets') + '</strong>'
      + '<p><strong>S / T:</strong> ' + copy('Bối cảnh & nhiệm vụ cụ thể.', 'Situation & specific task.') + '<br>'
      + '<strong>A:</strong> ' + copy('Hành động & Công nghệ sử dụng.', 'Action & technologies used.') + '<br>'
      + '<strong>R:</strong> ' + copy('Kết quả định lượng đo lường được.', 'Measurable quantitative results.') + '</p>'
      + '</div></div>';
  } else {
    // References Tab
    intelBody = '<div class="cv-intel-content">'
      + '<form class="field-row" id="cv-references-form" novalidate>'
      + field(copy('Công ty', 'Company'), '<input name="company" required maxlength="100" value="' + escape(data.referencesQuery?.company) + '">')
      + field(copy('Vị trí', 'Role'), '<input name="role" required maxlength="100" value="' + escape(data.referencesQuery?.role) + '">')
      + '<button class="button secondary small" type="submit">' + escape(copy('Tìm mẫu', 'Find references')) + '</button></form>'
      + (references ? muted(references.disclaimer) + '<ul class="audit-list">'
        + references.references.map(item => {
          const url = safeLink(item.source_url);
          return '<li><span>' + (url ? '<a href="' + escape(url) + '" target="_blank" rel="noopener noreferrer">' + escape(item.title) + '</a>' : escape(item.title))
            + '</span><small>' + escape(item.license) + '</small></li>';
        }).join('') + '</ul>' : '') + '</div>';
  }

  const intelPanel = '<article class="panel cv-intel cv-panel-intel">'
    + '<div class="panel-head cv-intel-header" style="margin-bottom:6px">'
    + '<h2 class="panel-title">' + copy('Thiết kế & Công cụ', 'Design & Tools') + '</h2>'
    + '<button type="button" class="button quiet small cv-intel-close-btn" data-act="cv-toggle-intel" title="' + escape(copy('Đóng bảng công cụ', 'Close tools panel')) + '">✕ ' + copy('Đóng', 'Close') + '</button>'
    + '</div>'
    + '<div class="cv-intel-tabs" role="tablist">'
    + '<button type="button" class="button' + (intelTab === 'design' ? ' active' : '') + '" data-act="cv-intel-tab" data-id="design">' + copy('🎨 Thiết kế', '🎨 Design') + '</button>'
    + '<button type="button" class="button' + (intelTab === 'github' ? ' active' : '') + '" data-act="cv-intel-tab" data-id="github">' + copy('📁 Minh chứng Git', '📁 Git Evidence') + '</button>'
    + '<button type="button" class="button' + (intelTab === 'ats' ? ' active' : '') + '" data-act="cv-intel-tab" data-id="ats">' + copy('🎯 Tối ưu ATS', '🎯 ATS Review') + '</button>'
    + '<button type="button" class="button' + (intelTab === 'ai' ? ' active' : '') + '" data-act="cv-intel-tab" data-id="ai">' + copy('✨ Trợ lý AI', '✨ AI Assistant') + '</button>'
    + '<button type="button" class="button' + (intelTab === 'references' ? ' active' : '') + '" data-act="cv-intel-tab" data-id="references">' + copy('🔍 Mẫu CV', '🔍 References') + '</button>'
    + '</div>'
    + intelBody
    + '</article>';

  return heading(t('nav.cv'), t('cv.intro')) + feedback(data, 'cv')
    + cvCommandBar
    + loadingNotice
    + '<div class="columns cv-workspace-3col' + (intelCollapsed ? ' intel-collapsed' : ' intel-open' + (intelExplicitOpen ? ' intel-explicit-open' : '')) + '">'
    + editorPanel
    + previewPanel
    + intelPanel
    + '</div>';
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

export function updateCVFitScale() {
  if (typeof document === 'undefined') return;
  const viewport = document.querySelector('.cv-preview-viewport');
  if (!viewport) return;
  const availW = Math.max(260, viewport.clientWidth - 32);
  const scale = Math.min(1.0, Math.max(0.35, availW / 794));
  viewport.style.setProperty('--cv-scale', scale.toFixed(4));
}
