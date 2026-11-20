import {jobs, jobRole} from './data.js';
import {dateLabel, sourceLabel, t} from './i18n.js';
import {repoById, sourceSkills, wordsIn} from './model.js';
import {milestoneText} from './roadmap-model.js';
import {attr, badge, blank, brand, btn, checkRow, details, escape, field, heading, icon, labelAttr, languagePicker, panelHead, tags} from './ui.js';

export function jobsView(state,runtime) {
  const query = runtime.jobQuery.toLowerCase().trim();
  const entries = jobs.filter(job => (jobRole(job) + ' ' + job.needs.join(' ') + ' ' + t('jobs.' + job.id + '.location')).toLowerCase().includes(query));
  const job = state.job;
  const known = sourceSkills(state);
  const requirements = job?.needs.map(skill => {
    const sources = [...(known.get(skill.toLowerCase())?.sources ?? [])];
    const status = sources.includes('github') ? 'has' : sources.length ? 'partial' : 'missing';
    return {skill,sources,status};
  }) ?? [];
  const matched = requirements.filter(item => item.status === 'has').length;
  const comparison = requirements.map(({skill,sources,status}) => '<li><div><strong>' + escape(skill) + '</strong>'
    + badge(t('jobs.' + status),status === 'has' ? 'green' : status === 'partial' ? 'amber' : '') + '</div><p>'
    + escape(t('jobs.' + status + 'Reason')) + '</p>' + (sources.length ? tags(sources.map(sourceLabel)) : '') + '</li>').join('');
  const match = '<article class="panel">' + panelHead(t('jobs.compare'),t('jobs.compareCopy'))
    + (job ? '<div class="panel-head"><h3>' + escape(jobRole(job)) + '</h3>' + badge(requirements.length
      ? t('jobs.matchCount',{matched,total:requirements.length}) : t('jobs.undetected'),'green') + '</div>'
      + (requirements.length ? '<ul class="job-evidence-list">' + comparison + '</ul>' : '<p class="subtle">' + escape(t('jobs.exampleTech')) + '</p>')
      : blank(t('jobs.none'),t('jobs.noneCopy'))) + '</article>';
  return heading(t('nav.jobs'),t('jobs.intro'))
    + '<div class="columns"><div class="stack"><article class="panel">' + panelHead(t('jobs.search'))
    + '<form id="job-search" class="field-row">' + field(t('jobs.keyword'),'<input name="query" value="' + escape(runtime.jobQuery)
      + '" placeholder="Python, FastAPI, TypeScript">') + '<button class="button secondary" type="submit">' + escape(t('jobs.searchAction')) + '</button></form>'
    + '<div class="rows view-rows">' + (entries.length ? entries.map(entry => '<div class="job-row"><h3>' + escape(jobRole(entry))
      + '</h3><p class="subtle">' + escape(t('jobs.' + entry.id + '.company') + ' · ' + t('jobs.' + entry.id + '.location')) + '</p><div class="action-row">'
      + btn(escape(t('jobs.matchAction')),'use-job','secondary small',attr('id',entry.id))
      + btn(escape(t(state.savedJobs.includes(entry.id) ? 'jobs.unsave' : 'jobs.save')),'save-job','quiet small',attr('id',entry.id))
      + '</div></div>').join('') : blank(t('jobs.noMatch'),t('jobs.noMatchCopy'))) + '</div></article>'
    + '<article class="panel">' + panelHead(t('jobs.paste')) + '<form id="jd-form" class="stack">'
    + field(t('jobs.description'),'<textarea name="jd" rows="4" maxlength="4000" placeholder="' + escape(t('jobs.placeholder'))
      + '" required>' + escape(runtime.jdText) + '</textarea>')
    + '<button class="button primary" type="submit">' + escape(t('jobs.analyze')) + '</button></form></article></div>' + match + '</div>';
}

