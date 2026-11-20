import puppeteer from 'puppeteer-core';
import { execSync } from 'node:child_process';

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sessionToken = execSync(
  'docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"',
  { encoding: 'utf-8' }
).trim();

async function investigate() {
  console.log('=== BẮT ĐẦU ĐIỀU TRA A -> B -> A TRÊN LOCALHOST ===');
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  await page.setCookie({
    name: 'ita_session',
    value: sessionToken,
    domain: 'localhost',
    path: '/',
    httpOnly: false,
    secure: false,
    sameSite: 'Lax',
  });

  const networkRequests = [];
  page.on('request', req => {
    if (req.url().includes('/api/v1/')) {
      networkRequests.push({ method: req.method(), url: req.url() });
    }
  });

  // Step 1: Mở Dashboard
  console.log('\n--- BƯỚC 1: MỞ DASHBOARD BAN ĐẦU ---');
  await page.goto('http://localhost:5173/#studio/dashboard');
  await new Promise(r => setTimeout(r, 2500));

  const initialDashInfo = await page.evaluate(() => {
    const title = document.querySelector('.page-heading h1')?.innerText;
    const radarTitle = document.querySelector('.radar-header h2')?.innerText;
    const radarCaption = document.querySelector('.radar-values p')?.innerText;
    const scores = [...document.querySelectorAll('.radar-indicator')].map(b => b.innerText.replace(/\s+/g, ' ').trim());
    const techScores = [...document.querySelectorAll('.score-item')].map(b => b.innerText.replace(/\s+/g, ' ').trim());
    return { title, radarTitle, radarCaption, scores, techScoresCount: techScores.length, sampleTechScores: techScores.slice(0, 3) };
  });
  console.log('Dashboard Info:', JSON.stringify(initialDashInfo, null, 2));

  // Step 2: Chuyển sang Repos, chọn Repo A (ID 81: Tom-Hallo/IT_AI_Profile)
  console.log('\n--- BƯỚC 2: CHỌN REPO A (ID 81) ---');
  networkRequests.length = 0;
  await page.goto('http://localhost:5173/#studio/repos');
  await new Promise(r => setTimeout(r, 2000));

  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="81"]');
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 2000));

  const repoAInfo = await page.evaluate(() => {
    return {
      selectedRepo: sessionStorage.getItem('ita-studio-selected-repo'),
      bannerTitle: document.querySelector('.repo-context-banner')?.innerText?.replace(/\s+/g, ' ').trim(),
      heading: document.querySelector('.repo-header h2')?.innerText
    };
  });
  console.log('Repo A state:', repoAInfo);
  console.log('Requests for Repo A:', networkRequests.map(r => `${r.method} ${r.url}`));

  // Quay lại Dashboard kiểm tra
  console.log('\n--- KIỂM TRA DASHBOARD KHI CHỌN REPO A ---');
  networkRequests.length = 0;
  await page.goto('http://localhost:5173/#studio/dashboard');
  await new Promise(r => setTimeout(r, 2000));

  const dashAfterA = await page.evaluate(() => {
    const radarCaption = document.querySelector('.radar-values p')?.innerText;
    const scores = [...document.querySelectorAll('.radar-indicator')].map(b => b.innerText.replace(/\s+/g, ' ').trim());
    // Click trục radar để mở insight evidence
    const firstAxis = document.querySelector('.radar-indicator');
    if (firstAxis) firstAxis.click();
    const insightEvidence = document.querySelector('.radar-insight')?.innerText?.replace(/\s+/g, ' ').trim();
    return { radarCaption, scores, insightEvidence };
  });
  console.log('Dashboard after Repo A:', dashAfterA);
  console.log('Requests on Dashboard:', networkRequests.map(r => `${r.method} ${r.url}`));

  // Step 3: Chuyển sang Repos, chọn Repo B (ID 83: NguyenHoangQuan-N25dtcn046/test)
  console.log('\n--- BƯỚC 3: CHỌN REPO B (ID 83) ---');
  networkRequests.length = 0;
  await page.goto('http://localhost:5173/#studio/repos');
  await new Promise(r => setTimeout(r, 2000));

  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="83"]');
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 2000));

  const repoBInfo = await page.evaluate(() => {
    return {
      selectedRepo: sessionStorage.getItem('ita-studio-selected-repo'),
      bannerTitle: document.querySelector('.repo-context-banner')?.innerText?.replace(/\s+/g, ' ').trim(),
      heading: document.querySelector('.repo-header h2')?.innerText
    };
  });
  console.log('Repo B state:', repoBInfo);
  console.log('Requests for Repo B:', networkRequests.map(r => `${r.method} ${r.url}`));

  // Quay lại Dashboard kiểm tra
  console.log('\n--- KIỂM TRA DASHBOARD KHI CHỌN REPO B ---');
  networkRequests.length = 0;
  await page.goto('http://localhost:5173/#studio/dashboard');
  await new Promise(r => setTimeout(r, 2000));

  const dashAfterB = await page.evaluate(() => {
    const radarCaption = document.querySelector('.radar-values p')?.innerText;
    const scores = [...document.querySelectorAll('.radar-indicator')].map(b => b.innerText.replace(/\s+/g, ' ').trim());
    const firstAxis = document.querySelector('.radar-indicator');
    if (firstAxis) firstAxis.click();
    const insightEvidence = document.querySelector('.radar-insight')?.innerText?.replace(/\s+/g, ' ').trim();
    return { radarCaption, scores, insightEvidence };
  });
  console.log('Dashboard after Repo B:', dashAfterB);
  console.log('Requests on Dashboard:', networkRequests.map(r => `${r.method} ${r.url}`));

  // Step 4: Quay lại Repo A (ID 81)
  console.log('\n--- BƯỚC 4: QUAY LẠI REPO A (ID 81) ---');
  await page.goto('http://localhost:5173/#studio/repos');
  await new Promise(r => setTimeout(r, 2000));
  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="81"]');
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 2000));
  await page.goto('http://localhost:5173/#studio/dashboard');
  await new Promise(r => setTimeout(r, 2000));

  const dashAfterA2 = await page.evaluate(() => {
    const scores = [...document.querySelectorAll('.radar-indicator')].map(b => b.innerText.replace(/\s+/g, ' ').trim());
    const firstAxis = document.querySelector('.radar-indicator');
    if (firstAxis) firstAxis.click();
    const insightEvidence = document.querySelector('.radar-insight')?.innerText?.replace(/\s+/g, ' ').trim();
    return { scores, insightEvidence };
  });
  console.log('Dashboard after return to Repo A:', dashAfterA2);

  await browser.close();
  console.log('\n=== HOÀN TẤT ĐIỀU TRA ===');
}
investigate();
