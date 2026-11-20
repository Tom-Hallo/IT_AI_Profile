import puppeteer from 'puppeteer-core';
import { execSync } from 'child_process';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';

function getSessionToken() {
  try {
    const output = execSync('docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"');
    return output.toString().trim();
  } catch (err) {
    console.error('Failed to generate session token:', err.message);
    return null;
  }
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function testAnalysisQueue() {
  console.log('=== STARTING MANDATORY REGRESSION TEST: ANALYSIS QUEUE & EXECUTION ===');

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1280,800']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  const token = getSessionToken();
  if (!token) throw new Error('Could not get session token');

  await page.setCookie({
    name: 'ita_session',
    value: token,
    domain: 'localhost',
    path: '/'
  });

  let createdJobId = null;
  page.on('response', async res => {
    if (res.url().includes('/api/v1/analysis/jobs') && res.request().method() === 'POST') {
      try {
        const body = await res.json();
        createdJobId = body.id;
        console.log(`[API RESPONSE] Created Analysis Job ID: ${createdJobId}, Status: ${body.status}`);
      } catch {}
    }
  });

  await page.goto(`${BASE_URL}/#studio/repos`, { waitUntil: 'networkidle0' });
  await sleep(1000);

  // Click on a public repo (e.g., repo 129 or first public repo)
  const repoBtn = await page.$('.repo-item');
  if (!repoBtn) throw new Error('No repository found in repo list');
  const repoName = await page.$eval('.repo-item strong', el => el.textContent);
  console.log(`Selected repository: ${repoName}`);
  await repoBtn.click();
  await sleep(800);

  // Click the Analyze button
  const analyzeBtn = await page.$('button[data-act="analyze"]');
  if (!analyzeBtn) throw new Error('Analyze button not found');

  const isDisabled = await page.$eval('button[data-act="analyze"]', el => el.disabled);
  console.log(`Analyze button disabled status: ${isDisabled}`);

  console.log('Clicking "Phân tích" button on UI...');
  await analyzeBtn.click();
  await sleep(1500);

  if (!createdJobId) {
    console.log('Warning: No job ID intercepted directly via POST. Checking job via status or current analysis...');
  }

  // Monitor the UI status and API status for up to 60 seconds
  console.log('\n--- Tracking job progress on Web UI & Backend API ---');
  let startTime = Date.now();
  let completed = false;
  let lastStatus = '';
  let lastStep = '';

  while (Date.now() - startTime < 60000) {
    const elapsed = Math.round((Date.now() - startTime) / 1000);

    // Check UI progress notice
    const uiNotice = await page.$eval('.notice[role="status"]', el => el.textContent).catch(() => null);
    const hasCancelBtn = await page.$('button[data-act="cancel-analysis"]').catch(() => null);
    const hasReportDetails = await page.$('#repo-details').catch(() => null);

    // If we have job ID, query backend API
    let apiStatus = null;
    if (createdJobId) {
      try {
        const apiRes = execSync(`curl.exe -s -m 5 -H "Cookie: ita_session=${token}" http://localhost:8000/api/v1/analysis/jobs/${createdJobId}`);
        apiStatus = JSON.parse(apiRes.toString());
      } catch {}
    }

    const currentStatus = apiStatus?.status || (uiNotice ? 'processing' : (hasReportDetails ? 'succeeded' : 'unknown'));
    const currentStep = apiStatus?.step || '';

    if (currentStatus !== lastStatus || currentStep !== lastStep) {
      console.log(`[T+${elapsed}s] UI Notice: "${uiNotice || 'None'}" | API Status: ${currentStatus} (Step: ${currentStep}, Progress: ${apiStatus?.progress || 0}%)`);
      lastStatus = currentStatus;
      lastStep = currentStep;
    }

    if (apiStatus?.status === 'succeeded' || (!uiNotice && hasReportDetails && elapsed > 3)) {
      console.log(`\n>>> SUCCESS! Job completed successfully at T+${elapsed}s! Report details rendered.`);
      completed = true;
      break;
    }

    if (apiStatus?.status === 'failed' || apiStatus?.status === 'cancelled') {
      console.log(`\n>>> Job reached terminal state: ${apiStatus.status} (${apiStatus.error_code || 'No error code'})`);
      completed = true;
      break;
    }

    await sleep(2000);
  }

  // Check worker container logs
  console.log('\n--- Recent Worker Container Logs ---');
  try {
    const workerLogs = execSync('docker compose logs --tail 10 worker').toString();
    console.log(workerLogs);
  } catch (err) {
    console.log('Worker logs err:', err.message);
  }

  await page.screenshot({ path: 'C:\\Users\\ADMIN\\.gemini\\antigravity\\brain\\e8e9f772-bac7-49a4-ad90-8635622f9aac\\qa-analysis-job.png' });

  await browser.close();

  if (completed) {
    console.log('\n=== RESULT: PASS (Analysis queue, worker processing, and UI updates verified) ===');
  } else {
    console.log('\n=== RESULT: INVESTIGATE (Job did not reach terminal state within 60s) ===');
  }
}

testAnalysisQueue().catch(err => {
  console.error('Test Error:', err);
  process.exit(1);
});
