import assert from 'node:assert/strict';
import test from 'node:test';
import {chooseRoadmap, chooseMilestone, resolveRoadmapView} from '../src/pixel-studio/roadmap-selection.js';

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

test('deleted current roadmap restores the valid saved roadmap', () => {
  assert.equal(chooseRoadmap(roads,{currentId:999,storedId:2,goal:'backend'}).id,2);
  assert.equal(chooseRoadmap(roads,{currentId:3,storedId:2,goal:'backend',goalWasChosen:true}).id,2);
  assert.equal(chooseRoadmap(roads,{currentId:1,storedId:2,goal:'backend'}).id,1);
});

const trackingFor = id => ({milestones:[{id:id*10+1},{id:id*10+2}],suggestions:[]});
const loadTracking = async id => trackingFor(id);
const readSaved = id => id*10+2;
const options = {currentId:1,storedId:2,goal:'backend',previousMilestone:11};

test('missing Skill Gap roadmap refreshes a consistent fallback view', async () => {
  const view = await resolveRoadmapView([roads[1]],{
    ...options,pendingFocus:{roadmapId:99,milestoneId:90}
  },loadTracking,readSaved);
  assert.equal(view.focusError,'roadmap');
  assert.equal(view.road.id,2);
  assert.deepEqual(view.tracking,trackingFor(2));
  assert.equal(view.milestone,22);
});

test('missing Skill Gap milestone cannot mix tracking from different roadmaps', async () => {
  const view = await resolveRoadmapView(roads,{
    ...options,pendingFocus:{roadmapId:2,milestoneId:999}
  },loadTracking,readSaved);
  assert.equal(view.focusError,'milestone');
  assert.equal(view.road.id,1);
  assert.deepEqual(view.tracking,trackingFor(1));
  assert.equal(view.milestone,11);
});

test('missing focus milestone reuses fresh tracking for the selected roadmap', async () => {
  const calls = [];
  const view = await resolveRoadmapView(roads,{
    ...options,pendingFocus:{roadmapId:1,milestoneId:999}
  },async id => { calls.push(id); return trackingFor(id); },readSaved);
  assert.equal(view.focusError,'milestone');
  assert.equal(view.road.id,1);
  assert.equal(view.milestone,11);
  assert.deepEqual(calls,[1]);
});

test('valid Skill Gap focus and explicit roadmap selection keep their own milestones', async () => {
  const focused = await resolveRoadmapView(roads,{
    ...options,pendingFocus:{roadmapId:3,milestoneId:31}
  },loadTracking,readSaved);
  assert.equal(focused.focusError,null);
  assert.equal(focused.road.id,3);
  assert.equal(focused.milestone,31);
  const explicit = await resolveRoadmapView(roads,{
    ...options,targetId:2,previousMilestone:21
  },loadTracking,readSaved);
  assert.equal(explicit.road.id,2);
  assert.equal(explicit.milestone,22);
});

test('no remaining roadmap clears tracking and milestone instead of keeping stale data', async () => {
  const view = await resolveRoadmapView([],{
    ...options,pendingFocus:{roadmapId:1,milestoneId:11}
  },loadTracking,readSaved);
  assert.equal(view.focusError,'roadmap');
  assert.equal(view.road,null);
  assert.equal(view.tracking,null);
  assert.equal(view.milestone,null);
});

test('deleted focus roadmap between list and tracking falls back on 404', async () => {
  const view = await resolveRoadmapView(roads,{
    ...options,pendingFocus:{roadmapId:1,milestoneId:11}
  },async id => {
    if (id === 1) throw Object.assign(new Error('Not found'),{status:404});
    return trackingFor(id);
  },readSaved);
  assert.equal(view.focusError,'roadmap');
  assert.equal(view.road.id,2);
  assert.deepEqual(view.tracking,trackingFor(2));
  assert.equal(view.milestone,22);
});

test('network failure rejects the staged view rather than publishing partial data', async () => {
  await assert.rejects(resolveRoadmapView(roads,{
    ...options,targetId:2
  },async () => { throw new Error('Offline'); },readSaved),/Offline/);
});
