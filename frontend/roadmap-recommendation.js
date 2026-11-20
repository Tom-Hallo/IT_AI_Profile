import {scoredRepos} from './model.js';
import {milestonesFor, nextStep, planFor, stateOf, taskFor} from './roadmap-model.js';

export function recommendationFor(state) {
  const next = nextStep(state);
  if (next < 0) return {index:next};
  const visible = scoredRepos(state);
  const milestones = milestonesFor(state);
  const open = milestones.map((milestone,index) => ({...milestone,index}))
    .filter(item => item.reportGap && stateOf(state,item.index) === 'ready');
  const plan = planFor(state);
  const scoped = state.snapshots.filter(item => item.scope === state.scope && item.range === state.range);
  const recent = new Map();
  for (const item of scoped) if (!recent.has(item.repo)) recent.set(item.repo,item);
  const snapshot = [...recent.values()].find(item => !plan.reviewed.includes(item.id)
    && visible.some(repo => repo.id === item.repo) && open.some(step => step.repo === item.repo));
  const index = snapshot ? open.find(item => item.repo === snapshot.repo).index : next;
  const source = milestones[index].reportGap ? visible.find(repo => repo.id === milestones[index].repo) : null;
  const task = source ? {key:'repo.' + source.id + '.gap',repo:source.id} : taskFor(state.goal,index);
  const previous = snapshot ? scoped.find(item => item.repo === snapshot.repo && item.id !== snapshot.id) : null;
  return {snapshot,previous,index,source,task};
}
