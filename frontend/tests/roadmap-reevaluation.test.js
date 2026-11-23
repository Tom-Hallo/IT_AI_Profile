import assert from 'node:assert/strict';
import test from 'node:test';
import {summarizeReevaluation, currentEvaluationSuggestions} from '../src/pixel-studio/reevaluation.js';

const evaluation = {snapshot_id:'snapshot-new',evaluation:{checked_milestones:3,verified_skill_count:2}};
const tracking = {suggestions:[
  {id:1,snapshot_id:'snapshot-old',milestone_id:10,state:'pending'},
  {id:2,snapshot_id:'snapshot-new',milestone_id:11,state:'pending'},
  {id:3,snapshot_id:'snapshot-new',milestone_id:12,state:'applied'}
]};

test('only suggestions for the evaluated snapshot appear as current proposals', () => {
  const result = summarizeReevaluation(evaluation,tracking);
  assert.equal(result.kind,'suggestions');
  assert.equal(result.pendingCount,1);
  assert.deepEqual(currentEvaluationSuggestions(result,tracking).map(s=>s.id),[2]);
});

test('no verified GitHub evidence explains missing suggestions without fabricating success', () => {
  const result = summarizeReevaluation({
    snapshot_id:'empty',evaluation:{checked_milestones:3,verified_skill_count:0}
  },{suggestions:[]});
  assert.equal(result.kind,'no-verified-evidence');
  assert.equal(result.pendingCount,0);
});

test('verified skills may be insufficient to complete a milestone', () => {
  const result = summarizeReevaluation(evaluation,{suggestions:[]});
  assert.equal(result.kind,'no-eligible-milestone');
});

test('all completed milestones have a distinct informational outcome', () => {
  const result = summarizeReevaluation({
    snapshot_id:'all-done',evaluation:{checked_milestones:0,verified_skill_count:0}
  },{suggestions:[]});
  assert.equal(result.kind,'all-completed');
});

test('an absent snapshot identifier cannot be confused with successful evaluation', () => {
  assert.throws(()=>summarizeReevaluation({suggestions:[]},{suggestions:[]}),/snapshot ID/);
});

test('old or rejected suggestions never become new proposals', () => {
  const result = summarizeReevaluation(evaluation,{suggestions:[
    {id:4,snapshot_id:'snapshot-old',state:'pending'},
    {id:5,snapshot_id:'snapshot-new',state:'rejected'}
  ]});
  assert.equal(result.pendingCount,0);
});
