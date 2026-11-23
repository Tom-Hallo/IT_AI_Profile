import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {mentor} from '../src/pixel-studio/mentor-view.js';

function renderProposal(overrides = {}) {
  const message = {
    type:'agent', id:17, parts:[], used:[],
    action:{tool:'update_roadmap',impact:'Add a verified SQL milestone',proposal:{title:'SQL'}},
    ...overrides
  };
  const runtime = {
    messages:[message], chosen:new Set(), chatPending:false,
    chatSnippet:null, chatDraft:'', sourcesOpen:false
  };
  const html = mentor(runtime,{icon:'bot',label:'Roadmap',metric:null},false,null);
  return {html,message};
}

test('pending Mentor proposal exposes the popup trigger at the top-right toolbar', () => {
  const {html,message} = renderProposal();
  assert.match(html, /<div class="chat-action-toolbar">[\s\S]*?data-act="agent-preview"[^>]*data-id="17"/);
  assert.ok(html.indexOf('data-act="agent-preview"') < html.indexOf('class="chat-action-impact"'));
  assert.match(html, /data-act="agent-decline"[^>]*data-id="17"/);
  assert.equal(message.actionDismissed, undefined);
});

test('declined proposal keeps status and a visible reconsider action, without reopening automatically', () => {
  const {html,message} = renderProposal({actionDismissed:true});
  assert.match(html, /class="chat-action-card dismissed"/);
  assert.match(html, /Đã từ chối đề xuất/);
  assert.match(html, /class="button secondary small chat-action-reopen"[^>]*data-act="agent-reconsider"[^>]*data-id="17"/);
  assert.doesNotMatch(html, /data-act="agent-preview"/);
  assert.equal(message.actionDismissed, true);
});

test('applied proposal does not show preview or reconsider controls', () => {
  const {html} = renderProposal({actionApplied:true});
  assert.doesNotMatch(html, /data-act="agent-preview"|data-act="agent-reconsider"/);
});

test('proposal animation respects the existing reduced-motion preference', () => {
  const css = readFileSync(new URL('../public/pixel-studio/styles.css',import.meta.url),'utf8');
  assert.match(css, /animation:chat-action-control-in 340ms/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)\{[\s\S]*?animation:none!important/);
});
