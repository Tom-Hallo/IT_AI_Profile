import assert from 'node:assert/strict';
import test from 'node:test';
import {isGitHubCommitOrPrUrl} from '../src/pixel-studio/evidence-url.js';

const sha = 'a'.repeat(40);
test('accepts direct GitHub PR and commit evidence URLs', () => {
  assert.equal(isGitHubCommitOrPrUrl('https://github.com/Tom-Hallo/IT_AI_Profile/pull/98'), true);
  assert.equal(isGitHubCommitOrPrUrl('https://github.com/Tom-Hallo/IT_AI_Profile/commit/' + sha), true);
});
test('rejects issues, lookalike hosts, repository pages and malformed identifiers', () => {
  for (const url of [
    'https://github.com/Tom-Hallo/IT_AI_Profile/issues/1',
    'https://github.com.attacker.com/repo/commit/12345',
    'https://github.com/Tom-Hallo/IT_AI_Profile',
    'https://github.com/Tom-Hallo/IT_AI_Profile/pull/0',
    'https://github.com/Tom-Hallo/IT_AI_Profile/commit/12345',
    'http://github.com/Tom-Hallo/IT_AI_Profile/pull/98',
    'https://github.com/Tom-Hallo/IT_AI_Profile/pull/98?x=1',
    'https://github.com/Tom-Hallo/IT_AI_Profile/pull/98/files',
    'https://github.com@attacker.com/Tom-Hallo/IT_AI_Profile/pull/98',
    'https://gitlab.com/Tom-Hallo/IT_AI_Profile/pull/98',
    'https://github.com/a//b/pull/12',
    'https://github.com:443/a/b/pull/12',
    'https://github.com/a/x/../b/pull/12',
    'https://github.com/a/b/PULL/12',
    '',
  ]) {
    assert.equal(isGitHubCommitOrPrUrl(url), false, url);
  }
});
