import assert from 'node:assert/strict';
import test from 'node:test';
import {liveRoadmap} from '../src/pixel-studio/live-views.js';
import {setLanguage} from '../src/pixel-studio/i18n.js';

function data(overrides={}) {
  return {
    road:{id:1,goal:'backend',milestones:[{skill:'python',objective:'Python',metric:'Practice',evidence:[]},{skill:'docker'},{skill:'fastapi'}]},
    roadmaps:[{id:1,goal:'backend',title:'Backend Career Roadmap'}],
    tracking:{milestones:[
      {id:11,title:'Python',external_key:'python',status:'completed',verification_status:'pending',evidence:[]},
      {id:12,title:'Docker',external_key:'docker',status:'in_progress'},
      {id:13,title:'FastAPI',external_key:'fastapi',status:'pending'}
    ],suggestions:[]},
    goal:'backend',milestone:11,history:[],historyLoaded:true,
    busy:new Set(),messages:{},errors:{},...overrides
  };
}

test('three distinct skill map states and manual completion label', () => {
  setLanguage('vi');
  const html = liveRoadmap(data());
  assert.match(html,/class="node"[^>]*data-state="done"/);
  assert.match(html,/class="node"[^>]*data-state="in-progress"/);
  assert.match(html,/class="node"[^>]*data-state="ready"/);
  assert.match(html,/Chưa xác minh năng lực/);
  assert.match(html,/Chưa có hoạt động nào được ghi nhận/);
});

test('only the clicked action shows loading while other mutation buttons are disabled', () => {
  const html = liveRoadmap(data({busy:new Set(['road']),roadAction:'reevaluate'}));
  assert.match(html,/class="button secondary small is-loading"[^>]*data-act="road-draft"[^>]*aria-busy="true"/);
  assert.doesNotMatch(html,/class="button primary is-loading"[^>]*data-act="road-create"/);
  assert.equal((html.match(/is-loading/g)||[]).length,1);
});

test('resolved and stale evaluation outcomes are distinct', () => {
  const input = data({reevaluation:{kind:'suggestions',snapshotId:'s',verifiedSkills:1}});
  assert.match(liveRoadmap(input),/Đã xử lý tất cả đề xuất/);
  input.tracking.suggestions = [{id:7,state:'stale',snapshot_id:'s',milestone_id:11}];
  assert.match(liveRoadmap(input),/Kết quả đánh giá đã cũ/);
});

test('submitted evidence appears once and the save notice provides a next action', () => {
  const input = data({roadNotice:{title:'Đã lưu minh chứng tự khai báo.',detail:'Chưa đủ bằng chứng.',verified:false}});
  const url = 'https://github.com/owner/repo/pull/12';
  input.tracking.milestones[0].evidence = [{source:'submission',url,verified:false,verification_status:'self_reported'}];
  input.road.milestones[0].evidence = input.tracking.milestones[0].evidence;
  const html = liveRoadmap(input);
  assert.equal((html.match(/href="https:\/\/github\.com\/owner\/repo\/pull\/12"/g)||[]).length,1);
  assert.match(html,/Đến phân tích GitHub/);
  assert.doesNotMatch(html,/milestone-analysis-refs/);
});

test('English language and failed evidence draft are retained', () => {
  setLanguage('en');
  try {
    const html = liveRoadmap(data({roadEvidenceDraft:{roadId:1,milestoneId:11,url:'https://github.com/owner/repo/pull/12',note:'My notes'}}));
    assert.match(html,/Skill not verified/);
    assert.match(html,/No activity has been recorded/);
    assert.match(html,/value="My notes"/);
  } finally { setLanguage('vi'); }
});
