import puppeteer from 'puppeteer-core';
import { execSync } from 'node:child_process';
import path from 'node:path';

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const BASE_URL = 'http://localhost:5173';
const ARTIFACTS_DIR = 'C:/Users/ADMIN/.gemini/antigravity/brain/e8e9f772-bac7-49a4-ad90-8635622f9aac';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function inspectBaseline() {
  console.log('>>> BẮT ĐẦU ĐÁNH GIÁ TRẢI NGHIỆM DEVELOPER TRƯỚC KHI SỬA (BASELINE AUDIT)');

  const sessionToken = execSync(
    'docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"',
    { encoding: 'utf-8' }
  ).trim();

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1280,800']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  await page.setCookie({
    name: 'ita_session',
    value: sessionToken,
    domain: 'localhost',
    path: '/'
  });

  await page.goto(`${BASE_URL}/#studio/repos`, { waitUntil: 'networkidle0' });
  await page.evaluate(() => {
    try { localStorage.setItem('it-talent-pixel:locale', 'vi'); } catch {}
  });
  await page.reload({ waitUntil: 'networkidle0' });
  await sleep(1000);

  // Chụp ảnh baseline màn hình Repositories
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'journey-before-repos-main.png') });

  // Kiểm tra thông tin hiển thị trên Repo hiện tại
  const repoTitle = await page.$eval('#repo-title', el => el.textContent.trim()).catch(() => '');
  const hasRangeInHeader = await page.$eval('.repo-head', el => el.textContent.includes('ngày')).catch(() => false);
  const analyzeBtnLocation = await page.$eval('button[data-act="analyze"]', el => {
    const rect = el.getBoundingClientRect();
    return { top: Math.round(rect.top), left: Math.round(rect.left) };
  }).catch(() => null);

  const hasNextSteps = await page.$('.report-next button').catch(() => null);
  const nextStepsCount = await page.$$eval('.report-next button', els => els.length).catch(() => 0);

  console.log('--- BASELINE METRICS ---');
  console.log(`Repo đang chọn: "${repoTitle}"`);
  console.log(`Khoảng thời gian hiển thị ngay trong header repo: ${hasRangeInHeader}`);
  console.log(`Vị trí nút Phân tích repo:`, analyzeBtnLocation);
  console.log(`Số lượng hành động tiếp theo trong báo cáo: ${nextStepsCount}`);

  await browser.close();
}

inspectBaseline();
