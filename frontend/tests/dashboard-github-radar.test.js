import assert from 'node:assert/strict';
import test from 'node:test';
import {githubRadarMetrics, RADAR_RUBRIC_VERSION} from '../src/pixel-studio/dashboard-github-metrics.js';
import {radarView, measuredRadarSegments} from '../src/pixel-studio/radar.js';

const ref = (id,kind='verification') => ({
  evidence_id:id,repository_id:7,report_id:4,kind,target:'123'
});
const report = (key,criteria,version=RADAR_RUBRIC_VERSION) => ({
  rubric_version:version,axes:[{key,score:100,criteria}]
});

test('unknown axes remain null and a partial radar still renders', () => {
  const metrics = githubRadarMetrics([report('testing',[{key:'test_change',evidence:ref(1)}])]);
  assert.deepEqual(metrics.map(item => item.score), [null,null,50,null,null]);
  const html = radarView(metrics.map(item => ({...item,label:item.key})),
    1,'Public','90 days',{},'',true);
  assert.match(html,/radar-plot/);
  assert.match(html,/data-score="50"/);
  assert.match(html,/data-score=""/);
  assert.doesNotMatch(html,/data-score="0"/);
  assert.match(html,/50<small>%/);
});

test('combine distinct criteria across reports without inflating duplicate events', () => {
  const a = report('ci',[{key:'workflow_change',evidence:ref(2)}]);
  const b = report('ci',[{key:'completed_check',evidence:ref(3,'collaboration')}]);
  assert.equal(githubRadarMetrics([a,a])[4].score,50);
  assert.equal(githubRadarMetrics([a,b])[4].score,100);
});

test('reject incompatible rubric versions and absent provenance', () => {
  const reports = [report('code',[{key:'source_change',evidence:ref(1)}],'old'),
    report('architecture',[{key:'data_design',evidence:{evidence_id:3}}])];
  assert.ok(githubRadarMetrics(reports).every(item => item.score === null));
});

test('do not use server totals without individual criterion evidence', () => {
  assert.equal(githubRadarMetrics([report('collaboration',[])])[3].score,null);
});


test('partial radar shades only adjacent observed sectors, without inventing missing vertices', () => {
  assert.deepEqual(measuredRadarSegments([.5,null,.5,1,1]), [[2,3],[3,4],[4,0]]);
  assert.deepEqual(measuredRadarSegments([null,null,null,null,null]), []);
  assert.deepEqual(measuredRadarSegments([0,.5,null,null,null]), [[0,1]]);
});
