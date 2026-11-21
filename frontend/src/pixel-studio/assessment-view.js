import {repoText, roleScores} from './data.js';
import {dateLabel, rangeLabel, roleLabel, scopeLabel, sourceLabel, t} from './i18n.js';
import {currentRepos, radarScores, reportFor, repoSelected, roleEvidence, scoredRepos, sourceSkills} from './model.js';
import {evidenceURL, latestAward, milestoneText, milestonesFor, nextStep, stateOf, stepsDone} from './roadmap-model.js';
import {activityFor, compareSnapshots, radarComparison, reportTimeline} from './analysis-data.js';
import {codeReference, codeReferenceLabel, matchesCodeReference} from './evidence.js';
import {attr, badge, blank, btn, codeBlock, details, escape, field, filterControls, heading, icon, labelAttr, link, option, panelHead, progress, tags} from './ui.js';
import {radarView} from './radar.js';

const evidenceButton = repo => btn(icon('file') + ' ' + escape(repo.file),'evidence','link-button',attr('id',repo.id));

function scoreRow(title,score,action,id,active) {
  return '<button type="button" class="score-row" data-act="' + action + '"' + attr('id',id) + ' aria-pressed="' + String(active)
    + '"><span>' + escape(title) + '</span><b>' + score + '<small>/100</small></b>' + '<span class="score-track" aria-hidden="true">' + progress(score,title) + '</span></button>';
}

function confidence(value) {
  return '<div class="confidence-line"><span class="confidence-mark"><i></i><i></i><i></i></span><div>'
    + '<strong>' + escape(t('profile.coverage',{value})) + '</strong><small>' + escape(t('profile.confidenceHelp')) + '</small></div></div>';
}

function originRows(skills) {
  return skills.map(({name,sources}) => '<div class="skill-origin"><strong>' + escape(name) + '</strong>'
    + [...sources].map(source => badge(sourceLabel(source),source === 'github' ? 'green' : source === 'declared' ? 'blue' : '')).join('') + '</div>').join('');
}

