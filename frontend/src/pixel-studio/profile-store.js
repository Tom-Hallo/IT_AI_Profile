import {repos, scopes} from './data.js';
import {messages} from './messages.js';
import {paths, taskFor} from './roadmap-model.js';

export const profileKey = 'it-talent-pixel:profile-v1';
const sessionKey = 'it-talent-pixel:preview';
const connectionKey = sessionKey + ':github';

const emptyPlan = () => ({done:[],checks:{},awards:{},notes:[],history:[],reviewed:[]});

const seedReports = ['student-club-api','portfolio-lab'];
const legacyTaskKeys = {
  'Ghi lại dự án, công nghệ và phần bạn trực tiếp xây dựng.':'path.backend.0.task',
  'Kiểm tra hai trường hợp: chủ câu lạc bộ xóa thành công và thành viên bị từ chối.':'path.backend.1.task',
  'Thêm test xóa câu lạc bộ với quyền chủ sở hữu và chạy CI.':'path.backend.1.task',
  'Rà soát schema và chọn một truy vấn để tối ưu.':'path.backend.2.task',
  'Mô tả cách API, cơ sở dữ liệu và worker phối hợp.':'path.backend.3.task',
  'Viết một case study từ tính năng bạn trực tiếp xây dựng.':'path.backend.4.task'
};

function restorePlan(goal, stored={}) {
  const plan = {...emptyPlan(),...stored};
  const milestones = paths[goal];
  const done = new Set(Array.isArray(plan.done) ? plan.done : []);
  plan.done = [];
  milestones.forEach((milestone,index) => {
    if (done.has(index) && milestone.needs.every(dep => plan.done.includes(dep))) plan.done.push(index);
  });
  const notes = Array.isArray(plan.notes) ? plan.notes.filter(note => note && milestones[note.i]) : [];
  plan.notes = notes.map(note => {
    if (note.key || typeof note.task !== 'string') return note;
    const milestone = milestones[note.i];
    const gapKey = 'repo.' + milestone.repo + '.gap';
    const task = taskFor(goal,note.i);
    if (messages[gapKey]?.[0] === note.task) return {...note,key:gapKey,repo:milestone.repo};
    const key = Object.hasOwn(legacyTaskKeys,note.task) ? legacyTaskKeys[note.task]
      : messages[task.key]?.[0] === note.task ? task.key : null;
    return key ? {...note,key} : note;
  });
  return plan;
}

export function loadProfile() {
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(profileKey) || '{}') ?? {}; } catch {}
  const {
    done, notes, analyzed, appliedAnalysis, lastAnalysis,
    access, scope, plans, ...profile
  } = stored;
  const legacyReports = Array.isArray(analyzed) ? repos.filter(repo => analyzed.includes(repo.id)
    && !profile.snapshots?.some(snapshot => snapshot.repo === repo.id)).map(repo => repo.id) : [];
  const backend = plans?.backend ?? {done:Array.isArray(done) ? done : [0],notes};
  return {
    range:90, repo:'student-club-api', repoTab:'code', synced:false,
    snapshots:[], skillBasis:[], claimEvidence:[], focusScore:'student-club-api',
    attempts:[], audit:[], cv:null, template:'plain', job:null, savedJobs:[], share:null, simulateFailure:false,
    ...profile,
    seededReports:[...new Set([...(profile.seededReports ?? seedReports),...legacyReports])],
    access:'public', scope:'public',
    goal:Object.hasOwn(paths, profile.goal) ? profile.goal : 'backend',
    plans:{backend:restorePlan('backend',backend),frontend:restorePlan('frontend',plans?.frontend)}
  };
}

export function readSession() {
  try {
    if (sessionStorage.getItem(sessionKey) !== 'yes') return null;
    const connection = JSON.parse(sessionStorage.getItem(connectionKey) || 'null');
    const access = ['none','public','combined'].includes(connection?.access) ? connection.access : 'public';
    const scope = access === 'combined' && scopes.includes(connection?.scope) ? connection.scope : 'public';
    return {access,scope};
  } catch {
    return null;
  }
}

export function writeSession(active) {
  try {
    if (active) sessionStorage.setItem(sessionKey,'yes');
    else {
      sessionStorage.removeItem(sessionKey);
      sessionStorage.removeItem(connectionKey);
    }
  } catch {}
}

export function saveProfile(state,signedIn) {
  const {access,scope,...profile} = state;
  try { localStorage.setItem(profileKey,JSON.stringify(profile)); } catch {}
  if (signedIn) {
    try { sessionStorage.setItem(connectionKey,JSON.stringify({access,scope})); } catch {}
  }
}

export function findSharedProfile(id) {
  try {
    const share = JSON.parse(localStorage.getItem(profileKey))?.share;
    if (share?.id !== id) return null;
    const scores = share.scores.map(item => {
      const repo = repos.find(candidate => candidate.visibility === 'public' &&
        (item.repo ? candidate.id === item.repo : messages['repo.' + candidate.id + '.skill'][0] === item.name));
      return repo ? {repo:repo.id,score:item.score} : null;
    }).filter(Boolean);
    return {...share,scores};
  } catch {
    return null;
  }
}
