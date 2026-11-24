import { chromium } from 'playwright-core';
import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';
const SAMPLE_PDF = 'C:\\Users\\ADMIN\\.gemini\\antigravity\\brain\\e65cc7ad-ad67-4f76-acc3-0685316d0551\\.user_uploaded\\media_1795437555024_e7625e38.pdf';

function getSessionToken() {
  try {
    const output = execSync('docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"');
    return output.toString().trim();
  } catch (err) {
    console.error('Failed to get session token:', err.message);
    return null;
  }
}

async function run() {
  console.log('--- BẮT ĐẦU KIỂM THỬ TOÀN DIỆN TÍNH NĂNG CV STUDIO (LOCALHOST) ---');
  const token = getSessionToken();
  console.log('Session token:', token ? 'Created successfully' : 'FAILED');

  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1366,900']
  });

  const context = await browser.newContext({
    viewport: { width: 1366, height: 900 }
  });

  if (token) {
    await context.addCookies([
      {
        name: 'ita_session',
        value: token,
        domain: 'localhost',
        path: '/'
      }
    ]);
  }

  const page = await context.newPage();
  const consoleLogs = [];
  const networkErrors = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleLogs.push(msg.text());
    }
  });

  page.on('requestfailed', req => {
    networkErrors.push({ url: req.url(), failure: req.failure()?.errorText });
  });

  const results = [];
  function record(step, ok, details = '') {
    results.push({ step, ok, details });
    console.log(`[${ok ? 'PASS' : 'FAIL'}] ${step}: ${details}`);
  }

  try {
    // BƯỚC 1: Mở trang CV Studio
    await page.goto(`${BASE_URL}/#studio/cv`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);

    const title = await page.title();
    record('1. Mở trang Studio CV', title.includes('IT Talent'), `Tiêu đề trang: ${title}`);

    // BƯỚC 2: Kiểm tra các tab mẫu CV (plain, tech, reference)
    const tabs = await page.$$eval('.cv-preview .tabs button', btns => btns.map(b => ({ id: b.dataset.id, text: b.textContent.trim(), pressed: b.getAttribute('aria-pressed') })));
    record('2. Kiểm tra 3 Tabs Mẫu CV', tabs.length === 3, `Tabs: ${JSON.stringify(tabs)}`);

    // BƯỚC 3: Nhập thông tin CV và kiểm tra Real-time Preview
    await page.fill('input[name="name"]', 'Nguyễn Văn Test');
    await page.fill('input[name="role"]', 'Senior Backend Engineer');
    await page.fill('textarea[name="body"]', 'Kinh nghiệm 5 năm làm việc với Python, FastAPI, PostgreSQL và Docker.');
    await page.waitForTimeout(500);

    const previewName = await page.$eval('#cv-name', el => el.textContent.trim()).catch(() => '');
    const previewRole = await page.$eval('#cv-role', el => el.textContent.trim()).catch(() => '');
    const previewBody = await page.$eval('#cv-body', el => el.textContent.trim()).catch(() => '');
    record('3. Real-time Preview (Plain/Tech)', previewName === 'Nguyễn Văn Test' && previewRole === 'Senior Backend Engineer',
      `Tên: "${previewName}", Vị trí: "${previewRole}", Nội dung xem trước: "${previewBody.slice(0, 40)}..."`);

    // BƯỚC 4: Chuyển sang Tab "Theo mẫu" (reference)
    await page.click('button[data-id="reference"]');
    await page.waitForTimeout(500);
    const hasRefPaper = await page.$('.cv-paper.cv-reference-paper').then(el => Boolean(el));
    const refName = await page.$eval('.cv-ref-name', el => el.textContent.trim()).catch(() => '');
    record('4. Tab Theo mẫu (Reference)', hasRefPaper && refName.includes('Nguyễn Văn Test'),
      `Có khung reference paper: ${hasRefPaper}, Tên hiển thị: "${refName}"`);

    // BƯỚC 4b: Trực tiếp chỉnh sửa trên mặt giấy CV (WYSIWYG on paper)
    const nameOnPaper = await page.$('#cv-name[contenteditable="true"]');
    if (nameOnPaper) {
      await nameOnPaper.click();
      await nameOnPaper.evaluate(el => {
        el.innerText = 'Trần Văn Trực Tiếp';
        el.dispatchEvent(new Event('input', { bubbles: true }));
      });
      await page.waitForTimeout(300);
      const formInputName = await page.$eval('input[name="name"]', el => el.value);
      record('4b. Sửa trực tiếp trên mặt giấy CV (WYSIWYG Name)', formInputName === 'Trần Văn Trực Tiếp',
        `Tên trên form đồng bộ: "${formInputName}"`);
    }

    // BƯỚC 5: Chuyển lại Tab "Tối giản" & "Kỹ thuật" và kiểm tra tính mượt mà
    await page.click('button[data-id="plain"]');
    await page.waitForTimeout(300);
    const plainTemplate = await page.$eval('.cv-paper', el => el.dataset.template).catch(() => '');
    await page.click('button[data-id="tech"]');
    await page.waitForTimeout(300);
    const techTemplate = await page.$eval('.cv-paper', el => el.dataset.template).catch(() => '');
    await page.click('button[data-id="reference"]');
    await page.waitForTimeout(300);
    const backToRef = await page.$eval('.cv-paper', el => el.dataset.template).catch(() => '');
    record('5. Khôi phục & chuyển đổi qua lại giữa các Tab mượt mà không lỗi',
      plainTemplate === 'plain' && techTemplate === 'tech' && backToRef === 'reference',
      `Plain: ${plainTemplate}, Tech: ${techTemplate}, Reference: ${backToRef}`);

    // BƯỚC 6: Kiểm tra Upload tệp CV (PDF/DOCX)
    if (fs.existsSync(SAMPLE_PDF)) {
      const fileInput = await page.$('#cv-upload');
      await fileInput.setInputFiles(SAMPLE_PDF);
      console.log('Đã đưa file mẫu PDF vào ô upload, đang đợi API xử lý...');

      // Đợi hoàn thành parse
      await page.waitForFunction(() => !document.querySelector('.cv-loading-notice'), { timeout: 30000 });
      await page.waitForTimeout(1000);

      const parsedName = await page.$eval('input[name="name"]', el => el.value);
      const parsedBody = await page.$eval('textarea[name="body"]', el => el.value);
      const activeTab = await page.$eval('.cv-preview .tabs button[aria-pressed="true"]', el => el.dataset.id).catch(() => '');

      record('6. Upload & Xử lý File CV mẫu qua API', parsedBody.length > 100 && activeTab === 'reference',
        `Tên trích xuất: "${parsedName}", Ký tự trích xuất: ${parsedBody.length}, Tự động chuyển tab: "${activeTab}"`);
    } else {
      record('6. Upload File CV mẫu', false, `Không tìm thấy file mẫu tại: ${SAMPLE_PDF}`);
    }

    // BƯỚC 7: Kiểm tra tính năng Lưu CV
    const saveBtn = await page.$('.cv-command-actions button[data-act="cv-save-bar"]');
    if (saveBtn) {
      await saveBtn.click();
      await page.waitForTimeout(2000);
      const toastText = await page.$eval('#toast', el => el.textContent.trim()).catch(() => '');
      const statusBadge = await page.$eval('.cv-command-status', el => el.textContent.trim()).catch(() => '');
      record('7. Lưu CV trên máy chủ', toastText.includes('Đã lưu') || statusBadge.includes('Đã lưu') || statusBadge.includes('Đã tải lên'),
        `Toast: "${toastText}", Status Badge: "${statusBadge}"`);
    } else {
      record('7. Lưu CV', false, 'Không tìm thấy nút Lưu CV trên thanh công cụ');
    }

    // BƯỚC 8: Kiểm tra Chèn kỹ năng từ GitHub
    // Đợi toast cũ từ Bước 7 ẩn đi
    await page.waitForTimeout(4500);
    const insertGitLocator = page.locator('button[data-act="cv-insert-github"]').first();
    if (await insertGitLocator.count()) {
      console.log('Bấm nút Chèn kỹ năng từ GitHub, đợi tổng hợp dữ liệu từ repo...');
      await insertGitLocator.click();
      // Chờ cho đến khi toast mới xuất hiện
      await page.waitForFunction(() => {
        const toast = document.querySelector('#toast');
        return toast && !toast.hidden && toast.textContent.includes('kỹ năng');
      }, { timeout: 20000 }).catch(() => {});
      await page.waitForTimeout(1000);

      const toast = await page.$eval('#toast', el => el.textContent.trim()).catch(() => '');
      const bodyAfter = await page.$eval('textarea[name="body"]', el => el.value);
      record('8. Chèn kỹ năng có bằng chứng từ GitHub', Boolean(toast || bodyAfter.includes('KỸ NĂNG')),
        `Phản hồi hệ thống: Toast: "${toast}", Thân CV chứa kỹ năng: ${bodyAfter.includes('KỸ NĂNG')}`);
    }

    // BƯỚC 8b: Kiểm tra Chuyển đổi Chế độ Soạn thảo (Form Cấu trúc ⇄ Văn bản thô)
    const rawModeBtn = page.locator('button[data-act="cv-editor-mode"][data-id="raw"]');
    const structModeBtn = page.locator('button[data-act="cv-editor-mode"][data-id="structured"]');
    if (await rawModeBtn.count()) {
      await rawModeBtn.click();
      await page.waitForTimeout(300);
      const structInRaw = await page.$('.cv-struct-container').then(Boolean);
      await structModeBtn.click();
      await page.waitForTimeout(300);
      const structInStruct = await page.$('.cv-struct-container').then(Boolean);
      record('8b. Chuyển đổi Chế độ Form cấu trúc ⇄ Văn bản thô', !structInRaw && structInStruct,
        `Form cấu trúc ẩn trong Raw: ${!structInRaw}, Form cấu trúc hiện trong Struct: ${structInStruct}`);
    }

    // BƯỚC 8c: Kiểm tra Zoom CV Preview (85%, 100%, 115%)
    const zoom85 = page.locator('button[data-act="cv-zoom"][data-id="85"]');
    const zoom115 = page.locator('button[data-act="cv-zoom"][data-id="115"]');
    const zoom100 = page.locator('button[data-act="cv-zoom"][data-id="100"]');
    if (await zoom85.count()) {
      await zoom85.click();
      await page.waitForTimeout(200);
      const hasZoom85 = await page.$('.cv-preview-viewport.cv-zoom-85').then(Boolean);
      await zoom115.click();
      await page.waitForTimeout(200);
      const hasZoom115 = await page.$('.cv-preview-viewport.cv-zoom-115').then(Boolean);
      await zoom100.click();
      await page.waitForTimeout(200);
      const hasZoom100 = await page.$('.cv-preview-viewport.cv-zoom-100').then(Boolean);
      record('8c. Zoom CV Preview', hasZoom85 && hasZoom115 && hasZoom100,
        `Zoom 85%: ${hasZoom85}, Zoom 115%: ${hasZoom115}, Zoom 100%: ${hasZoom100}`);
    }

    // BƯỚC 9: Mở Tab ATS và Kiểm tra tính năng Phản hồi ATS
    const atsTabBtn = page.locator('button[data-act="cv-intel-tab"][data-id="ats"]');
    if (await atsTabBtn.count()) {
      await atsTabBtn.click();
      await page.waitForTimeout(300);
    }
    const atsJdLocator = page.locator('textarea[name="ats-jd"]');
    const atsBtnLocator = page.locator('button[data-act="cv-check"]');
    if (await atsBtnLocator.count()) {
      const atsBtnText = (await atsBtnLocator.textContent()).trim();
      const isDisabled = await atsBtnLocator.getAttribute('disabled');
      record('9a. Nhãn và trạng thái nút Kiểm tra ATS', atsBtnText.includes('Kiểm tra ATS') && !isDisabled,
        `Tên nút: "${atsBtnText}", Disabled: ${isDisabled}`);

      await atsJdLocator.fill('Python, FastAPI, Docker, PostgreSQL, Microservices, REST API, Git');
      console.log('Đã nhập JD, bấm Kiểm tra ATS...');
      await atsBtnLocator.click();
      // Đợi kết quả phân tích ATS xuất hiện
      await page.waitForFunction(() => {
        const res = document.querySelector('#ats-result');
        return res && res.textContent.trim().length > 0;
      }, { timeout: 15000 }).catch(() => {});

      const atsResult = await page.$eval('#ats-result', el => el.textContent.trim()).catch(() => '');
      record('9. Phân tích Phản hồi ATS với JD', atsResult.length > 0,
        `Kết quả ATS: "${atsResult.slice(0, 100)}..."`);
    } else {
      record('9. Kiểm tra ATS', false, 'Không tìm thấy nút hoặc ô nhập ATS');
    }

    // BƯỚC 10: Mở Tab Tham khảo & Kiểm tra Tìm mẫu CV tham khảo (References)
    const refTabBtn = page.locator('button[data-act="cv-intel-tab"][data-id="references"]');
    if (await refTabBtn.count()) {
      await refTabBtn.evaluate(el => el.click());
      await page.waitForTimeout(500);
    }
    const refForm = await page.$('#cv-references-form');
    if (refForm) {
      await page.fill('#cv-references-form input[name="company"]', 'Google');
      await page.fill('#cv-references-form input[name="role"]', 'Software Engineer');
      await page.click('#cv-references-form button[type="submit"]');
      await page.waitForTimeout(3000);
      const refList = await page.$$eval('#cv-references-form ~ ul li', els => els.map(e => e.textContent.trim())).catch(() => []);
      record('10. Tìm mẫu CV tham khảo', refList.length > 0, `Số lượng mẫu tìm thấy: ${refList.length}`);
    }

    // BƯỚC 11: Kiểm tra Pop-up Tạo CV bằng AI
    const aiBtn = await page.$('.cv-command-actions button[data-act="cv-generate"]');
    if (aiBtn) {
      await aiBtn.click();
      await page.waitForTimeout(1000);
      const modalTitle = await page.$eval('#dialog-title', el => el.textContent.trim()).catch(() => '');
      const defaultCVSelected = await page.$eval('#dialog select[name="cv-id"]', el => el.value).catch(() => '');
      const modalTip = await page.$eval('#dialog .subtle', el => el.textContent.trim()).catch(() => '');
      record('11. Pop-up Tạo CV bằng AI', modalTitle.includes('Tạo CV'),
        `Tiêu đề Modal: "${modalTitle}", CV đã chọn sẵn: "${defaultCVSelected}", Gợi ý: "${modalTip}"`);
      await page.keyboard.press('Escape');
    }

  } catch (err) {
    record('Lỗi thực thi kiểm thử', false, err.message);
  } finally {
    if (consoleLogs.length) {
      console.log('\n--- Console Errors: ---');
      consoleLogs.forEach(c => console.log('  !', c));
    }
    if (networkErrors.length) {
      console.log('\n--- Network Failures: ---');
      networkErrors.forEach(n => console.log('  !', n.url, n.failure));
    }
    await browser.close();
  }

  console.log('\n--- TỔNG KẾT KẾT QUẢ KIỂM THỬ: ---');
  results.forEach(r => console.log(`[${r.ok ? 'PASS' : 'FAIL'}] ${r.step}`));
}

run();
