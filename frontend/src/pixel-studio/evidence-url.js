// Match the backend raw URL grammar before browser URL normalization.
const evidencePattern = /^https:\/\/github\.com\/([A-Za-z0-9][A-Za-z0-9-]{0,38})\/([A-Za-z0-9_.-]+)\/(commit|pull)\/([A-Za-z0-9]+)\/?$/i;

export function isGitHubCommitOrPrUrl(raw) {
  if (typeof raw !== 'string') return false;
  const match = evidencePattern.exec(raw.trim());
  if (!match || match[2] === '.' || match[2] === '..') return false;
  const [, , , kind, id] = match;
  return (kind === 'commit' && /^[a-fA-F0-9]{40}$/.test(id))
    || (kind === 'pull' && /^[1-9][0-9]*$/.test(id));
}
