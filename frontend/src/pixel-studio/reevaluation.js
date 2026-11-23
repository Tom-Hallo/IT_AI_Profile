/**
 * Summarize the stored GitHub analysis re-evaluation without inventing skill
 * verification or exposing old snapshot suggestions as new results.
 */
export function summarizeReevaluation(result, tracking) {
  const snapshotId = typeof result?.snapshot_id === 'string' ? result.snapshot_id : '';
  if (!snapshotId) throw new Error('Roadmap evaluation returned no snapshot ID');

  const pending = (Array.isArray(tracking?.suggestions) ? tracking.suggestions : [])
    .filter(item => item.state === 'pending' && item.snapshot_id === snapshotId);
  const verifiedSkills = Math.max(0, Number(result.evaluation?.verified_skill_count) || 0);
  const checkedMilestones = Math.max(0, Number(result.evaluation?.checked_milestones) || 0);

  return {
    snapshotId,
    pendingCount: pending.length,
    verifiedSkills,
    checkedMilestones,
    kind: pending.length ? 'suggestions'
      : checkedMilestones === 0 ? 'all-completed'
      : verifiedSkills === 0 ? 'no-verified-evidence' : 'no-eligible-milestone'
  };
}

export function currentEvaluationSuggestions(evaluation, tracking) {
  if (!evaluation?.snapshotId) return [];
  return (Array.isArray(tracking?.suggestions) ? tracking.suggestions : [])
    .filter(item => item.state === 'pending' && item.snapshot_id === evaluation.snapshotId);
}
