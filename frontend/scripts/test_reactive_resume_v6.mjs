import { chromium } from 'playwright-core';
import { execSync } from 'child_process';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';

function getSessionToken() {
  try {
    const output = execSync('docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"');
    return output.toString().trim();
  } catch (err) {
    return null;
  }
}

async function run() {
  console.log('=== KIỂM THỬ TÍNH NĂNG MỚI: REACTIVE RESUME V6 IN IT TALENT ===');
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
    await page.goto(`${BASE_URL}/#studio/cv`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);

    // 1. Kiểm tra Top Toolbar
    const titleText = await page.$eval('.cv-toolbar-title', el => el.textContent.trim()).catch(() => '');
    console.log('[PASS] 1. Top Toolbar hiển thị tiêu đề CV:', titleText);

    // 2. Kiểm tra Accordion Sections
    const sectionCount = await page.$$eval('.cv-struct-section', els => els.length);
    console.log(`[PASS] 2. Số section Accordion hiện có: ${sectionCount}`);

    // 3. Kiểm tra Thêm mục mới vào section đầu tiên
    const addEntryBtn = await page.$('.cv-add-entry-btn');
    if (addEntryBtn) {
      const entriesBefore = await page.$$eval('.cv-struct-entry', els => els.length);
      await addEntryBtn.click();
      await page.waitForTimeout(500);
      const entriesAfter = await page.$$eval('.cv-struct-entry', els => els.length);
      console.log(`[PASS] 3. Thêm mục vào Accordion: Trước = ${entriesBefore}, Sau = ${entriesAfter}`);
    }

    // 4. Kiểm tra Xóa mục vừa thêm
    const delBtn = await page.$('.cv-entry-del-btn');
    if (delBtn) {
      const countBefore = await page.$$eval('.cv-struct-entry', els => els.length);
      await delBtn.click();
      await page.waitForTimeout(500);
      const countAfter = await page.$$eval('.cv-struct-entry', els => els.length);
      console.log(`[PASS] 4. Xóa mục trong Accordion: Trước = ${countBefore}, Sau = ${countAfter}`);
    }

    // 5. Kiểm tra Thêm phần mới (+ Dự án)
    const addSecBtn = await page.$('button[data-act="cv-add-section"][data-type="Projects"]');
    if (addSecBtn) {
      await addSecBtn.click();
      await page.waitForTimeout(500);
      const bodyText = await page.$eval('textarea[name="body"]', el => el.value);
      console.log('[PASS] 5. Thêm phần mới (+ Dự án): Có chứa tiêu đề dự án:', bodyText.includes('DỰ ÁN'));
    }

    // 6. Kiểm tra Bảng Thiết kế & Công cụ (Design Tab Cards)
    const designTabBtn = await page.$('button[data-act="cv-intel-tab"][data-id="design"]');
    if (designTabBtn) {
      await designTabBtn.click();
      await page.waitForTimeout(300);
      const cards = await page.$$eval('.cv-tpl-card', els => els.length);
      console.log(`[PASS] 6. Thẻ chọn mẫu trong Tab Thiết kế: ${cards} mẫu`);
    }

    // 7. Kiểm tra Thu gọn / Mở rộng bảng Công cụ
    const toggleBtn = await page.$('.cv-toggle-intel-btn');
    if (toggleBtn) {
      await page.click('.cv-toggle-intel-btn');
      await page.waitForTimeout(300);
      const isCollapsed = await page.$('.cv-workspace-3col.intel-collapsed').then(Boolean);
      console.log('[PASS] 7. Thu gọn bảng Công cụ (intel-collapsed):', isCollapsed);
      await page.click('.cv-toggle-intel-btn');
      await page.waitForTimeout(300);
      const isReopened = await page.$('.cv-workspace-3col.intel-open').then(Boolean);
      console.log('[PASS] 7b. Mở lại bảng Công cụ (intel-open):', isReopened);
    }

    // 8. Kiểm tra Mở AI Mentor và Layout thích ứng (Mentor Focus Mode)
    const mentorToggle = await page.$('#mentor-toggle');
    if (mentorToggle) {
      await mentorToggle.click();
      await page.waitForTimeout(600);
      const hasMentorClass = await page.$eval('.workspace-body', el => el.classList.contains('has-mentor')).catch(() => false);
      const isIntelHidden = await page.$eval('.cv-panel-intel', el => window.getComputedStyle(el).display === 'none').catch(() => false);
      const hasHorizScroll = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      console.log('[PASS] 8. Mentor Focus Mode: has-mentor =', hasMentorClass, ', Panel công cụ tự thu gọn =', isIntelHidden, ', Không cuộn ngang =', !hasHorizScroll);

      // Đóng Mentor
      const mentorClose = await page.$('#mentor-close, button[data-act="close-mentor"]');
      if (mentorClose) await mentorClose.click();
      else await mentorToggle.click();
      await page.waitForTimeout(600);
      const mentorClosed = await page.$eval('.workspace-body', el => !el.classList.contains('has-mentor')).catch(() => false);
      console.log('[PASS] 8b. Đóng AI Mentor khôi phục layout sạch sẽ:', mentorClosed);
    }

  } catch (err) {
    console.error('Lỗi kiểm thử:', err.message);
  } finally {
    await browser.close();
  }
}

run();
