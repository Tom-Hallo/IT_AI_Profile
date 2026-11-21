import {t} from './i18n.js';

export const sampleUser = {handle:'minh-dev', name:'Minh Nguyễn'};

export const radarMetrics = [
  'code','architecture','testing','collaboration','ci'
];

export const repos = [
  {
    id:'student-club-api', name:'student-club-api', visibility:'public', days:7,
    tech:'Python', stack:['Python','FastAPI','PostgreSQL','pytest'],
    score:63, confidence:72,
    radar:{code:80,architecture:75,testing:63,collaboration:84,ci:83},
    file:'tests/test_clubs.py', startLine:12, commit:'7c1a4e2', pull:18,
    code:['def test_member_cannot_delete_club(client):','    response = client.delete("/clubs/42")','    assert response.status_code == 403'],
    languages:[['Python',86],['SQL',10],['Shell',4]], structure:['app/api/','app/services/','app/models/','tests/'],
  },
  {
    id:'portfolio-lab', name:'portfolio-lab', visibility:'public', days:58,
    tech:'TypeScript', stack:['TypeScript','React','CSS'],
    score:78, confidence:81,
    radar:{code:86,architecture:77,testing:58,collaboration:70,ci:100},
    file:'src/components/ProjectCard.tsx', startLine:5, commit:'2aa713b', pull:7,
    code:['export function ProjectCard({ name, href }) {','    return <a href={href}>{name}</a>','}'],
    languages:[['TypeScript',74],['CSS',23],['HTML',3]], structure:['src/components/','src/pages/','public/'],
  },
  {
    id:'fastapi-starter', name:'fastapi-starter', visibility:'public', days:118,
    tech:'Python', stack:['Python','FastAPI','pytest'],
    score:65, confidence:76,
    radar:{code:74,architecture:62,testing:66,collaboration:86,ci:100},
    file:'tests/test_health.py', startLine:3, commit:'918de2a', pull:4,
    code:['def test_health(client):','    response = client.get("/health")','    assert response.status_code == 200'],
    languages:[['Python',94],['Shell',6]], structure:['app/','docs/','tests/'],
    fork:true
  },
  {
    id:'queue-lab', name:'queue-lab', visibility:'private', days:16,
    tech:'Python', stack:['Python','Redis','RQ','Docker'],
    score:72, confidence:74,
    radar:{code:76,architecture:82,testing:72,collaboration:78,ci:100},
    file:'tests/test_retry.py', startLine:18, commit:'dd4910a', pull:3,
    code:['def test_retry_on_timeout(queue):','    job = queue.enqueue(simulate_timeout, retry=3)','    assert job.retries_left == 3'],
    languages:[['Python',89],['Dockerfile',8],['Shell',3]], structure:['app/tasks/','app/worker/','tests/'],
  }
];

export const roleScores = [
  {id:'backend',repos:['student-club-api','queue-lab'],weights:[['architecture',40],['testing',35],['code',25]]},
  {id:'frontend',repos:['portfolio-lab'],weights:[['code',40],['testing',35],['architecture',25]]}
];

export const jobs = [
  {id:'backend',needs:['Python','FastAPI','PostgreSQL','Docker','CI/CD']},
  {id:'frontend',needs:['TypeScript','React','CSS','Playwright']},
  {id:'platform',needs:['Python','Redis','Docker','Kubernetes']}
];

export const mentorSources = ['github','report','roadmap','cv','job','private'];
export const scopes = ['public','private','combined'];
export const ranges = [30,90,365];
export const repoText = (repo, field) => t('repo.' + repo.id + '.' + field);
export const jobRole = job => t(job.id ? 'jobs.' + job.id + '.role' : 'jobs.custom');