function competency(state,runtime,visible) {
  const tab = runtime.scoreTab;
  const tabs = [['tech','profile.tech'],['roles','profile.roles'],['sources','profile.sources']];
  const tabButtons = '<div class="tabs" role="group"' + labelAttr(t('profile.scoreType')) + '>'
    + tabs.map(([key,label]) => '<button type="button" id="' + key + '" data-act="score-tab"' + attr('id',key) + ' aria-pressed="' + (tab === key)
      + '">' + escape(t(label)) + '</button>').join('') + '</div>';
  let scores = '';
  let evidence = '';
  if (tab === 'tech') {
    const selected = visible.find(repo => repo.id === state.focusScore) ?? visible[0];
    scores = visible.map(repo => scoreRow(repo.tech + ' · ' + repoText(repo,'skill'),repo.score,'score',repo.id,selected?.id === repo.id)).join('');
    if (selected) {
      evidence = '<h3>' + escape(repoText(selected,'skill')) + '</h3>' + confidence(selected.confidence)
        + '<dl class="reason-list"><div><dt>' + escape(t('profile.working')) + '</dt><dd>' + escape(repoText(selected,'result')) + '</dd></div>'
        + '<div><dt>' + escape(t('profile.gap')) + '</dt><dd>' + escape(repoText(selected,'gap')) + '</dd></div></dl>'
        + '<div class="action-row">' + evidenceButton(selected)
        + btn(icon('bot') + escape(t('action.askMentor')),'ask-evidence','secondary small',attr('id',selected.id)) + '</div>';
    }
  } else if (tab === 'roles') {
    const roles = roleScores.map(({id}) => roleEvidence(state,id)).filter(Boolean);
    const selected = roles.find(role => role.id === runtime.roleIndex) ?? roles[0];
    scores = roles.map(role => scoreRow(roleLabel(role.id),role.score,'role-score',role.id,selected.id === role.id)).join('');
    if (selected) {
      const {metrics} = selected;
      evidence = '<h3>' + escape(roleLabel(selected.id)) + '</h3>' + confidence(selected.confidence)
        + '<p>' + escape(selected.reason) + '</p><dl class="role-breakdown">' + metrics.map(metric => '<div><dt>' + escape(metric.label) + ' <small>· ' + escape(t('profile.weight',{value:metric.weight})) + '</small>'
          + '</dt><dd>' + metric.score + '<small>/100</small></dd></div>').join('') + '</dl>'
        + '<div class="action-row">' + selected.evidence.map(evidenceButton).join('') + '</div>';
    }
  } else {
    const skills = [...sourceSkills(state).values()];
    const verified = skills.filter(skill => skill.sources.has('github'));
    const supplementary = skills.filter(skill => [...skill.sources].some(source => source !== 'github'))
      .map(skill => ({...skill,sources:new Set([...skill.sources].filter(source => source !== 'github'))}));
    if (skills.length) scores = '<div class="project-skills"><h3>' + escape(t('profile.verifiedHeading')) + '</h3>'
      + (verified.length ? originRows(verified.map(skill => ({...skill,sources:new Set(['github'])}))) : '<p class="subtle">' + escape(t('profile.noEvidence')) + '</p>')
      + '<h3>' + escape(t('profile.supplementary')) + '</h3>' + (supplementary.length ? originRows(supplementary) : '<p class="subtle">' + escape(t('profile.noSupplement')) + '</p>') + '</div>';
    evidence = '<h3>' + escape(t('profile.self')) + '</h3><p>' + escape(t('profile.selfCopy')) + '</p>'
      + '<form id="skill-form" class="skill-form">' + field(t('profile.skill'),'<input name="skill" maxlength="35" placeholder="'
      + escape(t('profile.skillExample')) + '" required>')
      + field(t('road.optionalLink'),'<input type="url" name="evidence" maxlength="900" placeholder="https://">')
      + '<button class="button primary" type="submit">' + escape(t('action.add')) + '</button></form>'
      + (state.skillBasis.length ? '<ul class="claimed-skills">' + state.skillBasis.map(skill => {
        const url = evidenceURL(state.claimEvidence.find(item => item.skill === skill)?.url);
        const proof = url ? '<a class="link-button" href="' + escape(url) + '" target="_blank" rel="noopener noreferrer">'
          + icon('link') + escape(t('road.linkEvidence')) + '</a>' : '';
        return '<li><strong>' + escape(skill) + '</strong><div class="action-row">' + proof
          + btn(icon('close'),'remove-skill','quiet small',attr('id',skill) + labelAttr(t('action.remove') + ' ' + skill)) + '</div></li>';
      }).join('') + '</ul>' : '');
  }
  return '<div class="columns dashboard-columns"><section class="panel scores-panel">' + panelHead(t('profile.skills'),t('profile.scoreCopy'))
    + tabButtons + '<div class="rows">' + (scores || blank(t('profile.noScores'),t('profile.noEvidenceCopy'))) + '</div></section>'
    + '<section class="panel evidence-card">' + panelHead(t(tab === 'sources' ? 'profile.origins' : 'profile.evidence'))
    + (evidence || blank(t('profile.noEvidence'),t('profile.noEvidenceCopy'),link(escape(t('action.openRepo')),'repos','secondary small'))) + '</section></div>';
}

const radarEvidence = {
  code:{repos:['portfolio-lab','student-club-api','queue-lab','fastapi-starter'],tab:'code',step:0},
  architecture:{repos:['student-club-api','queue-lab','portfolio-lab','fastapi-starter'],tab:'code',step:3},
  testing:{repos:['student-club-api','fastapi-starter','queue-lab'],tab:'code',step:1},
  collaboration:{repos:['student-club-api','portfolio-lab','fastapi-starter','queue-lab'],tab:'collab',step:4},
  ci:{repos:['student-club-api','queue-lab','portfolio-lab','fastapi-starter'],tab:'collab',step:1}
};

