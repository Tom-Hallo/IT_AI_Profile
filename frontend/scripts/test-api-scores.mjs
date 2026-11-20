import { execSync } from 'node:child_process';

const sessionToken = execSync(
  'docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"',
  { encoding: 'utf-8' }
).trim();

async function check() {
  const headers = { 'Cookie': 'ita_session=' + sessionToken };
  const resRepos = await fetch('http://localhost:8000/api/v1/github/repositories?per_page=20', { headers });
  console.log('GET /github/repositories status:', resRepos.status);
  const repos = await resRepos.json();
  console.log('Repos items count:', repos.items?.length);
  for (const r of repos.items.slice(0, 5)) {
    console.log(`Repo: ${r.id} | ${r.full_name || r.name} | analyzed_at: ${r.analyzed_at} | latest_report_id: ${r.latest_report_id}`);
    const reportRes = await fetch(`http://localhost:8000/api/v1/repositories/${r.id}/analysis/dashboard-report`, { headers });
    const report = await reportRes.json().catch(() => null);
    console.log(`  dashboard-report:`, report ? `ID ${report.id} (status: ${report.status})` : 'null');
    if (report?.id) {
      const skillsRes = await fetch(`http://localhost:8000/api/v1/scoring/repositories/${r.id}/skills?report_id=${report.id}`, { headers });
      const skills = await skillsRes.json().catch(() => null);
      console.log(`  skills count: ${skills?.length}`);
      if (skills?.length) {
        console.log(`    samples:`, skills.slice(0, 3).map(s => `${s.technology} (${s.kind}): ${s.score}`));
      }
    }
  }
}
check();
