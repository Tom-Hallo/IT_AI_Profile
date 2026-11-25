# E2E evidence validation

Use a test GitHub account/repository and a separate test dataset. Record repository ID, current user ID, job UUID, report ID, report SHA, analysis window and rubric version. No fabricated score or database writes.

1. Create actual non-merge source commits and an authored PR with source changes, tests and a CI run. Include a dependency-only framework and a source-linked framework. Record GitHub URLs/SHAs, author and changed files. Do not manufacture attribution.
2. Log in, sync, select repository, start full analysis with explicit date range. Observe `POST /api/v1/analysis/jobs` (202), `GET /api/v1/analysis/jobs/{job_id}`, and /events until succeeded; failed/canceled/queued are not successful results.
3. Read `GET /api/v1/repositories/{repository_id}/analysis?report_id=...` and `/analysis/evidence?report_id=...`; verify SHA, detected languages/frameworks and file paths. Static detection != verified proficiency.
4. Read `/repositories/{repository_id}/verification` then `/verification/evidence?verification_id=...&verification_status=verified`; verify report association, author, PR/commit identity, merge/bot/inherited flags, coverage and pagination. Do not assume latest verification matches report; compare IDs. Source-change evidence and per-rubric eligibility must be checked separately.
5. Read `/scoring/repositories/{repository_id}/skills?report_id=...`; compare IDs, status, score, breakdown/evidence links, rubric version. A language requires all five weighted metrics; frameworks require four and verified PR OR non-merge commit tied to framework source. Missing metric is Insufficient, null, not 0. Numeric zero is allowed only where evidence supports zero. Stored score is integer, check actual persistence rounding before comparing fractional engine output.
6. Read `/repositories/{repository_id}/analysis/dashboard-report` then `/analysis/dashboard-radar?report_id=...` with same window. Inspect browser Network and UI. Radar coverage/verified counts/role score are distinct metrics; do not equate them. Ensure dates, public/private/combined scope, rounding and report IDs match. Check evidence click-through and no stale result after changing report/role.

## Edge cases

| ID | Fixture | Expected |
|---|---|---|
| EV01 | Authored non-merge source commit + authored PR | Traceable verified eligible evidence; numeric score only if all criteria observed |
| EV02 | Empty repo or README only | No fabricated skill score |
| EV03 | Dependency manifest only | Detected framework, not proficiency |
| EV04 | Fork inherited files / another author / bot / merge-only | Not attributed as user's source contribution |
| EV05 | One verified PR, no verified commit for a framework | May score if all four metrics are evidence-backed; no fabricated commit |
| EV06 | No tests/checks | Missing quality/check evidence explicit; no assumed test pass |
| EV07 | API rate limit / incomplete pages | Partial coverage disclosed; no fabricated complete coverage |
| EV08 | Duplicate PR/commit / retry | No double-count in same report |
| EV09 | Job queued/failed/canceled | No new successful snapshot presented |
| EV10 | New report for same SHA or new SHA | Dashboard binds to explicit report, does not mix old score/evidence |
| EV11 | Private repo without consent or another user's IDs | Access rejected; no private evidence in public UI |
| EV12 | Verified zero, max, missing or invalid metric | 0, 100, null, rejection respectively in engine fixtures |
| EV13 | UTC boundary, timezone, scope filters | Counts and selected snapshot consistent with filter |
| EV14 | Backend integer persistence vs decimal rubric output | Document rounding; all displays agree |

## Read-only SQL (replace example IDs before running)

```sql
SELECT id, repository_id, commit_sha, analyzed_at, scope, time_range, budget
FROM ita.analysis_reports WHERE id = 14 AND repository_id = 1;
SELECT id, report_id, user_id, verification_status, coverage_status,
       verified_commits_count, verified_prs_count
FROM ita.repository_verifications WHERE report_id = 14 AND user_id = 1;
SELECT ve.evidence_type, ve.target_identifier, ve.verification_status,
       ve.actor_login, ve.is_merge, ve.is_bot, ve.is_fork_inherited, ve.html_url
FROM ita.verification_evidence ve
JOIN ita.repository_verifications rv ON rv.id=ve.verification_id
WHERE rv.report_id=14 AND rv.user_id=1;
SELECT s.id, s.kind, s.technology, s.status, s.score, s.report_id,
       s.commit_sha, r.version, s.breakdown
FROM ita.skill_scores s JOIN ita.rubric_versions r ON r.id=s.rubric_id
WHERE s.report_id=14 AND s.user_id=1 AND s.repository_id=1;
SELECT s.technology, s.id AS score_id, e.id AS evidence_id, e.report_id,
       e.file_path, e.commit_sha, e.evidence_source
FROM ita.skill_scores s JOIN ita.score_evidence_links l ON l.score_id=s.id
JOIN ita.analysis_evidence e ON e.id=l.evidence_id
WHERE s.report_id=14 AND s.user_id=1;
```

Verify linked evidence provenance and expected snapshot; inspect mismatches rather than deleting or patching records. Capture GitHub URL, sanitized network response, SQL result, Dashboard screenshot and result PASS/FAIL for every case. These are proposed cases, not completed live test results.