function metricInsight(state,metric,displayed,comparison) {
  const {key,label,score} = metric;
  const {repos,tab,step} = radarEvidence[key];
  const trend = comparison?.metrics[key];
  const related = repos.map(id => displayed.find(repo => repo.id === id)).filter(Boolean);
  const repo = related[0];
  const added = key === 'testing' ? comparison?.addedTests.filter(ref => displayed.some(item => matchesCodeReference(item,ref))) ?? [] : [];
  const alreadyLinked = added.some(ref => ref.repoId === repo?.id);
  const evidenceDetail = repo && ({
    code:() => codeReferenceLabel(codeReference(repo)),
    architecture:() => repo.structure.join(' · '),
    testing:() => codeReferenceLabel(codeReference(repo)),
    collaboration:() => t('analysis.reviewCount',{count:activityFor(repo,state.range)[2]}),
    ci:() => t('analysis.workflowCount',{count:activityFor(repo,state.range)[3]})
  })[key]();
  const evidence = repo ? '<div class="radar-evidence-line"><div><strong>' + escape(repo.name) + '</strong><small>'
    + escape(t('profile.coverage',{value:repo.confidence})) + ' · ' + escape(t('radar.confidenceBasis')) + '</small>'
    + (alreadyLinked ? '' : '<p>' + escape(evidenceDetail) + '</p>') + '</div>'
    + (alreadyLinked ? '' : btn(icon('file') + escape(t('radar.openEvidence')),'metric-evidence','secondary small',attr('id',repo.id) + attr('tab',tab)))
    + '</div>' : '<p class="subtle">' + escape(t('radar.noMetricEvidence')) + '</p>';
  const trendCopy = trend
    ? '<div class="radar-trend"><strong>' + trend.before + ' <span aria-hidden="true">→</span> ' + trend.current + '<small>/100</small></strong>'
      + '<span>' + escape(t('radar.compared',{version:comparison.rubric})) + '</span></div>'
    : '<p class="subtle">' + escape(t('analysis.noComparison')) + '</p>';
  return '<section id="radar-detail-' + key + '" class="radar-insight" aria-labelledby="radar-label-' + key + '" hidden>'
    + '<div class="radar-insight-head"><h3 id="radar-label-' + key + '">' + escape(label) + '</h3><b>' + score + '<small>/100</small></b></div>'
    + '<p>' + escape(t('radar.meaning.' + key)) + '</p>' + trendCopy
    + (added.length ? '<div class="radar-added"><strong>' + escape(t('radar.addedEvidence')) + '</strong>'
      + added.map(ref => btn(icon('file') + escape(codeReferenceLabel(ref)),'evidence','link-button',attr('id',ref.repoId)
        + attr('file',ref.file) + attr('commit',ref.commit) + attr('start',ref.start) + attr('end',ref.end))).join('') + '</div>' : '')
    + evidence + '<div class="radar-next-actions">'
    + btn(icon('bot') + escape(t('radar.askMetric')),'ask-metric','secondary small',attr('id',key))
    + btn(icon('branch') + escape(t('radar.relatedMilestone',{name:milestoneText(state.goal,step)})),
      'focus-milestone','quiet small',attr('id',step))
    + '</div></section>';
}

