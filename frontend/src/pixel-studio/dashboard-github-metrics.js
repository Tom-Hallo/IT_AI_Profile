export const RADAR_KEYS = ['code', 'architecture', 'testing', 'collaboration', 'ci'];
export const RADAR_RUBRIC_VERSION = 'github-evidence-coverage-v1';

const rubric = {
  code:['source_change','framework_source'],
  architecture:['service_design','data_design','structure_design'],
  testing:['test_change','test_config'],
  collaboration:['authored_pr','merged_pr','peer_review'],
  ci:['workflow_change','completed_check']
};

const validEvidence = ref => ref &&
  Number.isSafeInteger(ref.evidence_id) && ref.evidence_id > 0 &&
  Number.isSafeInteger(ref.repository_id) && ref.repository_id > 0 &&
  Number.isSafeInteger(ref.report_id) && ref.report_id > 0 &&
  ['verification','collaboration'].includes(ref.kind);

/** Union of distinct observed rubric criteria, not averages or event counts. */
export function githubRadarMetrics(reports = []) {
  const compatible = reports.filter(report => report?.rubric_version === RADAR_RUBRIC_VERSION);
  return RADAR_KEYS.map(key => {
    const criteria = rubric[key].map(criterion => {
      let evidence = null;
      for (const report of compatible) {
        const axis = report.axes?.find(item => item.key === key);
        const ref = axis?.criteria?.find(item => item.key === criterion)?.evidence;
        if (validEvidence(ref)) {
          evidence = ref;
          break;
        }
      }
      return {key:criterion,evidence};
    });
    const observed = criteria.filter(item => item.evidence).length;
    return {key,criteria,observed,total:criteria.length,
      score:observed ? Math.round(observed * 100 / criteria.length) : null};
  });
}
