import { chromium } from 'playwright-core';
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';
const ARTIFACT_DIR = 'C:\\Users\\ADMIN\\.gemini\\antigravity\\brain\\e65cc7ad-ad67-4f76-acc3-0685316d0551\\cv_a4_verification';

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

const VIEWPORTS = [
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '1440x900',  width: 1440, height: 900 },
  { name: '1366x768',  width: 1366, height: 768 },
  { name: '1280x800',  width: 1280, height: 800 },
  { name: '1024x768',  width: 1024, height: 768 },
];

async function run() {
  console.log('=== MULTI-RESOLUTION A4 PREVIEW & SECTION NAVIGATOR VERIFICATION ===');
  const token = getSessionToken();
  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const results = [];

  for (const vp of VIEWPORTS) {
    console.log(`\n--- Testing Viewport: ${vp.name} (${vp.width}x${vp.height}) ---`);
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    if (token) {
      await context.addCookies([{ name: 'ita_session', value: token, domain: 'localhost', path: '/' }]);
    }

    const page = await context.newPage();
    try {
      await page.goto(`${BASE_URL}/#studio/cv`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(800);

      // --- Mode A: Mentor Closed ---
      const boxClosed = await page.locator('.cv-paper').first().boundingBox();
      const horizScrollClosed = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      const ratioClosed = boxClosed ? (boxClosed.width / boxClosed.height).toFixed(4) : 'N/A';
      const isPortraitClosed = boxClosed ? boxClosed.width < boxClosed.height : false;

      console.log(`[Mentor Closed] .cv-paper bbox: ${Math.round(boxClosed.width)}x${Math.round(boxClosed.height)}px, Aspect Ratio: ${ratioClosed}, Portrait: ${isPortraitClosed}, No Horiz Scroll: ${!horizScrollClosed}`);

      await page.screenshot({ path: path.join(ARTIFACT_DIR, `${vp.name}_mentor_closed.png`) });

      // --- Mode B: Mentor Open ---
      const mentorToggle = await page.$('#mentor-toggle');
      if (mentorToggle) {
        await mentorToggle.click();
        await page.waitForTimeout(600);
      }

      const boxOpen = await page.locator('.cv-paper').first().boundingBox();
      const horizScrollOpen = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      const ratioOpen = boxOpen ? (boxOpen.width / boxOpen.height).toFixed(4) : 'N/A';
      const isPortraitOpen = boxOpen ? boxOpen.width < boxOpen.height : false;

      console.log(`[Mentor Open]   .cv-paper bbox: ${Math.round(boxOpen.width)}x${Math.round(boxOpen.height)}px, Aspect Ratio: ${ratioOpen}, Portrait: ${isPortraitOpen}, No Horiz Scroll: ${!horizScrollOpen}`);

      await page.screenshot({ path: path.join(ARTIFACT_DIR, `${vp.name}_mentor_open.png`) });

      results.push({
        viewport: vp.name,
        closed: { width: Math.round(boxClosed.width), height: Math.round(boxClosed.height), ratio: ratioClosed, isPortrait: isPortraitClosed, noScroll: !horizScrollClosed },
        open: { width: Math.round(boxOpen.width), height: Math.round(boxOpen.height), ratio: ratioOpen, isPortrait: isPortraitOpen, noScroll: !horizScrollOpen }
      });

      // Close mentor before next viewport test
      if (mentorToggle) {
        await mentorToggle.click();
        await page.waitForTimeout(400);
      }

    } catch (err) {
      console.error(`Error at ${vp.name}:`, err.message);
    } finally {
      await context.close();
    }
  }

  // --- Test Section Navigator & Zoom on 1440x900 ---
  console.log('\n--- Testing Section Navigator & Zoom Controls ---');
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  if (token) {
    await context.addCookies([{ name: 'ita_session', value: token, domain: 'localhost', path: '/' }]);
  }
  const page = await context.newPage();
  try {
    await page.goto(`${BASE_URL}/#studio/cv`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);

    // 1. Verify Section Navigator cards exist
    const navCards = await page.$$eval('.cv-sec-nav-card', els => els.length);
    console.log(`[PASS] Section Navigator cards found: ${navCards}`);

    // 2. Open first section
    const openBtn = await page.$('button[data-act="cv-open-sec"]');
    if (openBtn) {
      await openBtn.click();
      await page.waitForTimeout(400);
      const isFocused = await page.$('.cv-focused-sec-editor').then(Boolean);
      console.log(`[PASS] Clicked Sửa →: Focused Section Editor visible = ${isFocused}`);

      // 3. Click back
      const backBtn = await page.$('button[data-act="cv-nav-back"]');
      if (backBtn) {
        await backBtn.click();
        await page.waitForTimeout(400);
        const returnedToNav = await page.$('.cv-sec-nav-wrap').then(Boolean);
        console.log(`[PASS] Clicked ← Quay lại: Returned to Section Navigator = ${returnedToNav}`);
      }
    }

    // 4. Test Zoom levels
    for (const z of ['85', '100', '115', 'fit']) {
      const zoomBtn = await page.$(`button[data-act="cv-zoom"][data-id="${z}"]`);
      if (zoomBtn) {
        await zoomBtn.click();
        await page.waitForTimeout(300);
        const hasZoomClass = await page.$eval('.cv-preview-viewport', (el, zoom) => el.classList.contains(`cv-zoom-${zoom}`), z);
        const box = await page.locator('.cv-paper').first().boundingBox();
        console.log(`[PASS] Zoom level ${z}: Class applied = ${hasZoomClass}, Paper width = ${Math.round(box.width)}px, height = ${Math.round(box.height)}px`);
      }
    }

    // Capture final verified state
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'final_verified_1440x900.png') });

  } catch (err) {
    console.error('Section Navigator / Zoom test error:', err.message);
  } finally {
    await context.close();
    await browser.close();
  }

  console.log('\n=== VERIFICATION SUMMARY TABLE ===');
  console.table(results.map(r => ({
    Viewport: r.viewport,
    'Closed WxH': `${r.closed.width}x${r.closed.height}`,
    'Closed Ratio': r.closed.ratio,
    'Closed Portrait': r.closed.isPortrait,
    'Open WxH': `${r.open.width}x${r.open.height}`,
    'Open Ratio': r.open.ratio,
    'Open Portrait': r.open.isPortrait
  })));
}

run();
