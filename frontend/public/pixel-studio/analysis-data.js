import {radarMetrics} from './data.js';
import {codeReference} from './evidence.js';

const rubric = '1.0';
const activity = {
  'student-club-api':[[19,4,6,3],[42,8,12,6],[55,11,17,9]],
  'portfolio-lab':[[0,0,0,0],[26,5,4,3],[34,8,6,5]],
  'fastapi-starter':[[0,0,0,0],[0,0,0,0],[13,2,3,2]],
  'queue-lab':[[12,2,3,2],[19,4,6,4],[29,7,9,7]]
};

export const activityFor = (repo, days) => activity[repo.id][days === 30 ? 0 : days === 90 ? 1 : 2];

export function createSnapshot(repo,state,at=Date.now()) {
  return {
    id:crypto.randomUUID(), repo:repo.id, scope:state.scope, range:state.range, at, rubric,
    score:repo.score, confidence:repo.confidence, radar:{...repo.radar}, commit:repo.commit, tests:testEvidence(repo)
  };
}

function testEvidence(repo) {
  return repo.file.startsWith('tests/') ? [codeReference(repo)] : [];
}

const sampleDays = ['2026-10-25T09:00:00+07:00','2026-11-10T09:00:00+07:00'];

export function reportTimeline(state,repo) {
  const saved = state.snapshots.filter(item => item.repo === repo.id && item.scope === state.scope && item.range === state.range);
  if (state.scope !== 'public' || state.range !== 90 || !state.seededReports.includes(repo.id)
    || !['student-club-api','portfolio-lab'].includes(repo.id)) return saved;
  const current = {
    id:'sample-current-' + repo.id, repo:repo.id, scope:'public', range:90, at:Date.parse(sampleDays[1]), rubric,
    score:repo.score, confidence:repo.confidence, radar:{...repo.radar}, commit:repo.commit, tests:testEvidence(repo), sample:true
  };
  const older = {...current,id:'sample-previous-' + repo.id,at:Date.parse(sampleDays[0])};
  if (repo.id === 'student-club-api') {
    older.score = 55;
    older.confidence = 64;
    older.radar = {...older.radar,testing:55};
    older.commit = '58b4fe2';
    older.tests = [];
  }
  return [...saved,current,older].sort((a,b) => b.at - a.at);
}

export function compareSnapshots(latest, previous) {
  if (!latest || !previous || latest.repo !== previous.repo || latest.scope !== previous.scope
    || latest.range !== previous.range || latest.rubric !== previous.rubric) return null;
  return latest.score - previous.score;
}

export function radarComparison(state,reports) {
  const pairs = reports.map(repo => reportTimeline(state,repo));
  if (!pairs.length || pairs.some(([latest,previous],index) => compareSnapshots(latest,previous) === null
    || latest.rubric !== pairs[0][0].rubric || latest.commit !== reports[index].commit)) return null;
  const metrics = Object.fromEntries(radarMetrics.flatMap(key => {
    if (pairs.some(([latest,previous],index) => latest.radar?.[key] !== reports[index].radar[key]
      || !Number.isFinite(previous.radar?.[key]))) return [];
    const current = Math.round(pairs.reduce((sum,[report]) => sum + report.radar[key],0) / pairs.length);
    const before = Math.round(pairs.reduce((sum,[,report]) => sum + report.radar[key],0) / pairs.length);
    return [[key,{current,before,delta:current - before}]];
  }));
  const addedTests = pairs.flatMap(([latest,previous]) => {
    if (!Array.isArray(latest.tests) || !Array.isArray(previous.tests)) return [];
    return latest.tests.filter(reference => !previous.tests.some(older => older.file === reference.file
      && older.start === reference.start && older.end === reference.end));
  });
  return {metrics,addedTests,rubric:pairs[0][0].rubric};
}
