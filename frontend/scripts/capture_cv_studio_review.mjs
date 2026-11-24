import { chromium } from 'playwright-core';
import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';
const OUT_DIR = 'C:\\Users\\ADMIN\\.gemini\\antigravity\\brain\\e65cc7ad-ad67-4f76-acc3-0685316d0551\\cv_studio_review';
const SAMPLE_PDF = 'C:\\Users\\ADMIN\\.gemini\\antigravity\\brain\\e65cc7ad-ad67-4f76-acc3-0685316d0551\\.user_uploaded\\media_1795437555024_e7625e38.pdf';

function getSessionToken() {
  try {
    const output = execSync('docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"');
    return output.toString().trim();
  } catch (err) {
    return null;
  }
}

async function run() {
  const token = getSessionToken();
  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900']
  });

  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  if (token) {
    await context.addCookies([{ name: 'ita_session', value: token, domain: 'localhost', path: '/' }]);
  }

  const page = await context.newPage();
  try {
    // 1. Màn hình khởi đầu
    await page.goto(`${BASE_URL}/#studio/cv`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(OUT_DIR, '01_initial_studio.png'), fullPage: false });
    console.log('Saved 01_initial_studio.png');

    // 2. Upload sample PDF hoặc nạp dữ liệu phong phú để render CV hoàn chỉnh
    if (fs.existsSync(SAMPLE_PDF)) {
      const fileInput = await page.$('#cv-upload');
      if (fileInput) {
        await fileInput.setInputFiles(SAMPLE_PDF);
        await page.waitForFunction(() => !document.querySelector('.cv-loading-notice'), { timeout: 30000 });
        await page.waitForTimeout(1200);
      }
    }
    await page.screenshot({ path: path.join(OUT_DIR, '02_sample_cv_loaded.png'), fullPage: false });
    console.log('Saved 02_sample_cv_loaded.png');

    // 3. Chuyển sang Tab Công cụ (Minh chứng Git, ATS, Trợ lý AI)
    const atsTab = await page.$('button[data-act="cv-intel-tab"][data-id="ats"]');
    if (atsTab) {
      await atsTab.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(OUT_DIR, '03_ats_tab.png'), fullPage: false });
      console.log('Saved 03_ats_tab.png');
    }

    // 4. Mở AI Mentor panel
    const mentorToggle = await page.$('#mentor-toggle');
    if (mentorToggle) {
      await mentorToggle.click();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(OUT_DIR, '04_mentor_open.png'), fullPage: false });
      console.log('Saved 04_mentor_open.png');
    }

    // 5. Test trên màn hình Laptop 1366x768
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(OUT_DIR, '05_laptop_1366.png'), fullPage: false });
    console.log('Saved 05_laptop_1366.png');

  } catch (err) {
    console.error('Error during capture:', err);
  } finally {
    await browser.close();
  }
}

run();
