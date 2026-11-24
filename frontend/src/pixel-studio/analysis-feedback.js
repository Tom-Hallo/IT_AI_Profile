import {escape} from './ui.js';

/** Render only confirmed terminal outcomes; never use success styling for failures. */
export function renderAnalysisFeedback(outcome, language = 'vi') {
  if (!outcome) return '';
  const copy = (vi, en) => language === 'en' ? en : vi;
  const {status, errorCode, repoName} = outcome;
  if (['queued', 'running', 'cancel_requested'].includes(status)) return '';

  let css = 'notice red notice-error';
  let role = 'alert';
  let icon = '⚠';
  let message;

  if (status === 'succeeded') {
    css = 'notice green notice-success';
    role = 'status';
    icon = '✓';
    message = copy('Đã phân tích', 'Analyzed') + (repoName ? ' ' + repoName : '') + '.';
  } else if (status === 'cancelled') {
    css = 'notice amber';
    role = 'status';
    icon = 'ℹ';
    message = copy('Đã hủy phân tích.', 'Analysis cancelled.');
  } else if (errorCode === 'GitHubTokenRevokedError') {
    message = copy(
      'Phân tích GitHub thất bại. Quyền truy cập GitHub không còn hợp lệ. Vui lòng kết nối lại GitHub rồi thử lại.',
      'GitHub analysis failed. GitHub access is no longer valid. Reconnect GitHub and try again.'
    );
  } else {
    message = copy('Phân tích thất bại', 'Analysis failed') + (errorCode ? ' · ' + errorCode : '') + '.';
  }

  return '<div class="' + css + '" role="' + role + '"><span class="notice-icon" aria-hidden="true">'
    + icon + '</span> <span>' + escape(message) + '</span></div>';
}
