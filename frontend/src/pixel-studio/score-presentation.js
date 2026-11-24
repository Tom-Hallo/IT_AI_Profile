/** Keep missing evidence distinct from an actual zero proficiency score. */
export function verifiedSkillScore(score, status) {
  return status === 'Scored' && typeof score === 'number' && Number.isFinite(score) ? score : null;
}

export function numericScore(score) {
  return typeof score === 'number' && Number.isFinite(score) ? score : null;
}

/**
 * Dashboard labels a skill score as personally verified only when its stored
 * scoring breakdown cites real PBI-013 verification event IDs. Manifest/source
 * detections without such links remain visible in the report, but not as a
 * verified proficiency rating on the profile.
 */
export function reportBackedSkillScore(item) {
  const value = verifiedSkillScore(item?.score, item?.status);
  if (value === null || value < 0 || value > 100) return null;
  const linked = item.breakdown?.some(part =>
    part.evidence_kind === 'verification' &&
    Array.isArray(part.evidence_ids) &&
    part.evidence_ids.some(id => Number.isSafeInteger(id) && id > 0)
  );
  return linked ? value : null;
}

/** CV insertion must use the same provenance checks as the Dashboard. */
export function verifiedCVSkills(items = []) {
  return (Array.isArray(items) ? items : []).filter(item =>
    reportBackedSkillScore(item) !== null &&
    Number.isSafeInteger(item.report_id) && item.report_id > 0 &&
    Number.isSafeInteger(item.repo?.id) && item.repo.id > 0 &&
    Boolean(item.repo.full_name || item.repo.name) &&
    typeof item.technology === 'string' && item.technology.length > 0
  );
}

export function cvSkillKey(item) {
  return JSON.stringify([item.repo.id,item.report_id,item.kind,item.technology]);
}

/** Role totals are valid only when the backend explicitly marks them as scored. */
export function verifiedRoleScore(item) {
  const value = numericScore(item?.role_score);
  return item?.status === 'SCORED' && value !== null && value >= 0 && value <= 100 ? value : null;
}

/** Missing historical diagnostics are unknown, never an observed zero. */
export function skillEvidenceSummary(item) {
  const d = item?.diagnostics;
  const count = key => Number.isSafeInteger(d?.[key]) && d[key] >= 0 ? d[key] : null;
  const part = item?.breakdown?.find(p => p.criterion === 'confidence'
    && p.evidence_kind === 'verification' && p.evidence_ids?.some(id => Number.isSafeInteger(id) && id > 0));
  const value = part?.normalized_value;
  return {
    available: Boolean(d && !d.snapshot_missing && Array.isArray(d.missing_metrics)),
    snapshotMissing: d?.snapshot_missing === true,
    missing: Array.isArray(d?.missing_metrics) ? d.missing_metrics.filter(key => typeof key === 'string') : [],
    confidence: Number.isFinite(value) && value >= 0 && value <= 1 ? Math.round(value * 10000) / 100 : null,
    matchedCommits: count('matched_commits'),
    matchedPRs: count('matched_prs'),
    matchedFiles: count('matched_files'),
    usedEvents: count('used_events'),
    usedFiles: count('used_files'),
    sourceFiles: count('framework_source_files'),
    eligiblePRFiles: count('eligible_pr_files'),
    completedPRFiles: count('completed_pr_files'),
    collectionIncomplete: d?.collection_complete === false,
    filesPartial: d?.file_collection_partial === true,
  };
}
