import {jobRole, repos} from './data.js';
import {radarComparison} from './analysis-data.js';
import {getLanguage, sourceLabel, t} from './i18n.js';
import {codeReferenceLabel, matchesCodeReference} from './evidence.js';
import {radarScores, repositorySkills, scoredRepos} from './model.js';
import {milestoneText, milestonesFor, nextStep, stateOf, taskFor} from './roadmap-model.js';

const answer = (parts,used=[],source=null,action=null) => ({parts,used,source,action});
const repoCopy = (repo,field) => 'repo.' + repo.id + '.' + field;
const repoSource = repo => ({label:repo.file,action:'evidence',id:repo.id});
const routeSource = (route,key) => ({route,key});
const roadmapSource = (goal,id) => ({action:'milestone',goal,id});

function normalize(value) {
  return value.toLowerCase().normalize('NFD').replace(/\p{M}/gu,'').replaceAll('đ','d');
}

export function answerMentor(state, question, chosen, privateAI, context={}) {
  const query = normalize(question);
  const has = name => chosen.has(name);
  const canReadPrivate = has('github') && has('private') && privateAI;
  const wantsPrivate = /\bprivate\b|rieng tu|queue-lab/.test(query);
  const inScope = has('github') || has('report') ? scoredRepos(state) : [];
  const reports = inScope.filter(repo => repo.visibility === 'public' || canReadPrivate);
  const requested = repos.find(repo => query.includes(repo.name))?.id ?? context.repoId;
  const repo = requested ? reports.find(item => item.id === requested) : reports[0];
  const need = name => answer([['mentor.needSource',{source:name}]]);

  if (context.requestedMetric) {
    if (!has('report')) return need('report');
    if (reports.length !== inScope.length) return answer(['mentor.privateRequired']);
    const metric = radarScores(reports).find(item => item.key === context.requestedMetric);
    if (!metric) return answer(['mentor.noRepo']);
    const comparison = radarComparison(state,reports);
    const trend = comparison?.metrics[metric.key];
    const used = ['report'];
    if (reports.some(item => item.visibility === 'private')) used.push('github','private');
    const parts = trend
      ? [['mentor.metricComparison',{metric:metric.key,before:trend.before,current:trend.current}]]
      : [['mentor.metricCurrent',{metric:metric.key,current:metric.score}],'analysis.noComparison'];
    const test = metric.key === 'testing' && has('github')
      && comparison?.addedTests.find(ref => reports.some(item => matchesCodeReference(item,ref)));
    if (test) {
      if (!used.includes('github')) used.push('github');
      parts.push(['mentor.metricEvidence',{file:test.file,start:test.start,end:test.end}]);
    }
    return answer(parts,used,{action:'radar-source',id:metric.key,key:'metric.' + metric.key});
  }

  if (context.snippet) {
    if (!has('github')) return need('github');
    const linked = inScope.find(item => matchesCodeReference(item,context.snippet));
    if (!linked) return answer(['mentor.snippetUnavailable']);
    if (linked.visibility === 'private' && !canReadPrivate) return answer(['mentor.privateRequired']);
    const used = ['github'];
    if (linked.visibility === 'private') used.push('private');
    const parts = [repoCopy(linked,'result'),repoCopy(linked,'gap')];
    if (has('report')) {
      used.push('report');
      parts.unshift(['mentor.score',{repoId:linked.id,score:linked.score,confidence:linked.confidence}]);
    }
    return answer(parts,used,{...repoSource(linked),snippet:context.snippet});
  }
  if (/doan (code|nay)|code snippet|this snippet/.test(query)) return answer(['mentor.snippetNeeded']);
  if (wantsPrivate) {
    if (!canReadPrivate) return answer(['mentor.privateRequired']);
    const queue = reports.find(item => item.visibility === 'private');
    return queue
      ? answer([repoCopy(queue,'result'),repoCopy(queue,'gap')],['github','private'],repoSource(queue))
      : answer(['mentor.noPrivate']);
  }
  if (/\bcv\b|\bats\b|ho so ung tuyen|\bresume\b/.test(query)) {
    if (!has('cv')) return need('cv');
    return state.cv?.body.trim()
      ? answer([['mentor.cvAnswer',{count:state.cv.body.trim().split(/\s+/).length}]],['cv'],routeSource('cv','mentor.cvLabel'))
      : answer(['mentor.cvEmpty'],[],routeSource('cv','nav.cv'));
  }
  if (/\bjd\b|viec lam|tuyen dung|mo ta cong viec|\bjob\b/.test(query)) {
    if (!has('job')) return need('job');
    if (!state.job) return answer(['mentor.jobEmpty'],[],routeSource('jobs','nav.jobs'));
    const githubReports = has('github') ? reports : [];
    const known = new Set(repositorySkills(githubReports).map(skill => skill.toLowerCase()));
    const used = ['job'];
    if (githubReports.length) used.push('github');
    if (githubReports.some(item => item.visibility === 'private')) used.push('private');
    const gaps = state.job.needs.filter(skill => !known.has(skill.toLowerCase()));
    const message = githubReports.length && state.job.needs.length
      ? gaps.length ? ['mentor.jobGap',{skills:gaps}] : 'mentor.jobCovered'
      : ['mentor.jobRequirements',{skills:state.job.needs}];
    return answer([message],used,{route:'jobs',jobId:state.job.id ?? null});
  }
  if (/lo trinh|roadmap|\bbuoc\b|\btuan\b|\bmoc\b|milestone|\bweek\b|next step/.test(query)) {
    if (!has('roadmap')) return need('roadmap');
    const goal = state.goal;
    const hinted = milestonesFor(state).findIndex((_,i) => {
      const name = normalize(milestoneText(goal,i));
      return name.length > 0 && query.includes(name);
    });
    const i = hinted >= 0 ? hinted : context.milestone ?? nextStep(state);
    if (i < 0) return answer(['mentor.done'],['roadmap'],routeSource('roadmap','nav.roadmap'));
    const milestone = milestonesFor(state)[i];
    const needs = milestone.needs.filter(dep => stateOf(state,dep) !== 'done');
    const source = roadmapSource(goal,i);
    if (needs.length) return answer([['mentor.requirements',{goal,index:i,needs}]],['roadmap'],source);
    const task = taskFor(goal,i);
    if (stateOf(state,i) === 'ready' && /them|len lich|tao viec|\badd\b|\bschedule\b/.test(query)) {
      return answer([['mentor.offer',{goal,index:i}]],['roadmap'],source,{goal,i,task});
    }
    return answer([task.key,['mentor.proof',{goal,index:i}]],['roadmap'],source);
  }
  if (requested || /diem|ky nang|kiem thu|bang chung|github|repo|test|code|score|skill|evidence|report/.test(query)) {
    if (!has('report') && !has('github')) return need('github');
    if (!repo) return answer(['mentor.noRepo']);
    const used = [has('github') ? 'github' : 'report'];
    if (repo.visibility === 'private') used.push('private');
    if (has('github') && has('report')) used.push('report');
    const parts = has('github') ? [repoCopy(repo,'result'),repoCopy(repo,'gap')] : [repoCopy(repo,'gap')];
    if (has('report')) parts.unshift(['mentor.score',{repoId:repo.id,score:repo.score,confidence:repo.confidence}]);
    const source = has('github') ? repoSource(repo) : routeSource('dashboard','nav.dashboard');
    return answer(parts,used,source);
  }
  return answer(['mentor.generic']);
}

export function replyCopy(part) {
  if (typeof part === 'string') return t(part);
  const [key,values] = part;
  const {goal,index,needs,repoId,source,skills,metric,...plain} = values;
  const join = new Intl.ListFormat(getLanguage() === 'en' ? 'en' : 'vi',{type:'conjunction'});
  if (goal) {
    plain.name = milestoneText(goal,index);
    plain.proof = milestoneText(goal,index,'proof');
    if (needs) plain.needs = join.format(needs.map(i => milestoneText(goal,i)));
  }
  if (repoId) plain.name = t('repo.' + repoId + '.skill');
  if (source) plain.name = sourceLabel(source);
  if (metric) plain.name = t('metric.' + metric);
  if (skills) {
    plain.skills = join.format(skills);
    plain.requirements = skills.length ? plain.skills : t('mentor.jobNoRequirements');
  }
  return t(key,plain);
}

export function replySourceLabel(source) {
  if (source.snippet) return codeReferenceLabel(source.snippet);
  if (source.goal) return milestoneText(source.goal,source.id);
  if (Object.hasOwn(source,'jobId')) return jobRole({id:source.jobId});
  return source.key ? t(source.key) : source.label;
}
