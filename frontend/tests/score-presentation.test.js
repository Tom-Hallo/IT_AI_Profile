import assert from 'node:assert/strict';
import test from 'node:test';
import {numericScore, reportBackedSkillScore, verifiedSkillScore, verifiedRoleScore, skillEvidenceSummary} from '../src/pixel-studio/score-presentation.js';
import {verifiedCVSkills,cvSkillKey} from '../src/pixel-studio/score-presentation.js';

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


test('CV only inserts report-backed personally verified skills', () => {
  const good = {status:'Scored',score:75,kind:'language',technology:'Python',
    report_id:4,repo:{id:7,full_name:'owner/repo'},
    breakdown:[{evidence_kind:'verification',evidence_ids:[11]}]};
  const other = {...good,repo:{id:8,full_name:'owner/other'}};
  assert.deepEqual(verifiedCVSkills([good,other,{...good,report_id:null},
    {...good,status:'Insufficient'}, {...good,breakdown:[{evidence_kind:'manifest',evidence_ids:[11]}]}]),[good,other]);
  assert.notEqual(cvSkillKey(good),cvSkillKey(other));
  assert.deepEqual(verifiedCVSkills(null),[]);
});


test('role totals require a scored status and preserve a genuine zero', () => {
  assert.equal(verifiedRoleScore({status:'SCORED',role_score:0}),0);
  assert.equal(verifiedRoleScore({status:'SCORED',role_score:75}),75);
  assert.equal(verifiedRoleScore({status:'INSUFFICIENT',role_score:75}),null);
  assert.equal(verifiedRoleScore({status:'SCORED',role_score:null}),null);
  assert.equal(verifiedRoleScore({status:'SCORED',role_score:101}),null);
  assert.equal(verifiedRoleScore(null),null);
});


test('skill evidence diagnostics keep missing data distinct from observed zero', () => {
  const old = skillEvidenceSummary({status:'Insufficient',breakdown:[]});
  assert.equal(old.available,false);
  assert.equal(old.matchedFiles,null);
  assert.equal(old.confidence,null);
  const fresh = skillEvidenceSummary({diagnostics:{
    missing_metrics:['pr_contribution'],matched_commits:2,matched_prs:0,
    matched_files:1,used_events:0,used_files:0,file_collection_partial:true
  }});
  assert.equal(fresh.available,true);
  assert.equal(fresh.matchedPRs,0);
  assert.equal(fresh.usedEvents,0);
  assert.deepEqual(fresh.missing,['pr_contribution']);
  assert.equal(fresh.filesPartial,true);
});

test('confidence needs real verification links and preserves fractional percentages', () => {
  const part = {criterion:'confidence',normalized_value:.3125,evidence_kind:'verification',evidence_ids:[7]};
  assert.equal(skillEvidenceSummary({breakdown:[part]}).confidence,31.25);
  assert.equal(skillEvidenceSummary({breakdown:[{...part,evidence_ids:[]}]}).confidence,null);
  assert.equal(skillEvidenceSummary({diagnostics:{snapshot_missing:true}}).snapshotMissing,true);
});
