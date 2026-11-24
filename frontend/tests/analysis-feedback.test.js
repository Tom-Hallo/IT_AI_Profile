import assert from 'node:assert/strict';
import test from 'node:test';
import {renderAnalysisFeedback} from '../src/pixel-studio/analysis-feedback.js';

test('failed GitHub analysis uses an error alert and actionable reconnect guidance', () => {
  const outcome = {status:'failed',errorCode:'GitHubTokenRevokedError'};
  const vi = renderAnalysisFeedback(outcome);
  assert.match(vi,/notice red notice-error/);
  assert.match(vi,/role="alert"/);
  assert.match(vi,/kết nối lại GitHub/);
  assert.doesNotMatch(vi,/notice-success|notice green|✓|GitHubTokenRevokedError/);
  assert.match(renderAnalysisFeedback(outcome,'en'),/Reconnect GitHub/);
});

test('other failures remain red and technical error text is escaped', () => {
  const html = renderAnalysisFeedback({status:'failed',errorCode:'<script>'});
  assert.match(html,/notice-error/);
  assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<script>|notice-success|✓/);
});

test('success alone has a green check, and repository names are escaped', () => {
  const html = renderAnalysisFeedback({status:'succeeded',repoName:'owner/<repo>'});
  assert.match(html,/notice green notice-success/);
  assert.match(html,/role="status"/);
  assert.match(html,/✓/);
  assert.match(html,/owner\/&lt;repo&gt;/);
});

test('cancellation is not a success or failure and active jobs show no terminal notice', () => {
  const html = renderAnalysisFeedback({status:'cancelled'});
  assert.match(html,/notice amber/);
  assert.match(html,/Đã hủy phân tích/);
  assert.doesNotMatch(html,/notice-success|notice-error|✓/);
  for (const status of ['queued','running','cancel_requested']) {
    assert.equal(renderAnalysisFeedback({status}),'');
  }
  assert.equal(renderAnalysisFeedback(null),'');
});
