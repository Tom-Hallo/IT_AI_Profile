import assert from 'node:assert/strict';
import test from 'node:test';
import { submittedEvidenceLinks } from '../src/pixel-studio/roadmap-evidence.js';
import { liveRoadmap } from '../src/pixel-studio/live-views.js';

const link = id => `https://github.com/team/project/pull/${id}`;
const submission = (id, verified = false, note = '') => ({
  url: link(id), note, verified,
  verification_status: verified ? 'verified' : 'self_reported'
});

function roadmapData(evidence, scoreReferences = [], status = 'in_progress') {
  const milestone = {
    id: 7, external_key: 'ci/cd', title: 'ci/cd',
    status, version: 1, verification_status: 'self_reported', evidence
  };
  return {
    goal: 'devops', milestone: 7, history: [], reevaluation: null,
    errors: {}, messages: {}, busy: new Set(),
    roadmaps: [],
    road: { id: 99, goal: 'devops', milestones: [{
      skill: 'ci/cd', objective: 'Implement CI', metric:
        'Reach verified ci/cd assessment >= 75/100 with at least one accessible evidence reference',
      evidence: scoreReferences
    }] },
    tracking: { milestones: [milestone], suggestions: [] }
  };
}

function yellowProof(html) {
  return html.split('<div class="milestone-proof">')[1]
    .split('<div class="milestone-evidence-block">')[0];
}

test('no evidence means no submitted-link checkmarks, even with scored references', () => {
  const scored = [{evidence_id:'verification-commit:abc',file_path:'ci.yaml'}];
  const html = liveRoadmap(roadmapData([],scored));
  assert.match(yellowProof(html), /Đã nộp 0 liên kết/);
  assert.match(yellowProof(html), /Chưa có liên kết bằng chứng/);
  assert.doesNotMatch(yellowProof(html), /class="milestone-proof-link /);
  assert.match(html, /Tham chiếu phân tích năng lực/);
  assert.match(html, /75\/100/); // Skill thresholds stay intact.
});

test('six unique links create exactly six ticks; verification stays separate', () => {
  const records = [
    submission(1,true),submission(2,false),submission(3,true),
    submission(4,false),submission(5,true),submission(6,true)
  ];
  const data = roadmapData(records);
  const html = liveRoadmap(data);
  const proof = yellowProof(html);
  assert.equal((proof.match(/class="milestone-proof-link /g) ?? []).length,6);
  assert.equal((proof.match(/is-verified"/g) ?? []).length,4);
  assert.equal((proof.match(/is-self-reported"/g) ?? []).length,2);
  assert.match(proof, /Đã nộp 6 liên kết/);
  assert.match(proof, /4 đã xác minh/);
  assert.equal(data.tracking.milestones[0].status,'in_progress');
  assert.equal(data.tracking.milestones[0].evidence.length,6);
});

test('duplicates count once, and an explicit verified record takes precedence', () => {
  const a = submission(11,false);
  const b = submission(11,true);
  const records = Object.freeze([Object.freeze(a),Object.freeze(b)]);
  const result = submittedEvidenceLinks(records);
  assert.equal(result.length,1);
  assert.equal(result[0].verified,true);
  assert.equal(records[0].verified,false);
  assert.equal((yellowProof(liveRoadmap(roadmapData(records)))
    .match(/class="milestone-proof-link /g) ?? []).length,1);
});

test('legacy evidence_url and strings display as submitted but never automatically verified', () => {
  const result = submittedEvidenceLinks([
    'https://github.com/team/project/issues/4',
    { evidence_url: link(3), verification_status: 'verified' },
    { url: link(5), verified: true, verification_status: 'self_reported' }
  ]);
  assert.equal(result.length,3);
  assert.equal(result.filter(e => e.verified).length,0);
});

test('invalid URLs and scoring-only references never inflate the count', () => {
  const result = submittedEvidenceLinks([
    {evidence_id:99,commit_sha:'a'.repeat(40)}, '', null,
    {url:'javascript:alert(1)'}, {url:'not a URL'},
    {url:'https://github.com/team/project/pull/18', verified:true}
  ]);
  assert.equal(result.length,1);
  assert.equal(result[0].verified,false);
});

test('many links remain in the DOM instead of being silently truncated', () => {
  const records = Array.from({length:25}, (_,i) => submission(i+1));
  const proof = yellowProof(liveRoadmap(roadmapData(records,'', 'completed')));
  assert.equal((proof.match(/class="milestone-proof-link /g) ?? []).length,25);
  assert.match(proof,/Đã nộp 25 liên kết/);
  assert.doesNotMatch(proof,/Đã nộp 0 liên kết/);
});
