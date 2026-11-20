const api = '/api/v1';

export class StudioApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export async function request(path, {method='GET',json,file,signal,timeout=15000}={}) {
  const deadline = AbortSignal.timeout(timeout);
  const headers = {};
  if (json !== undefined) headers['Content-Type'] = 'application/json';
  if (file) headers['Content-Type'] = /\.pdf$/i.test(file.name) ? 'application/pdf'
    : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  const response = await fetch(api + path, {
    method, headers, credentials:'same-origin', cache:'no-store',
    body:file ?? (json === undefined ? undefined : JSON.stringify(json)),
    signal:signal ? AbortSignal.any([signal,deadline]) : deadline
  });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => undefined);
  if (!response.ok) throw new StudioApiError(response.status,
    typeof payload?.detail === 'string' ? payload.detail : 'API HTTP ' + response.status);
  if (payload === undefined) throw new Error('Phản hồi API không hợp lệ.');
  return payload;
}

export const post = (path,json,timeout) => request(path,{method:'POST',json,timeout});
export const remove = path => request(path,{method:'DELETE'});
export const query = values => new URLSearchParams(Object.entries(values).filter(([,value]) => value !== null && value !== undefined && value !== '')).toString();

export function period(days) {
  const now = new Date();
  const start = new Date(now);
  start.setUTCDate(start.getUTCDate() - days + 1);
  return {start_date:start.toISOString().slice(0,10),end_date:now.toISOString().slice(0,10)};
}

export function parseSkills(value,level) {
  return [...new Set(value.split(/[,\n]/).map(skill => skill.trim()).filter(Boolean))]
    .map(skill_key => ({skill_key,level}));
}

export function safeLink(value) {
  try {
    const url = new URL(value);
    return ['https:','http:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

export const exportURL = (documentId,number,format) =>
  api + '/cv-studio/' + encodeURIComponent(documentId) + '/versions/' + Number(number) + '/export?' + query({format});
