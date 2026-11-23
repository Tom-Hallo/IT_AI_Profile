import assert from 'node:assert/strict';
import test from 'node:test';
import {numericScore, reportBackedSkillScore, verifiedSkillScore} from '../src/pixel-studio/score-presentation.js';

test('insufficient or unknown evidence must not appear as zero out of 100', () => {
  assert.equal(verifiedSkillScore(null, 'Insufficient'), null);
  assert.equal(verifiedSkillScore(0, 'Insufficient'), null);
  assert.equal(verifiedSkillScore(81, 'Unknown'), null);
  assert.equal(verifiedSkillScore(undefined, 'Scored'), null);
  assert.equal(verifiedSkillScore(NaN, 'Scored'), null);
});

test('a genuinely scored zero remains zero', () => {
  assert.equal(verifiedSkillScore(0, 'Scored'), 0);
  assert.equal(verifiedSkillScore(86, 'Scored'), 86);
  assert.equal(numericScore(null), null);
  assert.equal(numericScore(0), 0);
});

test('a profile skill is scored only with genuine report-bound verification IDs', () => {
  const item = {score:90,status:'Scored'};
  assert.equal(reportBackedSkillScore(item), null);
  assert.equal(reportBackedSkillScore({...item,breakdown:[
    {evidence_kind:'manifest',evidence_ids:[3]}
  ]}), null);
  assert.equal(reportBackedSkillScore({...item,breakdown:[
    {evidence_kind:'verification',evidence_ids:[18]}
  ]}), 90);
  assert.equal(reportBackedSkillScore({...item,score:0,breakdown:[
    {evidence_kind:'verification',evidence_ids:[18]}
  ]}), 0);
});
