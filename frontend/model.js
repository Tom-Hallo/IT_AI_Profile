import {repos, roleScores, jobs, radarMetrics} from './data.js';
import {t} from './i18n.js';

export const currentRepos = state => state.access === 'none' ? [] : repos.filter(repo =>
  (state.access === 'combined' || repo.visibility === 'public')
  && (state.scope === 'combined' || repo.visibility === state.scope)
  && repo.days <= state.range
);

export function reportFor(state, repo) {
  const snapshot = state.snapshots.find(item => item.repo === repo.id && item.range === state.range
    && (item.scope === state.scope || state.scope === 'combined' && item.scope === repo.visibility));
  if (snapshot) {
    const {score, confidence, radar, commit} = snapshot;
    return {...repo, score, confidence, radar, commit};
  }
  return state.seededReports.includes(repo.id) ? repo : null;
}

export const scoredRepos = state => currentRepos(state).map(repo => reportFor(state,repo)).filter(Boolean);
export const repoById = id => repos.find(repo => repo.id === id);
export const repoSelected = state => currentRepos(state).find(repo => repo.id === state.repo) ?? currentRepos(state)[0];

export function radarScores(reports) {
  if (!reports.length) return [];
  return radarMetrics.map(key => ({
    key,
    label:t('metric.' + key),
    score:Math.round(reports.reduce((total,repo) => total + repo.radar[key],0) / reports.length)
  }));
}

const technologies = [...new Set([...repos.flatMap(repo => repo.stack), ...jobs.flatMap(job => job.needs)])];

export function wordsIn(text, words=technologies) {
  return words.filter(word => {
    const needle = word.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    return new RegExp('(?:^|[^a-z0-9])' + needle + '(?=$|[^a-z0-9])','i').test(text);
  });
}

export function repositorySkills(reports) {
  const skills = new Set(reports.flatMap(repo => repo.stack));
  if (reports.some(repo => repo.id === 'student-club-api')) skills.add('CI/CD');
  return [...skills];
}

export function sourceSkills(state) {
  const sources = [
    ['github', repositorySkills(scoredRepos(state))],
    ['cv', wordsIn(state.cv?.body ?? '')],
    ['declared', state.skillBasis]
  ];
  const skills = new Map();
  for (const [source,names] of sources) {
    for (const name of names) {
      const key = name.toLowerCase();
      if (!skills.has(key)) skills.set(key,{name:technologies.find(skill => skill.toLowerCase() === key) ?? name,sources:new Set()});
      skills.get(key).sources.add(source);
    }
  }
  return skills;
}

export function roleEvidence(state,id) {
  const role = roleScores.find(item => item.id === id);
  if (!role) return null;
  const evidence = scoredRepos(state).filter(repo => role.repos.includes(repo.id));
  if (!evidence.length) return null;
  const metrics = role.weights.map(([key,weight]) => {
    const score = Math.round(evidence.reduce((sum,repo) => sum + repo.radar[key],0) / evidence.length);
    return {key,weight,score,label:t('metric.' + key)};
  });
  const score = Math.round(metrics.reduce((sum,metric) => sum + metric.score * metric.weight,0) / 100);
  const confidence = Math.round(evidence.reduce((sum,repo) => sum + repo.confidence,0) / evidence.length);
  const partial = id === 'backend' && !evidence.some(repo => repo.id === 'student-club-api');
  return {id,score,confidence,metrics,reason:t('rating.' + (partial ? 'backendPartial' : id)),evidence};
}
