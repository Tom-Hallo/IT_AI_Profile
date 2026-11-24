import assert from 'node:assert/strict';
import test from 'node:test';
import {chooseRoadmap, chooseMilestone} from '../src/pixel-studio/roadmap-selection.js';

const roads = [
  {id:1,goal:'backend',milestones:[{}]},
  {id:2,goal:'backend',milestones:[{}]},
  {id:3,goal:'frontend',milestones:[{}]},
  {id:4,goal:'devops',milestones:[]}
];
test('restore second roadmap for same goal after reload', () => {
  assert.equal(chooseRoadmap(roads,{storedId:2,goal:'backend'}).id,2);
});
test('explicit roadmap and goal selections are respected', () => {
  assert.equal(chooseRoadmap(roads,{targetId:3,currentId:2,goal:'backend'}).id,3);
  assert.equal(chooseRoadmap(roads,{currentId:2,goal:'frontend',goalWasChosen:true}).id,3);
  assert.equal(chooseRoadmap(roads,{currentId:2,goal:'fullstack',goalWasChosen:true}),null);
  assert.equal(chooseRoadmap(roads,{targetId:999,goal:'backend'}),null);
});
test('a roadmap with no remaining milestones is a valid selected roadmap', () => {
  assert.equal(chooseRoadmap(roads,{storedId:4,goal:'backend'}).id,4);
});
test('keep the current or saved milestone and safely fall back if deleted', () => {
  const items = [{id:11},{id:12},{id:13}];
  assert.equal(chooseMilestone(items,13,12),13);
  assert.equal(chooseMilestone(items,99,12),12);
  assert.equal(chooseMilestone(items,null,13),13);
  assert.equal(chooseMilestone(items,99,98),11);
  assert.equal(chooseMilestone([],11,12),null);
});
