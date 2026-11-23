/**
 * Dashboard radar data is read exclusively from authenticated GitHub scoring
 * responses. No sample data, file-count scoring, unverified detections or
 * fabricated 0/100 fallback are permitted in live mode.
 */
export const RADAR_KEYS = ['code', 'architecture', 'testing', 'collaboration', 'ci'];

const scored = (value, status) =>
  (status === 'SCORED' || status === 'Scored') &&
  typeof value === 'number' && Number.isFinite(value) &&
  value >= 0 && value <= 100;

const verifiedScore = item => scored(item?.score, item?.status);

const sourceCriterion = (criteria, predicate) =>
  criteria.find(item => predicate(item) && verifiedScore(item) &&
    Array.isArray(item.evidence_refs) &&
    item.evidence_refs.some(ref => ref.verified === true)) ?? null;

function chosenRole(roles, roleKey) {
  const requested = roles.find(item => item.key === roleKey);
  return requested?.score ? requested : roles.find(item => item.score) ?? null;
}

function scoreFromCriterion(item, role) {
  return {
    score: item.score,
    origin: 'role',
    source: item.name || item.key,
    repository_id: item.evidence_refs?.find(ref => ref.verified)?.repository_id ?? null,
    detail: item.rationale || '',
    role_name: role?.name || role?.score?.role_name || ''
  };
}

function scoreFromLanguage(scores) {
  // A scored language must have actual linked verification event IDs.
  // Identifying a language by its file extension alone is not proof of skill.
  const eligible = scores.filter(item =>
    item.kind === 'language' &&
    verifiedScore(item) &&
    item.breakdown?.some(part => Array.isArray(part.evidence_ids) &&
      part.evidence_ids.some(id => Number.isSafeInteger(id) && id > 0))
  );
  const row = eligible.sort((a, b) => b.score - a.score ||
    String(a.technology).localeCompare(String(b.technology)))[0];
  return row ? {
    score: row.score,
    origin: 'skill',
    source: row.technology,
    repository_id: row.repo?.id ?? null,
    detail: row.explanation || '',
    role_name: ''
  } : null;
}

/**
 * The five axes are visual categories, not a newly invented rubric.
 * Every displayed number is an existing persisted skill score or an already
 * scored role criterion, traceable to the named source. Unscored axes stay null.
 */
export function githubRadarMetrics({roles = [], scores = [], roleKey = null} = {}) {
  const role = chosenRole(roles, roleKey);
  const criteria = Array.isArray(role?.score?.criteria) ? role.score.criteria : [];
  const byKey = predicate => {
    const item = sourceCriterion(criteria, predicate);
    return item ? scoreFromCriterion(item, role) : null;
  };
  const language = byKey(item =>
    item.type === 'SKILL' && /(^|_)language($|_)/.test(item.key || '')
  ) || scoreFromLanguage(scores);
  const architecture = byKey(item => item.type === 'ARCHITECTURE');
  const testing = byKey(item => /(^|_)(testing|test|tests)($|_)/.test(item.key || ''));
  const collaboration = byKey(item =>
    /(^|_)(collaboration|review|reviews)($|_)/.test(item.key || '')
  );
  const ci = byKey(item => /(^|_)(ci|cd|pipeline|pipelines)($|_)/.test(item.key || ''));
  const derived = {code: language, architecture, testing, collaboration, ci};
  return RADAR_KEYS.map(key => ({key, score: derived[key]?.score ?? null,
    evidence: derived[key] || null}));
}
