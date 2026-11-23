// Fast feedback for the roadmap evidence form; backend remains authoritative.
const commitPattern = /^[a-fA-F0-9]{40}$/;
const pullPattern = /^[1-9][0-9]*$/;
const slugPattern = /^[A-Za-z0-9_.-]+$/;
const ownerPattern = /^[A-Za-z0-9][A-Za-z0-9-]{0,38}$/;

export function isGitHubCommitOrPrUrl(raw) {
  if (typeof raw !== 'string' || /[?#]/.test(raw)) return false;
  try {
    const url = new URL(raw.trim());
    if (url.protocol !== 'https:' || url.host.toLowerCase() !== 'github.com'
      || url.username || url.password || url.search || url.hash) return false;
    const parts = url.pathname.split('/').filter(Boolean);
    if (parts.length !== 4) return false;
    const [owner, repo, kind, id] = parts;
    if (!ownerPattern.test(owner) || !slugPattern.test(repo) || repo === '.' || repo === '..') return false;
    return (kind === 'commit' && commitPattern.test(id))
      || (kind === 'pull' && pullPattern.test(id));
  } catch {
    return false;
  }
}
