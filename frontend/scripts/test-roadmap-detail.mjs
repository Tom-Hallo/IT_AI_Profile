import puppeteer from 'puppeteer-core';
import { execSync } from 'node:child_process';

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sessionToken = execSync(
  'docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"',
  { encoding: 'utf-8' }
).trim();

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function testRoadmap() {
  console.log('=== TEST TRỰC TIẾP ROADMAP ===');
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

  await page.goto('http://localhost:5173/#studio/roadmap');
  await sleep(2500);

  const initial = await page.evaluate(() => {
    const heading = document.querySelector('.road-banner h2')?.innerText;
    const progressText = document.querySelector('.road-progress')?.innerText?.replace(/\s+/g, ' ').trim();
    const nodes = [...document.querySelectorAll('button.node[data-act="milestone"]')].map(n => ({
      id: n.dataset.id,
      title: n.querySelector('strong')?.innerText,
      state: n.getAttribute('state')
    }));
    const detail = document.querySelector('#milestone-detail')?.innerText?.replace(/\s+/g, ' ').trim();
    const statusBtns = [...document.querySelectorAll('#milestone-detail button[data-act="road-status"]')].map(b => ({
      text: b.innerText.trim(),
      status: b.dataset.status
    }));
    return { heading, progressText, nodes, detail, statusBtns };
  });
  console.log('Initial Roadmap State:', JSON.stringify(initial, null, 2));

  // Thử bấm một nút đổi trạng thái (ví dụ: chuyển sang 'completed' hoặc 'in_progress')
  if (initial.statusBtns?.length) {
    const targetBtn = initial.statusBtns[0];
    console.log(`Clicking status button: ${targetBtn.text} (${targetBtn.status})...`);
    await page.evaluate((targetStatus) => {
      const btn = document.querySelector(`#milestone-detail button[data-act="road-status"][data-status="${targetStatus}"]`);
      if (btn) btn.click();
    }, targetBtn.status);
    await sleep(2000);

    // Kiểm tra sau khi bấm
    const afterClick = await page.evaluate(() => {
      const progressText = document.querySelector('.road-progress')?.innerText?.replace(/\s+/g, ' ').trim();
      const nodes = [...document.querySelectorAll('button.node[data-act="milestone"]')].map(n => ({
        id: n.dataset.id,
        title: n.querySelector('strong')?.innerText,
        state: n.getAttribute('state')
      }));
      return { progressText, nodes };
    });
    console.log('After status click:', afterClick);

    // Tải lại trang kiểm tra persistence
    console.log('Reloading page to verify persistence...');
    await page.reload();
    await sleep(2500);

    const afterReload = await page.evaluate(() => {
      const progressText = document.querySelector('.road-progress')?.innerText?.replace(/\s+/g, ' ').trim();
      const nodes = [...document.querySelectorAll('button.node[data-act="milestone"]')].map(n => ({
        id: n.dataset.id,
        title: n.querySelector('strong')?.innerText,
        state: n.getAttribute('state')
      }));
      return { progressText, nodes };
    });
    console.log('After reload:', afterReload);
  }

  await page.screenshot({ path: 'C:/Users/ADMIN/.gemini/antigravity/brain/e8e9f772-bac7-49a4-ad90-8635622f9aac/roadmap-verified.png' });
  await browser.close();
  console.log('=== ROADMAP TEST XONG ===');
}
testRoadmap();
