import assert from 'node:assert/strict';
import test from 'node:test';
import {numericScore, verifiedSkillScore} from '../src/pixel-studio/score-presentation.js';

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
