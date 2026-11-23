/**
 * Evidence submitted for a roadmap milestone is distinct from assessment
 * references stored on careerRoadmap.milestones[].evidence.
 *
 * One checkmark in "What to produce" represents one distinct, clickable,
 * submitted URL. Verification remains an independent, explicit backend flag.
 * This function only prepares UI data; it never changes saved milestones.
 */
export function submittedEvidenceLinks(entries) {
  if (!Array.isArray(entries)) return [];

  const links = new Map();
  for (const entry of entries) {
    const raw = typeof entry === 'string'
      ? entry
      : entry && typeof entry === 'object' ? (entry.url ?? entry.evidence_url) : '';
    if (typeof raw !== 'string' || !raw.trim()) continue;

    let url;
    try {
      const parsed = new URL(raw.trim());
      if (!['https:', 'http:'].includes(parsed.protocol) || !parsed.hostname) continue;
      url = parsed.href;
    } catch {
      continue;
    }

    // A submitted link is *only* verified if the backend explicitly says so.
    const verified = typeof entry === 'object' && entry !== null
      && entry.verified === true && entry.verification_status === 'verified';
    const note = typeof entry === 'object' && entry !== null
      && typeof entry.note === 'string' ? entry.note : '';
    const previous = links.get(url);
    if (!previous) {
      links.set(url, { url, note, verified });
    } else {
      // Duplicate submissions count as one link, but retain verification.
      previous.verified ||= verified;
      if (!previous.note && note) previous.note = note;
    }
  }

  return [...links.values()];
}
