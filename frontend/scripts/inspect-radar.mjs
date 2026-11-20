import puppeteer from 'puppeteer-core';
import { execSync } from 'node:child_process';

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sessionToken = execSync(
  'docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"',
  { encoding: 'utf-8' }
).trim();

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

await page.goto('http://localhost:5173/#studio/dashboard');
await new Promise(r => setTimeout(r, 3000));
console.log('Current URL:', page.url());
const title = await page.evaluate(() => document.title);
console.log('Title:', title);

const radarInfo = await page.evaluate(() => {
  const el = document.querySelector('.radar-panel');
  if (!el) return null;
  const header = el.querySelector('.radar-header')?.innerText;
  const indicators = [...el.querySelectorAll('.radar-indicator')].map(b => b.innerText.replace(/\s+/g, ' ').trim());
  const legend = el.querySelector('.radar-legend')?.innerText;
  const caption = el.querySelector('.radar-values p')?.innerText;
  const { x, y, width, height } = el.getBoundingClientRect();
  return {
    header,
    indicators,
    legend,
    caption,
    box: { x, y, width, height }
  };
});

console.log('Radar Info:', JSON.stringify(radarInfo, null, 2));

if (radarInfo?.box) {
  await page.screenshot({
    path: 'C:/Users/ADMIN/.gemini/antigravity/brain/e8e9f772-bac7-49a4-ad90-8635622f9aac/radar-actual-screen.png',
    clip: radarInfo.box
  });
  console.log('Saved screenshot to radar-actual-screen.png');
}

await browser.close();
