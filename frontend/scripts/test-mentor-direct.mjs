import puppeteer from 'puppeteer-core';
import { execSync } from 'node:child_process';

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sessionToken = execSync(
  'docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"',
  { encoding: 'utf-8' }
).trim();

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function testMentor() {
  console.log('=== TEST TRỰC TIẾP AI MENTOR ===');
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.type(), msg.text()));
  page.on('response', async res => {
    if (res.url().includes('/api/v1/mentor/chat')) {
      console.log('MENTOR RESPONSE STATUS:', res.status());
      const body = await res.text().catch(() => '');
      console.log('MENTOR RESPONSE BODY:', body.slice(0, 500));
    }
  });

  await page.setCookie({
    name: 'ita_session',
    value: sessionToken,
    domain: 'localhost',
    path: '/',
    httpOnly: false,
    secure: false,
    sameSite: 'Lax',
  });

  await page.goto('http://localhost:5173/#studio/repos');
  await sleep(2000);

  // Click toggle mentor
  console.log('Clicking mentor toggle...');
  await page.evaluate(() => {
    const btn = document.querySelector('#mentor-toggle, button[data-act="toggle-mentor"]');
    if (btn) btn.click();
  });
  await sleep(1500);

  const panelVisible = await page.evaluate(() => {
    const p = document.querySelector('#mentor-panel');
    return p ? !p.hidden : false;
  });
  console.log('Mentor panel visible:', panelVisible);

  // Type question
  const question = "Dựa vào repo này, tôi nên cải thiện kỹ năng nào trước và vì sao?";
  console.log('Typing question in #mentor-question:', question);
  await page.evaluate((q) => {
    const input = document.querySelector('#mentor-question');
    if (input) {
      input.value = q;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }, question);

  // Submit form
  console.log('Submitting chat form...');
  await page.evaluate(() => {
    const form = document.querySelector('.chat-form');
    if (form) {
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.click();
      else form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    }
  });

  console.log('Waiting for AI Mentor response (up to 30s)...');
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    const messages = await page.evaluate(() => {
      return [...document.querySelectorAll('.mentor-message')].map(m => ({
        cls: m.className,
        text: m.innerText.replace(/\s+/g, ' ').trim()
      }));
    });
    if (messages.length > 1) {
      console.log(`Received messages (${messages.length}):`, JSON.stringify(messages, null, 2));
      break;
    }
  }

  await page.screenshot({ path: 'C:/Users/ADMIN/.gemini/antigravity/brain/e8e9f772-bac7-49a4-ad90-8635622f9aac/mentor-direct-result.png' });
  await browser.close();
}
testMentor();
