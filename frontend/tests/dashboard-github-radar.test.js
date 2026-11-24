import assert from 'node:assert/strict';
import test from 'node:test';
import {githubRadarMetrics} from '../src/pixel-studio/dashboard-github-metrics.js';
import {radarView} from '../src/pixel-studio/radar.js';

function score(technology, points, status='Scored', verified=true) {
  return {
    technology, kind:'language', score:points, status,
    repo:{id:7,full_name:'owner/repo'},
    breakdown: verified ? [{evidence_ids:[11],evidence_kind:'verification'}] : []
  };
}

function roleCriterion(key, points, status='SCORED', verified=true) {
  return {
    key, name:key, type:key === 'api_service_design' ? 'ARCHITECTURE' : 'SKILL',
    score:points, status,
    evidence_refs:verified ? [{verified:true,repository_id:7}] : []
  };
}

test('partial GitHub analysis produces a radar with missing axes, not an empty chart', () => {
  const metrics = githubRadarMetrics({scores:[score('Python', 100)]});
  assert.deepEqual(metrics.map(item => item.score), [100,null,null,null,null]);
  const html = radarView(metrics.map(item => ({...item,label:item.key})),
    1, 'Public', '90 days', {});
  assert.match(html, /radar-plot/);
  assert.match(html, /data-score="100"/);
  assert.match(html, /data-score=""/);
  assert.doesNotMatch(html, /data-score="0"/);
  assert.match(html, /is-unscored/);
});

test('insufficient language cannot become zero or a fake proficiency score', () => {
  const metrics = githubRadarMetrics({
    scores:[score('Python', 100, 'Insufficient'),score('TypeScript', 80, 'Scored', false)]
  });
  assert.deepEqual(metrics.map(item => item.score), [null,null,null,null,null]);
});

test('zero is valid only when a verified rubric actually scored zero', () => {
  const metrics = githubRadarMetrics({scores:[score('HTML', 0)]});
  assert.equal(metrics[0].score, 0);
});

test('role criteria contribute exactly their persisted values, not invented averages', () => {
  const metrics = githubRadarMetrics({
    roles:[{key:'backend_developer',name:'Backend Developer',score:{
      criteria:[
        roleCriterion('backend_language', 78),
        roleCriterion('api_service_design', 65),
        roleCriterion('testing', 55, 'INSUFFICIENT'),
        roleCriterion('ci', 100, 'SCORED', false)
      ]
    }}],
    scores:[score('JavaScript', 100)],
    roleKey:'backend_developer'
  });
  assert.deepEqual(metrics.map(item => item.score), [78,65,null,null,null]);
  assert.equal(metrics[0].evidence.origin, 'role');
  assert.equal(metrics[1].evidence.source, 'api_service_design');
});

test('a marked scored role criterion lacking individually verified links is excluded', () => {
  const metrics = githubRadarMetrics({roles:[{key:'backend',score:{
    criteria:[roleCriterion('backend_language', 100, 'SCORED', false)]
  }}]});
  assert.equal(metrics[0].score, null);
});

test('static Vite or framework detection without a scored source never grants a radar point', () => {
  const metrics = githubRadarMetrics({scores:[{
    kind:'framework',technology:'Vite',score:null,status:'Insufficient',
    breakdown:[{evidence_ids:[]}]
  }]});
  assert.ok(metrics.every(item => item.score === null));
});
