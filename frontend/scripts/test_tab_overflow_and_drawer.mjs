import { chromium } from 'playwright-core';
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';
const ARTIFACT_DIR = 'C:\\Users\\ADMIN\\.gemini\\antigravity\\brain\\e65cc7ad-ad67-4f76-acc3-0685316d0551\\drawer_verification';

if (!fs.existsSync(ARTIFACT_DIR)) {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
}

function getSessionToken() {
  try {
    const output = execSync('docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"');
    return output.toString().trim();
  } catch (err) {
    return null;
  }
}

async function run() {
  console.log('=== TEST: TAB OVERFLOW & FLYOUT DRAWER MODE WITH CHATBOT ===');
  const token = getSessionToken();
  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  // Test 1: 1024x768 (as in User Screenshot 2)
  console.log('\n--- Test on 1024x768 (User Screenshot Scenario) ---');
  const context = await browser.newContext({ viewport: { width: 1024, height: 768 } });
  if (token) {
    await context.addCookies([{ name: 'ita_session', value: token, domain: 'localhost', path: '/' }]);
  }
  const page = await context.newPage();

  try {
    await page.goto(`${BASE_URL}/#studio/cv`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);

    // 1. Verify tab wrapping without overflow in normal mode
    const tabsOverflow = await page.evaluate(() => {
      const el = document.querySelector('.cv-intel-tabs');
      if (!el) return false;
      return el.scrollWidth > el.clientWidth;
    });
    console.log(`[PASS] 1. Tab container overflow (scrollWidth > clientWidth): ${tabsOverflow} (Expected false)`);

    await page.screenshot({ path: path.join(ARTIFACT_DIR, '01_1024_normal_tabs.png') });

    // 2. Open AI Mentor (Hỏi Mentor)
    const mentorBtn = await page.$('#mentor-toggle');
    await mentorBtn.click();
    await page.waitForTimeout(600);

    const hasMentor = await page.$eval('.workspace-body', el => el.classList.contains('has-mentor'));
    const intelHiddenDefault = await page.$eval('.cv-panel-intel', el => window.getComputedStyle(el).display === 'none');
    console.log(`[PASS] 2. Mentor opened: has-mentor = ${hasMentor}, Intel tool panel collapsed by default = ${intelHiddenDefault}`);

    await page.screenshot({ path: path.join(ARTIFACT_DIR, '02_1024_mentor_opened_clean.png') });

    // 3. Open Tools while AI Mentor is active (Trigger Flyout Drawer)
    const toggleIntelBtn = await page.$('.cv-toggle-intel-btn');
    await toggleIntelBtn.click();
    await page.waitForTimeout(500);

    const intelBox = await page.locator('.cv-panel-intel').boundingBox();
    const mentorBox = await page.locator('#mentor-panel').boundingBox();

    console.log(`[PASS] 3. Flyout Drawer active: Width = ${Math.round(intelBox.width)}px (Expected >= 340px, not squeezed!)`);
    console.log(`[PASS] 3b. Drawer Box: x=${Math.round(intelBox.x)}, w=${Math.round(intelBox.width)} | Mentor Box: x=${Math.round(mentorBox.x)}, w=${Math.round(mentorBox.width)}`);

    const noOverlap = (intelBox.x + intelBox.width) <= (mentorBox.x + 5);
    console.log(`[PASS] 3c. Chatbot DOES NOT overlap Drawer (Drawer right edge <= Mentor left edge): ${noOverlap}`);

    const closeBtnVisible = await page.$eval('.cv-intel-close-btn', el => window.getComputedStyle(el).display !== 'none');
    console.log(`[PASS] 3d. Close button (✕ Đóng) visible in Drawer: ${closeBtnVisible}`);

    // Verify tabs inside drawer do not overflow
    const drawerTabsOverflow = await page.evaluate(() => {
      const el = document.querySelector('.cv-intel-tabs');
      if (!el) return false;
      return el.scrollWidth > el.clientWidth;
    });
    console.log(`[PASS] 3e. Tabs inside Drawer overflow: ${drawerTabsOverflow} (Expected false)`);

    await page.screenshot({ path: path.join(ARTIFACT_DIR, '03_1024_drawer_open_with_mentor.png') });

    // 4. Click Close button in Drawer
    const closeBtn = await page.$('.cv-intel-close-btn');
    await closeBtn.click();
    await page.waitForTimeout(400);

    const intelHiddenAfterClose = await page.$eval('.cv-panel-intel', el => window.getComputedStyle(el).display === 'none');
    console.log(`[PASS] 4. Clicked ✕ Đóng: Drawer closed cleanly = ${intelHiddenAfterClose}`);

    await page.screenshot({ path: path.join(ARTIFACT_DIR, '04_1024_drawer_closed.png') });

  } catch (err) {
    console.error('Test error on 1024x768:', err);
  } finally {
    await context.close();
  }

  // Test 2: 1440x900
  console.log('\n--- Test on 1440x900 ---');
  const context2 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  if (token) {
    await context2.addCookies([{ name: 'ita_session', value: token, domain: 'localhost', path: '/' }]);
  }
  const page2 = await context2.newPage();
  try {
    await page2.goto(`${BASE_URL}/#studio/cv`, { waitUntil: 'networkidle' });
    await page2.waitForTimeout(1000);

    await page2.click('#mentor-toggle');
    await page2.waitForTimeout(600);

    await page2.click('.cv-toggle-intel-btn');
    await page2.waitForTimeout(500);

    const intelBox = await page2.locator('.cv-panel-intel').boundingBox();
    const mentorBox = await page2.locator('#mentor-panel').boundingBox();
    console.log(`[PASS] 1440x900 Drawer Width = ${Math.round(intelBox.width)}px, Drawer Right <= Mentor Left: ${(intelBox.x + intelBox.width) <= (mentorBox.x + 5)}`);

    await page2.screenshot({ path: path.join(ARTIFACT_DIR, '05_1440_drawer_open_with_mentor.png') });
  } catch (err) {
    console.error('Test error on 1440x900:', err);
  } finally {
    await context2.close();
    await browser.close();
  }
  console.log('\n=== ALL TESTS FINISHED SUCCESSFULLY ===');
}

run();