export function dashboard(state,runtime) {
  const visible = scoredRepos(state);
  const metrics = radarScores(visible);
  const comparison = radarComparison(state,visible);
  const next = nextStep(state);
  const total = milestonesFor(state).length;
  const award = latestAward(state);
  const done = stepsDone(state);
  const scope = state.access === 'none' ? t('profile.disconnected') : scopeLabel(state.scope);
  return '<header class="page-heading dashboard-heading"><div><p class="eyebrow">' + escape(t('profile.target',{role:roleLabel(state.goal)}))
    + '</p><h1>' + escape(t('profile.greeting')) + '</h1><p>' + escape(t('profile.intro'))
    + '</p></div><div class="dashboard-filters">' + filterControls(state,!!runtime.operation) + '</div></header>'
    + '<div class="dashboard-summary"><section class="panel dashboard-focus"><div class="focus-heading"><span class="feature-icon">' + icon('branch')
    + '</span><div><p class="eyebrow">' + escape(t('profile.next')) + '</p><h2>'
    + escape(next === -1 ? t('road.finished') : milestoneText(state.goal,next)) + '</h2></div></div><p>'
    + escape(next === -1 ? t('road.finishedCopy') : milestoneText(state.goal,next,'task')) + '</p>'
    + (next < 0 ? '' : '<p class="focus-deliverable">' + icon('award') + '<span><strong>' + escape(t('road.proof')) + '</strong>'
      + escape(milestoneText(state.goal,next,'proof')) + '</span></p>')
    + (next === -1 ? link(escape(t('action.openRoadmap')) + icon('arrow'),'roadmap','secondary small')
      : btn(escape(t('profile.pickNext')) + icon('arrow'),'focus-milestone','primary small',attr('id',next))) + '</section>'
    + '<section class="panel dashboard-progress"><p class="eyebrow">' + escape(t('road.progress')) + '</p>'
    + '<div class="focus-progress"><strong>' + done + '<span> / ' + total + '</span></strong><small>'
    + escape(t('profile.milestonesDone')) + '</small>' + progress(done / total * 100,t('road.progressCount',{done,total})) + '</div>'
    + '<div class="dash-award"><span class="award-icon">' + icon('award') + '</span><div><p class="eyebrow">'
    + escape(t('profile.latestAchievement')) + '</p>' + (award === undefined
      ? '<p>' + escape(t('profile.achievementsEmpty')) + '</p>'
      : '<button class="award-link" type="button" data-act="focus-milestone"' + attr('id',award) + '>'
        + escape(milestoneText(state.goal,award,'achievement')) + icon('arrow') + '</button>') + '</div></div></section></div>'
    + radarView(metrics,visible.length,scope,rangeLabel(state.range),comparison?.metrics,
      metrics.map(metric => metricInsight(state,metric,visible,comparison)).join(''))
    + competency(state,runtime,visible);
}

function reportDetail(repo,tab,range,showEvidence) {
  const [,pulls,reviews] = activityFor(repo,range);
  if (tab === 'ownership') return details([
    [t('repos.repoType'),badge(t(repo.fork ? 'repos.fork' : 'repos.original'),repo.fork ? 'blue' : 'green')],
    [t('repos.owner'),escape(repoText(repo,'ownership'))],
    [t('repos.contribution'),escape(repoText(repo,'contribution'))]
  ]) + codeBlock(repo,showEvidence);
  if (tab === 'collab') return details([
    ['Pull Request',escape(t('analysis.prCount',{count:pulls}))],
    [t('repos.review'),escape(t('repos.reviewCount',{count:reviews,title:repoText(repo,'review')}))],
    ['GitHub Actions',escape(repoText(repo,'ci'))],
    [t('repos.incident'),escape(repoText(repo,'incident'))]
  ]);
  return details([
    [t('repos.languages'),tags(repo.languages.map(([name,share]) => name + ' ' + share + '%'))],
    [t('repos.tools'),tags(repo.stack)],
    [t('repos.structure'),tags(repo.structure)],
    [t('repos.finding'),escape(repoText(repo,'result'))]
  ]) + codeBlock(repo,showEvidence);
}

const analysisPhases = ['analysis.stepQueued','analysis.stepScan','analysis.stepBuild'];

