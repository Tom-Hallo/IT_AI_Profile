import puppeteer from 'puppeteer-core';
import { execSync } from 'node:child_process';
import path from 'node:path';

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sessionToken = execSync(
  'docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"',
  { encoding: 'utf-8' }
).trim();

async function verify() {
  console.log('=== BẮT ĐẦU KIỂM THỬ TRẢI NGHIỆM DASHBOARD SAU KHI SỬA ===');
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

  // 1. Kiểm tra với Repo A (81 - Tom-Hallo/IT_AI_Profile: Đã phân tích)
  console.log('\n--- 1. DASHBOARD VỚI REPO A (81: ĐÃ PHÂN TÍCH) ---');
  await page.goto('http://localhost:5173/#studio/repos');
  await new Promise(r => setTimeout(r, 1500));
  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="81"]');
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));

  await page.goto('http://localhost:5173/#studio/dashboard');
  await new Promise(r => setTimeout(r, 2000));

  const infoA = await page.evaluate(() => {
    const banner = document.querySelector('.dashboard-scope-banner');
    const title = banner?.querySelector('h2')?.innerText;
    const tags = [...(banner?.querySelectorAll('.scope-tag') ?? [])].map(t => t.innerText.trim());
    const badge = banner?.querySelector('.repo-selection-badge')?.innerText?.replace(/\s+/g, ' ').trim();
    const notice = banner?.querySelector('.dashboard-scope-notice p')?.innerText;
    const radarTitle = document.querySelector('.radar-header h2')?.innerText;
    const radarCaption = document.querySelector('.radar-values p')?.innerText;
    return { title, tags, badge, notice, radarTitle, radarCaption };
  });
  console.log('Repo A Dashboard Info:', JSON.stringify(infoA, null, 2));

  const bannerElA = await page.$('.dashboard-scope-banner');
  if (bannerElA) {
    await bannerElA.screenshot({
      path: 'C:/Users/ADMIN/.gemini/antigravity/brain/e8e9f772-bac7-49a4-ad90-8635622f9aac/dashboard-scope-banner-analyzed.png'
    });
    console.log('Saved dashboard-scope-banner-analyzed.png');
  }

  // 2. Chuyển sang Repo B (83 - NguyenHoangQuan-N25dtcn046/test: Đã phân tích)
  console.log('\n--- 2. DASHBOARD VỚI REPO B (83: ĐÃ PHÂN TÍCH) ---');
  await page.goto('http://localhost:5173/#studio/repos');
  await new Promise(r => setTimeout(r, 1500));
  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="83"]');
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));

  await page.goto('http://localhost:5173/#studio/dashboard');
  await new Promise(r => setTimeout(r, 2000));

  const infoB = await page.evaluate(() => {
    const banner = document.querySelector('.dashboard-scope-banner');
    const badge = banner?.querySelector('.repo-selection-badge')?.innerText?.replace(/\s+/g, ' ').trim();
    return { badge };
  });
  console.log('Repo B Dashboard Info:', JSON.stringify(infoB, null, 2));

  // 3. Chuyển sang Repo C (82 - Tom-Hallo/Collabbb-together: CHƯA PHÂN TÍCH)
  console.log('\n--- 3. DASHBOARD VỚI REPO C (82: CHƯA PHÂN TÍCH) ---');
  await page.goto('http://localhost:5173/#studio/repos');
  await new Promise(r => setTimeout(r, 1500));
  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="82"]');
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));

  await page.goto('http://localhost:5173/#studio/dashboard');
  await new Promise(r => setTimeout(r, 2000));

  const infoC = await page.evaluate(() => {
    const banner = document.querySelector('.dashboard-scope-banner');
    const badge = banner?.querySelector('.repo-selection-badge')?.innerText?.replace(/\s+/g, ' ').trim();
    const actionBtn = banner?.querySelector('.repo-selection-badge button')?.innerText?.trim();
    return { badge, actionBtn };
  });
  console.log('Repo C (Chưa phân tích) Dashboard Info:', JSON.stringify(infoC, null, 2));

  const bannerElC = await page.$('.dashboard-scope-banner');
  if (bannerElC) {
    await bannerElC.screenshot({
      path: 'C:/Users/ADMIN/.gemini/antigravity/brain/e8e9f772-bac7-49a4-ad90-8635622f9aac/dashboard-scope-banner-unanalyzed.png'
    });
    console.log('Saved dashboard-scope-banner-unanalyzed.png');
  }

  // Chụp toàn màn hình Dashboard sau khi hoàn thiện
  await page.screenshot({
    path: 'C:/Users/ADMIN/.gemini/antigravity/brain/e8e9f772-bac7-49a4-ad90-8635622f9aac/dashboard-full-after-fix.png'
  });
  console.log('Saved dashboard-full-after-fix.png');

  await browser.close();
  console.log('=== HOÀN TẤT KIỂM THỬ ===');
}
verify();
