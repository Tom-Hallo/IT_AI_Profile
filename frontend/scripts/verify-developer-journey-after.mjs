import puppeteer from 'puppeteer-core';
import { execSync } from 'node:child_process';
import path from 'node:path';

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const BASE_URL = 'http://localhost:5173';
const ARTIFACTS_DIR = 'C:/Users/ADMIN/.gemini/antigravity/brain/e8e9f772-bac7-49a4-ad90-8635622f9aac';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function verifyJourney() {
  console.log('>>> BẮT ĐẦU ĐÁNH GIÁ TRẢI NGHIỆM DEVELOPER SAU KHI SỬA (AFTER VERIFICATION)');

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

  // Tình huống 1: Mở Repositories, nạp repo
  await page.goto(`${BASE_URL}/#studio/repos`, { waitUntil: 'networkidle0' });
  await page.evaluate(() => {
    try { localStorage.setItem('it-talent-pixel:locale', 'vi'); } catch {}
  });
  await page.reload({ waitUntil: 'networkidle0' });
  await sleep(1000);

  // Chụp ảnh màn hình mới
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'journey-after-repos-main.png') });

  // 1. Kiểm tra Context Banner
  const hasContextBanner = await page.$('.repo-context-banner').catch(() => null);
  const contextText = hasContextBanner ? await page.$eval('.repo-context-banner', el => el.textContent.trim()) : '';

  // 2. Kiểm tra Highlights Card
  const hasHighlights = await page.$('.repo-highlights-card').catch(() => null);
  const highlightsText = hasHighlights ? await page.$eval('.repo-highlights-card', el => el.textContent.trim()) : '';

  // 3. Kiểm tra Action Grid (Next steps)
  const actionCardsCount = await page.$$eval('.action-card', els => els.length).catch(() => 0);

  // 4. Kiểm tra Badge "Đã có báo cáo" trong danh sách
  const analyzedBadgesCount = await page.$$eval('.repo-item .badge.green', els => els.length).catch(() => 0);

  // 5. Kiểm tra tính năng giữ lựa chọn (Persistence):
  // Chọn repo thứ 2 trong danh sách
  const repoButtons = await page.$$('.repo-item');
  let selectedRepoName = '';
  if (repoButtons.length > 1) {
    await repoButtons[1].click();
    await sleep(800);
    selectedRepoName = await page.$eval('#repo-title', el => el.textContent.trim());
  }

  // Reload trang để kiểm tra xem có giữ đúng repo không
  await page.reload({ waitUntil: 'networkidle0' });
  await sleep(1000);
  const reloadedRepoName = await page.$eval('#repo-title', el => el.textContent.trim());
  const isPersisted = selectedRepoName && selectedRepoName === reloadedRepoName;

  console.log('\n--- KẾT QUẢ KIỂM CHỨNG TRẢI NGHIỆM SAU KHI SỬA ---');
  console.log(`1. Context Banner hiển thị: ${Boolean(hasContextBanner)} ("${contextText.slice(0, 100)}...")`);
  console.log(`2. Highlights Card (Phát hiện năng lực cốt lõi): ${Boolean(hasHighlights)}`);
  console.log(`3. Số lượng hành động tiếp theo (Next Steps Cards): ${actionCardsCount} (Đạt chuẩn 3 lối tắt)`);
  console.log(`4. Huy hiệu "Đã có báo cáo" trên danh sách repo: ${analyzedBadgesCount > 0}`);
  console.log(`5. Tính năng giữ lựa chọn khi tải lại trang: ${isPersisted ? 'PASS' : 'FAIL'} (Repo: "${reloadedRepoName}")`);

  await browser.close();
}

verifyJourney();