function analysisProgress(operation) {
  return '<section class="analysis-run" aria-live="polite"><header><h3>' + escape(t('analysis.running')) + '</h3>'
    + btn(escape(t('analysis.cancel')),'cancel-analysis','quiet small') + '</header><ol class="pipeline">'
    + analysisPhases.map((key,i) => '<li data-state="' + (i < operation.phase ? 'done' : i === operation.phase ? 'active' : 'waiting')
    + '"' + (i === operation.phase ? ' aria-current="step"' : '') + '><span>' + icon(i < operation.phase ? 'check' : 'pulse') + '</span>'
    + escape(t(key)) + '</li>').join('') + '</ol><p class="analysis-wait-hint">' + escape(t('analysis.waitRepo')) + '</p></section>';
}

function reportHistory(state,repo) {
  const snapshots = reportTimeline(state,repo);
  const [latest,previous] = snapshots;
  const delta = compareSnapshots(latest,previous);
  const copy = delta === null ? t('analysis.noComparison') : delta === 0
    ? t('analysis.same',{score:latest.score})
    : t('analysis.changed',{delta:(delta > 0 ? '+' : '') + delta});
  return '<details class="report-history"><summary>' + escape(t('analysis.history')) + '</summary>'
    + (latest ? '<p>' + escape(copy) + '</p><ul class="audit-list">' + snapshots.slice(0,8).map(snapshot => '<li><time datetime="'
      + new Date(snapshot.at).toISOString() + '">' + escape(dateLabel(snapshot.at,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}))
      + '</time><span><b>' + snapshot.score + '/100</b> · ' + escape(scopeLabel(snapshot.scope) + ' · ' + rangeLabel(snapshot.range)
        + ' · ' + t('analysis.rubric',{version:snapshot.rubric})) + '</span></li>').join('') + '</ul>'
      : '<p>' + escape(t('analysis.historyEmpty')) + '</p>') + '</details>';
}

