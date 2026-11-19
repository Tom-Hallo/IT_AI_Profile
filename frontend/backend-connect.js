const API = '/api/v1';
async function request(path, options = {}) {
  const response = await fetch(API + path, {
    ...options, credentials: 'include',
    headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  });
  if (!response.ok) {
    const error = new Error(`Backend API ${response.status} on ${path}`);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}
export const backend = {
  authenticated: false,
  me: () => request('/auth/me'),
  repositories: () => request('/github/repositories?page=1&per_page=100'),
  logout: () => request('/auth/logout', {method: 'POST'}),
};
export function normalizeRepo(repo) {
  const languages = Object.entries(repo.languages || {}).sort((a,b)=>b[1]-a[1]);
  return {
    id: String(repo.id), backendId: repo.id, name: repo.full_name || repo.name,
    visibility: repo.private ? 'private' : 'public', days: 0,
    tech: repo.primary_language || 'Chưa xác định',
    stack: languages.map(([name])=>name), score: null, confidence: null,
    radar: {code:0,architecture:0,testing:0,collaboration:0,ci:0},
    file: '', startLine: 0, commit: '', pull: 0,
    code: [], languages, structure: [], fork: repo.is_fork,
  };
}