function cvFeedback(draft,job) {
  const {name,role,body} = draft;
  if (!body.trim()) return '<p class="notice amber">' + escape(t('cv.needContent')) + '</p>';
  const detected = wordsIn(body);
  const expected = job?.needs ?? [];
  const missing = expected.filter(word => !wordsIn(body,[word]).length);
  const named = Boolean(name.trim() && role.trim());
  const numeric = /\b[0-9]+(?:\b|%)/.test(body);
  const coverage = expected.length
    ? ['cv.atsCoverage',{matched:expected.length - missing.length,total:expected.length}]
    : ['cv.atsNoJD'];
  const checks = [
    [named,named ? 'cv.atsName' : 'cv.atsNeedName'],
    [Boolean(detected.length),detected.length ? 'cv.detected' : 'cv.needStack',{stack:detected.join(', ')}],
    [numeric,numeric ? 'cv.hasNumbers' : 'cv.needNumbers'],
    [!missing.length,...coverage]
  ];
  if (missing.length) checks.push([false,'cv.atsMissing',{stack:missing.join(', ')}]);
  return '<ul class="cv-checks">' + checks.map(([pass,key,fields]) => '<li data-pass="' + pass + '">'
    + icon(pass ? 'check' : 'info') + escape(t(key,fields)) + '</li>').join('') + '</ul>';
}

export function cvView(state,runtime) {
  const draft = runtime.cvDraft;
  return heading(t('nav.cv'),t('cv.intro'))
    + '<div class="columns"><article class="panel cv-editor">' + panelHead(t('cv.draft')) + '<form id="cv-form" class="cv-controls">'
    + field(t('cv.name'),'<input name="name" required maxlength="70" value="' + escape(draft.name) + '">')
    + field(t('cv.role'),'<input name="role" required maxlength="70" value="' + escape(draft.role) + '">')
    + field(t('cv.content'),'<textarea name="body" rows="8" maxlength="6000" placeholder="' + escape(t('cv.placeholder'))
      + '" required>' + escape(draft.body) + '</textarea>')
    + field(t('cv.import'),'<input id="cv-upload" type="file" accept=".txt,.md,text/plain,text/markdown">')
    + '<div class="action-row"><button class="button primary" type="submit">' + escape(t('cv.save')) + '</button>'
    + btn(escape(t('cv.example')),'cv-example') + '</div></form></article>'
    + '<article class="panel cv-preview">' + panelHead(t('cv.preview'),t('cv.previewCopy'))
    + '<div class="tabs" role="group"' + labelAttr(t('cv.templates')) + '>' + ['plain','tech'].map(key =>
      btn(escape(t('cv.' + key)),'cv-template','',attr('id',key) + ' aria-pressed="' + (state.template === key) + '"')).join('') + '</div>'
    + '<div class="cv-paper" data-template="' + escape(state.template) + '"><h2 id="cv-name">' + escape(draft.name)
    + '</h2><p id="cv-role">' + escape(draft.role) + '</p><div class="cv-body" id="cv-body">' + escape(draft.body || t('cv.empty')) + '</div></div>'
    + '<div class="action-row cv-exports">' + btn(escape(t('cv.text')),'cv-export','secondary small')
    + btn(escape(t('cv.print')),'cv-print','secondary small') + '</div></article></div>'
    + '<article class="panel cv-feedback view-rows">' + panelHead(t('cv.ats'),t('cv.atsCopy'))
    + btn(escape(t('cv.check')),'cv-check','secondary small') + '<div id="ats-result" aria-live="polite">' + (runtime.atsChecked ? cvFeedback(draft,state.job) : '') + '</div></article>';
}

