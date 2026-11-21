import puppeteer from 'puppeteer-core';
import { execSync } from 'node:child_process';
import path from 'node:path';

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sessionToken = execSync(
  'docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"',
  { encoding: 'utf-8' }
).trim();

const sleep = ms => new Promise(r => setTimeout(r, ms));
const ARTIFACTS_DIR = 'C:/Users/ADMIN/.gemini/antigravity/brain/e8e9f772-bac7-49a4-ad90-8635622f9aac';

async function runJourneys() {
  console.log('=== BẮT ĐẦU ĐÁNH GIÁ 6 HÀNH TRÌNH FIRST-TIME DEVELOPER ===');
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

  const results = {};

  // ==========================================
  // HÀNH TRÌNH 1: KẾT NỐI, CHỌN REPO, KHOẢNG THỜI GIAN, PHÂN TÍCH, THEO DÕI TIẾN ĐỘ, MỞ BÁO CÁO
  // ==========================================
  console.log('\n>>> HÀNH TRÌNH 1: Bắt đầu từ trang chủ và vào phân tích repo...');
  await page.goto('http://localhost:5173/');
  await sleep(1500);

  // Xem landing page có nút chuyển vào Studio / Repos không
  const homeButtons = await page.evaluate(() => {
    return [...document.querySelectorAll('a, button')].map(b => ({
      text: b.innerText.trim(),
      href: b.getAttribute('href'),
      act: b.getAttribute('data-act')
    })).filter(b => b.text);
  });
  console.log('Home buttons:', homeButtons.slice(0, 8));

  // Điều hướng vào #studio/repos
  await page.goto('http://localhost:5173/#studio/repos');
  await sleep(2000);

  // Kiểm tra repo đang chọn, bộ lọc thời gian và nút phân tích
  const journey1State = await page.evaluate(() => {
    const banner = document.querySelector('.repo-context-banner')?.innerText?.replace(/\s+/g, ' ').trim();
    const rangeValue = document.querySelector('.analysis-toolbar .filter-value')?.innerText;
    const analyzeBtn = document.querySelector('button[data-act="analyze"]');
    const selectedRepo = document.querySelector('.repo-card.selected strong')?.innerText;
    return { banner, rangeValue, analyzeBtnText: analyzeBtn?.innerText, selectedRepo };
  });
  console.log('Journey 1 Initial Repos State:', journey1State);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'journey1-repos-selection.png') });
  results.journey1 = { ...journey1State };

  // ==========================================
  // HÀNH TRÌNH 2: ĐỌC BÁO CÁO, TÌM PHÁT HIỆN QUAN TRỌNG NHẤT, MỞ BẰNG CHỨNG
  // ==========================================
  console.log('\n>>> HÀNH TRÌNH 2: Đọc báo cáo Repo A (ID 81 - Tom-Hallo/IT_AI_Profile)...');
  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="81"]');
    if (btn) btn.click();
  });
  await sleep(2000);

  const reportDetails = await page.evaluate(() => {
    const highlights = document.querySelector('.repo-highlights-card')?.innerText?.replace(/\s+/g, ' ').trim();
    const tabs = [...document.querySelectorAll('.tab-strip button')].map(b => ({ id: b.dataset.id, text: b.innerText.trim(), active: b.classList.contains('active') }));
    const activeContent = document.querySelector('.report-detail')?.innerText?.replace(/\s+/g, ' ').trim()?.slice(0, 300);
    return { highlights, tabs, activeContent };
  });
  console.log('Journey 2 Report Highlights & Tabs:', reportDetails);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'journey2-report-overview.png') });

  // Thử chuyển qua các tab báo cáo: Kiến trúc, Kiểm thử, Đóng góp
  for (const tabId of ['architecture', 'tests', 'collab', 'ownership']) {
    await page.evaluate((tid) => {
      const btn = document.querySelector(`.tab-strip button[data-id="${tid}"]`);
      if (btn) btn.click();
    }, tabId);
    await sleep(800);
  }
  const evidenceCheck = await page.evaluate(() => {
    const evidenceItems = [...document.querySelectorAll('.report-detail a, .report-detail button')].map(b => b.innerText.trim());
    return { evidenceCount: evidenceItems.length, sampleEvidence: evidenceItems.slice(0, 5) };
  });
  console.log('Journey 2 Evidence Check:', evidenceCheck);
  results.journey2 = { reportDetails, evidenceCheck };

  // ==========================================
  // HÀNH TRÌNH 3: MỞ SKILL DASHBOARD, ĐỔI A -> B -> A
  // ==========================================
  console.log('\n>>> HÀNH TRÌNH 3: Skill Dashboard A -> B -> A...');
  await page.goto('http://localhost:5173/#studio/dashboard');
  await sleep(2000);

  const dashInfoA = await page.evaluate(() => {
    const banner = document.querySelector('.dashboard-scope-banner')?.innerText?.replace(/\s+/g, ' ').trim();
    const radarTitle = document.querySelector('.radar-header h2')?.innerText;
    const scores = [...document.querySelectorAll('.radar-indicator')].map(b => b.innerText.replace(/\s+/g, ' ').trim());
    return { banner, radarTitle, scores };
  });
  console.log('Journey 3 Dashboard with Repo A:', dashInfoA);

  // Đổi sang Repo B (83)
  await page.goto('http://localhost:5173/#studio/repos');
  await sleep(1000);
  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="83"]');
    if (btn) btn.click();
  });
  await sleep(1500);
  await page.goto('http://localhost:5173/#studio/dashboard');
  await sleep(2000);

  const dashInfoB = await page.evaluate(() => {
    const banner = document.querySelector('.dashboard-scope-banner')?.innerText?.replace(/\s+/g, ' ').trim();
    const scores = [...document.querySelectorAll('.radar-indicator')].map(b => b.innerText.replace(/\s+/g, ' ').trim());
    return { banner, scores };
  });
  console.log('Journey 3 Dashboard with Repo B:', dashInfoB);

  // Đổi lại Repo A (81)
  await page.goto('http://localhost:5173/#studio/repos');
  await sleep(1000);
  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="81"]');
    if (btn) btn.click();
  });
  await sleep(1500);
  await page.goto('http://localhost:5173/#studio/dashboard');
  await sleep(2000);
  results.journey3 = { dashInfoA, dashInfoB };

  // ==========================================
  // HÀNH TRÌNH 4: AI MENTOR
  // ==========================================
  console.log('\n>>> HÀNH TRÌNH 4: Hỏi AI Mentor với Repo A và B...');
  // Mở mentor
  await page.evaluate(() => {
    const mentorBtn = document.querySelector('button[data-act="mentor"]');
    if (mentorBtn) mentorBtn.click();
  });
  await sleep(1500);

  // Gõ câu hỏi: "Dựa vào repo này, tôi nên cải thiện kỹ năng nào trước và vì sao?"
  const question = "Dựa vào repo này, tôi nên cải thiện kỹ năng nào trước và vì sao?";
  console.log('Asking question to AI Mentor:', question);
  await page.evaluate((q) => {
    const input = document.querySelector('.mentor-input input, textarea[name="chat"]');
    if (input) {
      input.value = q;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    const form = document.querySelector('.mentor-form, form');
    if (form) {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    }
  }, question);

  // Chờ câu trả lời của AI Mentor (tối đa 25s)
  console.log('Waiting for AI Mentor response...');
  let mentorReply = null;
  for (let i = 0; i < 25; i++) {
    await sleep(1000);
    mentorReply = await page.evaluate(() => {
      const messages = [...document.querySelectorAll('.mentor-message.agent, .message.agent')];
      if (!messages.length) return null;
      const last = messages[messages.length - 1];
      return {
        text: last.innerText.replace(/\s+/g, ' ').trim(),
        evidence: [...last.querySelectorAll('button, a')].map(b => b.innerText.trim())
      };
    });
    if (mentorReply?.text && !mentorReply.text.includes('Đang suy nghĩ')) {
      break;
    }
  }
  console.log('AI Mentor Reply for Repo A:', mentorReply);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'journey4-mentor-repoA.png') });
  results.journey4 = { question, mentorReply };

  // ==========================================
  // HÀNH TRÌNH 5: MỞ ROADMAP VÀ THEO DÕI TIẾN ĐỘ
  // ==========================================
  console.log('\n>>> HÀNH TRÌNH 5: Kiểm tra Lộ trình (Roadmap)...');
  await page.goto('http://localhost:5173/#studio/roadmap');
  await sleep(2500);

  const roadInfo = await page.evaluate(() => {
    const heading = document.querySelector('.road-banner h2')?.innerText;
    const progressText = document.querySelector('.road-progress')?.innerText?.replace(/\s+/g, ' ').trim();
    const milestones = [...document.querySelectorAll('.milestone-card, .road-step')].map(m => m.innerText.replace(/\s+/g, ' ').trim().slice(0, 100));
    const checkbox = document.querySelector('input[type="checkbox"].road-check, button[data-act="step-done"]');
    return { heading, progressText, milestonesCount: milestones.length, sampleMilestones: milestones.slice(0, 3), hasCheckbox: Boolean(checkbox) };
  });
  console.log('Roadmap Info:', roadInfo);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'journey5-roadmap.png') });
  results.journey5 = roadInfo;

  // ==========================================
  // HÀNH TRÌNH 6: REPO CHƯA PHÂN TÍCH VÀ CA JOB LỖI / CHỜ
  // ==========================================
  console.log('\n>>> HÀNH TRÌNH 6: Repo chưa phân tích (ID 82 - Collabbb-together)...');
  await page.goto('http://localhost:5173/#studio/repos');
  await sleep(1500);
  await page.evaluate(() => {
    const btn = document.querySelector('button[data-act="repo"][data-id="82"]');
    if (btn) btn.click();
  });
  await sleep(1500);

  const unanalyzedState = await page.evaluate(() => {
    const banner = document.querySelector('.repo-context-banner')?.innerText?.replace(/\s+/g, ' ').trim();
    const reportPanel = document.querySelector('.report-panel, .repo-main')?.innerText?.replace(/\s+/g, ' ').trim()?.slice(0, 300);
    const analyzeBtn = document.querySelector('button[data-act="analyze"]')?.innerText;
    return { banner, reportPanel, analyzeBtn };
  });
  console.log('Journey 6 Unanalyzed Repo State:', unanalyzedState);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'journey6-unanalyzed-repo.png') });
  results.journey6 = unanalyzedState;

  await browser.close();
  console.log('\n=== HOÀN TẤT THỰC NGHIỆM 6 HÀNH TRÌNH ===');
  console.log(JSON.stringify(results, null, 2));
}
runJourneys();