export function repositoryView(state,runtime) {
  const intro = heading(t('repos.heading'),t('repos.intro'));
  if (state.access === 'none') {
    return intro + '<div class="panel">' + blank(t('repos.disconnected'),t('repos.disconnectedCopy'),btn(escape(t('repos.connect')),'reconnect','primary')) + '</div>';
  }
  const visible = currentRepos(state);
  const active = repoSelected(state);
  const operation = runtime.operation;
  const syncing = operation?.kind === 'sync';
  const analyzing = operation?.kind === 'analysis';
  const toolbar = '<div class="panel analysis-toolbar"><div class="toolbar">' + filterControls(state,!!operation)
    + btn(icon('repo') + escape(t(syncing ? 'action.synching' : 'action.sync')),'sync','secondary',operation ? 'disabled' : '') + '</div>'
    + '<p class="scope-summary" role="status">' + escape(t(syncing ? 'analysis.syncReading' : state.synced ? 'analysis.syncDone' : 'repos.count',{count:visible.length}))
    + '</p></div>';
  if (!active) return intro + toolbar + '<div class="panel">' + blank(t('repos.noRepo'),t('repos.noRepoCopy')) + '</div>';
  const running = operation?.kind === 'analysis' && operation.id === active.id;
  const attempts = state.attempts.filter(item => item.repo === active.id && (item.scope === undefined
    || (item.scope === state.scope && item.range === state.range)));
  const attempt = attempts[0];
  const report = reportFor(state,active);
  const list = visible.map(repo => {
    const available = Boolean(reportFor(state,repo));
    return '<button type="button" class="repo-item" data-act="repo"' + attr('id',repo.id)
      + ' aria-pressed="' + (repo.id === active.id) + '"' + (analyzing ? ' disabled' : '') + '><span><strong>' + escape(repo.name) + '</strong>'
      + badge(scopeLabel(repo.visibility),repo.visibility === 'public' ? 'green' : 'amber') + '</span><small>'
      + escape(repo.tech + ' · ' + t('repos.updatedDays',{days:repo.days})) + '</small><span class="repo-report-marker'
      + (available ? ' has-report' : '') + '">' + icon(available ? 'check' : 'file')
      + escape(t(available ? 'repos.reportReady' : 'repos.reportPending')) + '</span></button>';
  }).join('');
  const picker = '<div class="compact-repo-picker">' + field(t('repos.switch'),
    '<select id="repo-switch"' + (analyzing ? ' disabled' : '') + '>' + visible.map(repo => option(repo.id,repo.name,active.id)).join('') + '</select>') + '</div>';
  const tabButtons = ['code','ownership','collab'].map(key => '<button data-act="repo-tab" type="button"' + attr('id',key)
    + ' aria-pressed="' + (state.repoTab === key) + '">' + escape(t('repos.' + key)) + '</button>').join('');
  const status = running ? analysisProgress(operation)
    : attempt?.state === 'failed' ? '<div class="notice red" role="status"><strong>' + escape(t('analysis.failed'))
      + '</strong>' + escape(t('analysis.timedout')) + '</div>'
    : attempt?.state === 'success' ? '<div class="notice report-ok" role="status"><span class="feature-icon">' + icon('check')
      + '</span><div><strong>' + escape(t('analysis.reportReady')) + '</strong><p>' + escape(t('analysis.updated',{repo:active.name}))
      + '</p></div></div>' : '';
  const [commits,pulls,reviews,ci] = activityFor(active,state.range);
  const showHeaderAction = report || running || attempt?.state === 'failed';
  const analyzeAction = btn(icon('pulse') + escape(t(running ? 'analysis.running' : attempt?.state === 'failed' ? 'action.retry' : 'action.analyze')),
    'analyze','primary small',operation ? 'disabled' : '');
  const related = milestonesFor(state).findIndex((milestone,i) => milestone.reportGap && milestone.repo === active.id
    && stateOf(state,i) === 'ready');
  return intro + toolbar + '<div class="repo-layout"><section class="panel repo-picker">' + panelHead(t('repos.list'))
    + '<div class="repo-list">' + list + '</div></section><article class="panel repo-main" aria-labelledby="repo-title">' + picker + '<header class="repo-head">'
    + '<div class="panel-head"><div><h2 id="repo-title">' + escape(active.name) + '</h2><p class="subtle">' + escape(repoText(active,'description'))
    + '</p></div>' + (showHeaderAction ? analyzeAction : '') + '</div>' + tags(active.stack) + '</header>' + status
    + '<div class="repo-report">' + (report
      ? '<section class="report-activity"><header><h3>' + escape(t('repos.activity')) + '</h3><small>' + escape(rangeLabel(state.range))
        + '</small></header><div class="report-counters">' + [['analysis.commitCount',commits],['analysis.prCount',pulls],['analysis.reviewCount',reviews],['analysis.workflowCount',ci]]
          .map(([key,count]) => '<span>' + escape(t(key,{count})) + '</span>').join('') + '</div><p>' + escape(t('repos.activityHint'))
        + '</p></section><div class="tabs" role="group"' + labelAttr(t('repos.aboutReport')) + '>' + tabButtons + '</div>'
        + '<div id="repo-details">' + reportDetail(report,state.repoTab,state.range,runtime.evidenceFocus === active.id) + '</div>'
        + '<section class="report-next"><div><h3>' + escape(t('repos.nextFromReport')) + '</h3><p>' + escape(repoText(report,'gap'))
        + '</p></div><div class="action-row">'
        + (related < 0 ? '' : btn(icon('branch') + escape(t('repos.openMilestone')),'focus-milestone','primary small',attr('id',related)))
        + btn(icon('bot') + escape(t('repos.askAboutReport')),'ask-evidence','secondary small',attr('id',active.id)) + '</div></section>'
        + reportHistory(state,active)
      : blank(t('repos.noReport'),t('repos.noReportCopy'),showHeaderAction ? '' : analyzeAction)) + '</div></article></div>';
}
