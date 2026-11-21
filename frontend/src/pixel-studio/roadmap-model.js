import {t} from './i18n.js';

export const paths = {
  backend:[
    {icon:'terminal',needs:[],minutes:25,repo:'student-club-api'},
    {icon:'check',needs:[0],minutes:45,repo:'student-club-api',reportGap:true},
    {icon:'database',needs:[0],minutes:60,repo:'student-club-api'},
    {icon:'branch',needs:[1,2],minutes:50,repo:'queue-lab',reportGap:true},
    {icon:'file',needs:[3],minutes:40,repo:'student-club-api'}
  ],
  frontend:[
    {icon:'terminal',needs:[],minutes:25,repo:'portfolio-lab'},
    {icon:'check',needs:[0],minutes:40,repo:'portfolio-lab',reportGap:true},
    {icon:'grid',needs:[0],minutes:50,repo:'portfolio-lab'},
    {icon:'branch',needs:[1,2],minutes:55,repo:'portfolio-lab'},
    {icon:'file',needs:[3],minutes:40,repo:'portfolio-lab'}
  ]
};

export const milestoneKey = (goal, index, field) => 'path.' + goal + '.' + index + '.' + field;
export const milestoneText = (goal, index, field='name') => t(milestoneKey(goal,index,field));
export const planFor = state => state.plans[state.goal];
export const milestonesFor = state => paths[state.goal];
export const stepsDone = state => planFor(state).done.length;
export const stateOf = (state, index) => {
  const {done} = planFor(state);
  if (done.includes(index)) return 'done';
  return milestonesFor(state)[index].needs.every(dep => done.includes(dep)) ? 'ready' : 'locked';
};
export const nextStep = state => milestonesFor(state).findIndex((_,i) => stateOf(state,i) === 'ready');

const checks = ['check1','check2'];
export const checklist = (state,index) => checks.map(field => ({
  field, label:milestoneText(state.goal,index,field),
  done:planFor(state).checks[index]?.includes(field) ?? false
}));

export function setChecklist(state,index,field,checked) {
  if (stateOf(state,index) !== 'ready' || !checks.includes(field)) return;
  const plan = planFor(state);
  const values = new Set(plan.checks[index] ?? []);
  if (checked) values.add(field);
  else values.delete(field);
  plan.checks[index] = [...values];
}

export function evidenceURL(raw) {
  try {
    const url = new URL(raw);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

export function addRoadHistory(plan,kind,index,at=Date.now()) {
  plan.history = [{kind,index,at},...plan.history].slice(0,30);
}

export function completeMilestone(state,index,link) {
  if (stateOf(state,index) !== 'ready' || checklist(state,index).some(item => !item.done)) return false;
  const plan = planFor(state);
  const at = Date.now();
  plan.done.push(index);
  plan.awards[index] = {at,link};
  addRoadHistory(plan,'Done',index,at);
  return true;
}

export function dependentMilestones(state,index) {
  const done = planFor(state).done;
  const affected = new Set([index]);
  milestonesFor(state).forEach((milestone,i) => {
    if (done.includes(i) && milestone.needs.some(dep => affected.has(dep))) affected.add(i);
  });
  return [...affected];
}

export function undoMilestone(state,index) {
  const plan = planFor(state);
  const affected = dependentMilestones(state,index);
  plan.done = plan.done.filter(i => !affected.includes(i));
  const at = Date.now();
  for (const i of affected.reverse()) addRoadHistory(plan,'Undo',i,at);
}

export function addRoadTask(state,index,task) {
  if (!milestonesFor(state)[index] || stateOf(state,index) !== 'ready') return false;
  const plan = planFor(state);
  if (plan.notes.some(note => note.i === index && note.key === task.key && note.repo === task.repo)) return false;
  plan.notes.push({...task, i:index, id:crypto.randomUUID(), done:false});
  addRoadHistory(plan,'Plan',index);
  return true;
}

export const taskLabel = task => task.key ? t(task.key) : task.task;
export const taskFor = (goal,index) => ({key:milestoneKey(goal,index,'task')});

export function achievementOrder(state) {
  const {done,awards} = planFor(state);
  return done.slice().reverse().sort((a,b) => (awards[b]?.at ?? 0) - (awards[a]?.at ?? 0));
}

export const latestAward = state => achievementOrder(state)[0];
