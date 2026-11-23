import assert from 'node:assert/strict';
import test from 'node:test';

import { liveDashboard, liveData, liveStatus } from '../src/pixel-studio/live-views.js';
import { radarView } from '../src/pixel-studio/radar.js';

const repository = {id:1,full_name:'owner/repository',name:'repository'};

function fixture() {
  const roleScore = {
    status:'INSUFFICIENT',role_score:null,coverage:null,criteria:[
      {key:'backend_language',name:'Backend language',status:'INSUFFICIENT',score:null},
      {key:'architecture',name:'Architecture',status:'UNKNOWN',score:null}
    ],rationale:'There is not enough verified evidence.',limitations:[]
  };
  return {
    state:{scope:'public',range:90,repo:1,access:'public'},
    runtime:{scoreTab:'tech',scoreKey:null,roleKey:'backend'},
    data:{
      user:{full_name:'Test user'},repos:[repository],
      scores:[{repo:repository,technology:'Vite',kind:'framework',status:'Insufficient',score:null,breakdown:[],explanation:'Not verified'}],
      roles:[{key:'backend',name:'Backend',score:roleScore}],
      skills:[],repoData:{1:{report:{id:1}}},tracking:{milestones:[]},road:null,
      busy:new Set(),messages:{},errors:{},health:null,sync:null,
      shares:[],audit:[],shared:null
    }
  };
}

test('unverified technologies are not presented as verified or assigned a zero/100 score', () => {
  const {state,runtime,data} = fixture();
  const html = liveDashboard(state,runtime,data);
  assert.match(html,/Chưa đủ bằng chứng/);
  assert.doesNotMatch(html,/Đủ bằng chứng xác minh/);
  assert.doesNotMatch(html,/evidence-score-pill">0<span>\/100/);
  assert.match(html,/evidence-score-pill">—/);
  assert.match(html,/radar-empty/);
  assert.doesNotMatch(html,/90\/100/);
});

test('only scored criteria appear on the radar; missing dimensions remain unknown', () => {
  const {state,runtime,data} = fixture();
  data.roles[0].score.criteria[1] = {key:'architecture',name:'Architecture',status:'SCORED',score:68};
  const html = liveDashboard(state,runtime,data);
  assert.match(html,/data-score="68"/);
  assert.match(html,/data-score=""/);
  assert.doesNotMatch(html,/data-score="100"/);
  assert.doesNotMatch(html,/data-previous="68"/);
});

test('real zero score remains valid when the backend status is scored', () => {
  const {state,runtime,data} = fixture();
  data.scores[0] = {...data.scores[0],status:'Scored',score:0};
  const html = liveDashboard(state,runtime,data);
  assert.match(html,/Đã chấm điểm/);
  assert.match(html,/evidence-score-pill">0<span>\/100/);
  assert.doesNotMatch(html,/evidence-score-pill">—/);
});

test('role scoring does not present an insufficient result as a green score', () => {
  const {state,runtime,data} = fixture();
  runtime.scoreTab = 'roles';
  data.roles[0].score.role_score = 100;
  const html = liveDashboard(state,runtime,data);
  assert.match(html,/Chưa đủ bằng chứng/);
  assert.doesNotMatch(html,/evidence-score-pill">100<span>\/100/);
});

test('radar empty and partial states are distinguishable', () => {
  const blank = [
    {key:'code',label:'Code',score:null},
    {key:'architecture',label:'Architecture',score:null}
  ];
  assert.match(radarView(blank,1,'Public','90 days',{}),/radar-empty/);
  const partial = [{...blank[0],score:71},blank[1]];
  const html = radarView(partial,1,'Public','90 days',{});
  assert.match(html,/<canvas/);
  assert.match(html,/data-score="71"/);
  assert.match(html,/data-score=""/);
  assert.doesNotMatch(html,/data-score="null"/);
});

test('live system status and data permission screens do not say sample environment', () => {
  const {state,data} = fixture();
  data.health = {status:'ok',httpStatus:200,checks:{database:'ok',redis:'ok'}};
  const status = liveStatus(data);
  const privacy = liveData(state,data);
  assert.match(status,/Trạng thái dịch vụ/);
  assert.doesNotMatch(status,/Môi trường mẫu/);
  assert.match(privacy,/Kết nối GitHub/);
  assert.doesNotMatch(privacy,/GitHub mẫu/);
});