export function dataView(state,runtime) {
  const checked = runtime.privateAI;
  const share = state.share;
  const href = share ? location.origin + location.pathname + '#share/' + share.id : '';
  return heading(t('data.heading'),t('data.intro'))
    + '<div class="columns"><article class="panel stack">' + panelHead(t('data.connection'))
    + details([[t('data.github'),badge(t('data.' + (state.access === 'none' ? 'disconnected' : state.access)),state.access === 'none' ? '' : 'green')],
      [t('data.send'),badge(t(checked ? 'data.consented' : 'data.noConsent'),checked ? 'green' : 'amber')]])
    + '<p class="subtle">' + escape(t('data.consentCopy')) + '</p><div class="action-row">'
    + (checked ? btn(escape(t('data.revoke')),'revoke-ai','secondary small') : btn(escape(t('data.allowAI')),'private-ai','secondary small',
      state.access !== 'combined' ? 'disabled' : ''))
    + (state.access === 'none' ? btn(escape(t('repos.connect')),'reconnect','secondary small')
      : btn(escape(t('privacy.disconnect')),'disconnect','quiet small')) + '</div></article>'
    + '<article class="panel stack">' + panelHead(t('data.share')) + '<p class="subtle">' + escape(t('data.shareIntro')) + '</p>'
    + (share ? field(t('data.shareLink'),'<input id="share-link" readonly value="' + escape(href) + '">')
      + '<div class="action-row"><a class="button secondary small" href="#share/' + escape(share.id) + '" target="_blank" rel="noopener">'
      + escape(t('data.shareOpen')) + ' ' + icon('arrow') + '</a>' + btn(escape(t('data.shareCopy')),'copy-share','secondary small')
      + btn(escape(t('data.shareRevoke')),'revoke-share','danger small') + '</div>'
      : btn(escape(t('data.sharePreview')),'share-start','secondary small')) + '</article></div>'
    + '<article class="panel view-rows">' + panelHead(t('data.audit'),t('data.auditCopy')) + auditRows(state.audit) + '</article>';
}

function auditRows(items) {
  if (!items.length) return '<p class="subtle">' + escape(t('data.noLogs')) + '</p>';
  return '<ul class="audit-list">' + items.slice(0,8).map(item => {
    const text = item.key ? t(item.key,{
      ...item.fields, sources:item.fields?.sources?.map(sourceLabel).join(', '),
      name:item.fields?.goal ? milestoneText(item.fields.goal,item.fields.i) : undefined
    }) : item.text;
    return '<li><time datetime="' + new Date(item.at).toISOString() + '">'
      + escape(dateLabel(item.at,{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'})) + '</time><span>'
      + escape(text) + '</span></li>';
  }).join('') + '</ul>';
}

export function statusView(state) {
  const entries = state.attempts
    .filter(item => state.access === 'combined' || state.access === 'public' && repoById(item.repo)?.visibility === 'public')
    .map(item => ({at:item.at,text:item.repo + ' · ' + t(item.state === 'failed' ? 'status.timeout' : 'analysis.success')}));
  return heading(t('nav.status'),t('status.intro'))
    + '<div class="columns"><article class="panel stack">' + panelHead(t('status.environment'))
    + details([[t('status.frontend'),badge(t('status.open'),'green')],[t('status.sync'),escape(t('status.sample'))],
      [t('status.worker'),escape(t('status.workerCopy'))]])
    + '<details class="status-tests"><summary>' + escape(t('status.testHeading')) + '</summary>'
    + checkRow(t('status.simulate'),'simulate-error',state.simulateFailure)
    + '<p class="subtle">' + escape(t('status.retry')) + '</p></details></article><article class="panel">'
    + panelHead(t('status.log')) + auditRows(entries) + '</article></div>';
}

export function shareView(share,inStudio) {
  const back = '<a href="' + (inStudio ? '#studio/dashboard' : '#about') + '" class="button secondary">' + escape(t('action.back')) + '</a>';
  return '<main class="share-view"><header class="share-top">' + brand(inStudio) + languagePicker() + '</header>' + (share
    ? heading(t('data.profile'),t('data.profileCopy'),back)
      + '<div class="stack">' + (share.repos.length ? '<article class="panel">' + panelHead(t('data.sharePublicRepos')) + tags(share.repos) + '</article>' : '')
      + (share.scores.length ? '<article class="panel">' + panelHead(t('data.sharePublicScores'))
        + details(share.scores.map(item => [t('repo.' + item.repo + '.skill'),escape(item.score + '/100')])) + '</article>' : '')
      + (share.declared.length ? '<article class="panel">' + panelHead(t('profile.self')) + tags(share.declared,'blue') + '</article>' : '') + '</div>'
    : '<article class="panel">' + blank(t('data.unavailable'),t('data.unavailableCopy'),back) + '</article>') + '</main>';
}
