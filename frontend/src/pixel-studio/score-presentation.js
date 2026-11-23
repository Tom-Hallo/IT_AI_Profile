/** Keep missing evidence distinct from an actual zero proficiency score. */
export function verifiedSkillScore(score, status) {
  return status === 'Scored' && typeof score === 'number' && Number.isFinite(score) ? score : null;
}

export function numericScore(score) {
  return typeof score === 'number' && Number.isFinite(score) ? score : null;
}
