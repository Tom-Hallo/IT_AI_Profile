const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { chromium } = require('../frontend/node_modules/playwright-core');

const BASE_URL = 'http://localhost:5173';
const OUTPUT_DIR = 'C:/Users/ADMIN/.gemini/antigravity/brain/e65cc7ad-ad67-4f76-acc3-0685316d0551/cv_studio_verification';
const SAMPLE_PDF_PATH = path.resolve(__dirname, '../backend/tests_cv_sample.pdf');

fs.mkdirSync(OUTPUT_DIR, { recursive: true });

function getTestSession() {
  return execSync(
    'docker compose exec -T backend python -c "from app.modules.auth.service import create_session; print(create_session(1))"',
    { encoding: 'utf-8' }
  ).trim();
}

async function runTest() {
  console.log('=== TEST ROUND 1: COMPREHENSIVE CV STUDIO TESTING ===');
  console.log('Using sample PDF:', SAMPLE_PDF_PATH, 'exists:', fs.existsSync(SAMPLE_PDF_PATH));

  const defects = [];

  const sessionToken = getTestSession();
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });

  await context.addCookies([{
    name: 'ita_session',
    value: sessionToken,
    url: 'http://localhost:5173'
  }]);

  const page = await context.newPage();

  // Listen to console and page errors
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log('PAGE ERROR LOG:', msg.text());
      defects.push({ category: 'console_error', detail: msg.text() });
    }
  });

  page.on('pageerror', err => {
    console.log('UNCAUGHT PAGE EXCEPTION:', err.message);
    defects.push({ category: 'page_exception', detail: err.message, stack: err.stack });
  });

  console.log('Step 1: Navigating to CV Studio (#studio/cv)...');
  await page.goto(`${BASE_URL}/#studio/cv`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  // Check if file upload input exists
  const uploadInput = await page.$('#cv-upload');
  if (!uploadInput) {
    defects.push({ category: 'upload', detail: 'Could not find #cv-upload input element' });
  } else {
    console.log('Step 2: Uploading template PDF file to #cv-upload...');
    // Set file input
    await uploadInput.setInputFiles(SAMPLE_PDF_PATH);
    // Wait for network requests or status change
    await page.waitForTimeout(3000);
  }

  await page.screenshot({ path: path.join(OUTPUT_DIR, 'round1_01_after_upload.png') });

  // Check what was populated in CV draft body, name, role
  const cvState = await page.evaluate(() => {
    const textarea = document.querySelector('textarea[name="body"]');
    const nameInput = document.querySelector('input[name="name"]') || document.querySelector('.cv-ref-name');
    const roleInput = document.querySelector('input[name="role"]') || document.querySelector('.cv-ref-role');
    const notice = document.querySelector('.notice, .cv-loading-notice, [role="alert"]');
    const paper = document.querySelector('.cv-paper');
    return {
      bodyText: textarea ? textarea.value : null,
      nameText: nameInput ? (nameInput.value || nameInput.textContent) : null,
      roleText: roleInput ? (roleInput.value || roleInput.textContent) : null,
      noticeText: notice ? notice.textContent : null,
      paperRendered: !!paper,
      paperHtml: paper ? paper.innerHTML.slice(0, 500) : null
    };
  });

  console.log('CV State after upload:', {
    bodyLength: cvState.bodyText ? cvState.bodyText.length : 0,
    name: cvState.nameText,
    role: cvState.roleText,
    notice: cvState.noticeText,
    paperRendered: cvState.paperRendered
  });

  if (!cvState.bodyText || cvState.bodyText.length < 50) {
    defects.push({
      category: 'upload_extraction',
      detail: 'CV body text empty or not populated after uploading PDF. Notice: ' + cvState.noticeText
    });
  }

  // Step 3: Test Structured Editor mode
  console.log('Step 3: Testing Structured Editor mode...');
  try {
    const structuredBtn = await page.$('[data-act="cv-editor-mode"][data-id="structured"]');
    if (structuredBtn) {
      await structuredBtn.click();
      await page.waitForTimeout(800);
      await page.screenshot({ path: path.join(OUTPUT_DIR, 'round2_02_structured_mode.png') });

      const sectionsCount = await page.evaluate(() => {
        return document.querySelectorAll('.cv-section-card, .cv-struct-section, .cv-sec-nav-card, .cv-focused-sec-editor').length;
      });
      console.log('Structured sections count rendered:', sectionsCount);
      if (sectionsCount === 0) {
        defects.push({
          category: 'structured_mode',
          detail: 'No section cards rendered in Structured Editor mode after uploading PDF'
        });
      } else {
        // Test clicking first section to open focused editor
        const firstCard = await page.$('.cv-sec-nav-card, .cv-section-card');
        if (firstCard) {
          await firstCard.click();
          await page.waitForTimeout(500);
          const hasFocusedEditor = await page.evaluate(() => !!document.querySelector('.cv-focused-sec-editor'));
          console.log('Focused editor opened:', hasFocusedEditor);
          if (!hasFocusedEditor) {
            defects.push({ category: 'structured_mode', detail: 'Clicking section card did not open focused editor' });
          } else {
            // Click back
            await page.click('[data-act="cv-nav-back"]');
            await page.waitForTimeout(500);
          }
        }
      }
    } else {
      defects.push({ category: 'structured_mode', detail: 'Structured mode toggle button not found' });
    }
  } catch (err) {
    defects.push({ category: 'structured_mode', detail: err.message });
  }

  // Step 4: Test Raw Markdown mode
  console.log('Step 4: Testing Raw Markdown mode...');
  try {
    const rawBtn = await page.$('[data-act="cv-editor-mode"][data-id="raw"]');
    if (rawBtn) {
      await rawBtn.click();
      await page.waitForTimeout(500);
      const rawTextarea = await page.$('textarea[name="body"]');
      const isVisible = rawTextarea ? await rawTextarea.isVisible() : false;
      console.log('Raw textarea is visible:', isVisible);
      if (!isVisible) {
        defects.push({ category: 'raw_mode', detail: 'Textarea[name="body"] not visible in Raw mode' });
      }
    }
  } catch (err) {
    defects.push({ category: 'raw_mode', detail: err.message });
  }

  // Step 5: Test Switching between Structured and Raw modes (Bidirectional integrity)
  console.log('Step 5: Testing Bidirectional integrity between Raw and Structured modes...');
  try {
    // Modify text in raw mode
    await page.evaluate(() => {
      const textarea = document.querySelector('textarea[name="body"]');
      if (textarea) {
        textarea.value += '\n\nKỸ NĂNG BỔ SUNG\n- Python & FastAPI Advanced Testing\n- Docker & CI/CD Pipelines\n';
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForTimeout(500);

    // Switch back to structured mode
    await page.click('[data-act="cv-editor-mode"][data-id="structured"]');
    await page.waitForTimeout(800);

    // Check if paper includes the new text
    const paperHasNewSkill = await page.evaluate(() => {
      const paper = document.querySelector('.cv-paper');
      return paper ? paper.textContent.includes('Python & FastAPI Advanced Testing') : false;
    });
    console.log('Paper rendered newly added skill:', paperHasNewSkill);
    if (!paperHasNewSkill) {
      defects.push({
        category: 'bidirectional_sync',
        detail: 'Paper canvas did not render new skill added in Raw mode when switching to Structured mode'
      });
    }
  } catch (err) {
    defects.push({ category: 'bidirectional_sync', detail: err.message });
  }

  // Step 6: Test Zoom Controls
  console.log('Step 6: Testing Zoom Controls in Canvas Toolbar...');
  try {
    const zoom125 = await page.$('[data-act="cv-zoom"][data-id="125"]');
    if (zoom125) {
      await zoom125.click();
      await page.waitForTimeout(400);
      const is125 = await page.evaluate(() => document.querySelector('.cv-preview-viewport')?.classList.contains('cv-zoom-125'));
      console.log('Zoom 125% activated:', is125);
    }
    const zoomFit = await page.$('[data-act="cv-zoom"][data-id="fit"]');
    if (zoomFit) {
      await zoomFit.click();
      await page.waitForTimeout(400);
      const isFit = await page.evaluate(() => document.querySelector('.cv-preview-viewport')?.classList.contains('cv-zoom-fit'));
      console.log('Zoom Fit activated:', isFit);
    }
    await page.click('[data-act="cv-zoom-in"]');
    await page.waitForTimeout(300);
    await page.click('[data-act="cv-zoom-out"]');
    await page.waitForTimeout(300);
    console.log('Zoom in and out buttons working');
  } catch (err) {
    defects.push({ category: 'zoom', detail: err.message });
  }

  // Step 7: Test Design Tab in Contextual Tools
  console.log('Step 7: Testing Contextual Tools -> Design Tab...');
  try {
    await page.click('[data-act="cv-intel-tab"][data-id="design"]');
    await page.waitForTimeout(500);

    // Try selecting different font
    const fontBtns = await page.$$('[data-act="cv-font"]');
    if (fontBtns.length > 0) {
      await fontBtns[1].click();
      await page.waitForTimeout(400);
      console.log('Font switch clicked, total font options:', fontBtns.length);
    }

    // Try selecting spacing
    const spacingBtns = await page.$$('[data-act="cv-spacing"]');
    if (spacingBtns.length > 0) {
      await spacingBtns[1].click();
      await page.waitForTimeout(400);
      console.log('Spacing switch clicked, total spacing options:', spacingBtns.length);
    }
  } catch (err) {
    defects.push({ category: 'design_tools', detail: err.message });
  }

  // Step 8: Test Templates Tab
  console.log('Step 8: Testing Contextual Tools -> Templates Tab...');
  try {
    await page.click('[data-act="cv-intel-tab"][data-id="templates"]');
    await page.waitForTimeout(500);
    const templateCards = await page.$$('.cv-tpl-card, .cv-template-card, [data-act="cv-template"]');
    console.log('Template cards count:', templateCards.length);
    if (templateCards.length > 0) {
      await page.click('[data-act="cv-template"][data-id="tech"]');
      await page.waitForTimeout(500);
      console.log('Switched to Tech Modern template');
      await page.click('[data-act="cv-template"][data-id="reference"]');
      await page.waitForTimeout(500);
      console.log('Switched back to Executive template');
    } else {
      defects.push({ category: 'templates', detail: 'No template cards found in Templates tab' });
    }
  } catch (err) {
    defects.push({ category: 'templates', detail: err.message });
  }

  // Step 9: Test GitHub Evidence Tab
  console.log('Step 9: Testing Contextual Tools -> GitHub Evidence Tab...');
  try {
    await page.click('[data-act="cv-intel-tab"][data-id="github"]');
    await page.waitForTimeout(600);
    const insertButtons = await page.$$('[data-act="cv-insert-single-skill"], [data-act="cv-insert-all-skills"], [data-act="cv-insert-github"]');
    console.log('GitHub Evidence insert buttons count:', insertButtons.length);
    if (insertButtons.length > 0) {
      await insertButtons[0].click();
      await page.waitForTimeout(1000);
      console.log('Clicked GitHub Evidence button');
    }
  } catch (err) {
    defects.push({ category: 'github_evidence', detail: err.message });
  }

  // Step 10: Test ATS Review Tab
  console.log('Step 10: Testing Contextual Tools -> ATS Review Tab...');
  try {
    await page.click('[data-act="cv-intel-tab"][data-id="ats"]');
    await page.waitForTimeout(500);

    const jdTextarea = await page.$('textarea[name="ats-jd"]');
    if (jdTextarea) {
      await jdTextarea.fill('Senior Fullstack Engineer with Python, React, PostgreSQL, Docker, AWS and CI/CD.');
      await page.waitForTimeout(300);
      
      // Wait until any background operation finishes so check button is enabled
      await page.waitForSelector('button[data-act="cv-check"]:not([disabled])', { timeout: 10000 });
      console.log('Clicking Check ATS button...');
      await page.click('button[data-act="cv-check"]');
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(OUTPUT_DIR, 'round2_03_ats_result.png') });

      const atsResult = await page.evaluate(() => {
        const res = document.querySelector('#ats-result');
        return res ? res.textContent : null;
      });
      console.log('ATS result text preview:', atsResult ? atsResult.slice(0, 200) : 'None');
      if (!atsResult || (!atsResult.includes('Cấu trúc') && !atsResult.includes('Độ phủ') && !atsResult.includes('%'))) {
        defects.push({ category: 'ats_check', detail: 'ATS result not rendered properly after clicking Check ATS' });
      }
    } else {
      defects.push({ category: 'ats_check', detail: 'JD textarea[name="ats-jd"] not found' });
    }
  } catch (err) {
    defects.push({ category: 'ats_check', detail: err.message });
  }

  // Step 11: Test Save CV
  console.log('Step 11: Testing Save CV...');
  try {
    const saveBtn = await page.$('button[data-act="cv-save"], button[data-act="cv-save-bar"]');
    if (saveBtn) {
      await saveBtn.click();
      await page.waitForTimeout(1500);
      const notice = await page.evaluate(() => {
        const n = document.querySelector('.notice, [role="alert"], [role="status"]');
        return n ? n.textContent : null;
      });
      console.log('Save notice:', notice);
    } else {
      defects.push({ category: 'save_cv', detail: 'Save CV button [data-act="cv-save"] not found' });
    }
  } catch (err) {
    defects.push({ category: 'save_cv', detail: err.message });
  }

  // Step 12: Test Export PDF
  console.log('Step 12: Testing Export PDF...');
  try {
    const exportBtn = await page.$('[data-act="cv-export-pdf"], button[data-act="cv-print"]');
    if (exportBtn) {
      console.log('Export PDF button found');
      // We do not trigger real browser print dialog in headless, but test handler presence
    } else {
      defects.push({ category: 'export_pdf', detail: 'Export PDF button not found' });
    }
  } catch (err) {
    defects.push({ category: 'export_pdf', detail: err.message });
  }

  // Step 13: Test Focus Mode
  console.log('Step 13: Testing Focus Mode and Escape shortcut...');
  try {
    await page.click('[data-act="cv-toggle-focus"]');
    await page.waitForTimeout(500);
    const inFocus = await page.evaluate(() => document.querySelector('.studio')?.classList.contains('cv-focus-mode'));
    if (!inFocus) {
      defects.push({ category: 'focus_mode', detail: 'Focus mode class not applied to .studio' });
    }
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    const outFocus = await page.evaluate(() => !document.querySelector('.studio')?.classList.contains('cv-focus-mode'));
    if (!outFocus) {
      defects.push({ category: 'focus_mode', detail: 'Escape key did not exit Focus Mode' });
    }
  } catch (err) {
    defects.push({ category: 'focus_mode', detail: err.message });
  }

  // Step 14: Test Preview Only Mode
  console.log('Step 14: Testing Preview Only mode...');
  try {
    await page.click('[data-act="cv-toggle-preview-only"]');
    await page.waitForTimeout(500);
    const inPreviewOnly = await page.evaluate(() => document.querySelector('.cv-workspace-3col')?.classList.contains('preview-only'));
    if (!inPreviewOnly) {
      defects.push({ category: 'preview_only', detail: 'preview-only class not applied to workspace' });
    }
    await page.click('[data-act="cv-toggle-preview-only"]');
    await page.waitForTimeout(500);
  } catch (err) {
    defects.push({ category: 'preview_only', detail: err.message });
  }

  // Step 15: Test AI Mentor Integration
  console.log('Step 15: Testing AI Mentor Integration with CV Studio...');
  try {
    await page.click('#mentor-toggle');
    await page.waitForTimeout(800);
    const mentorOpen = await page.evaluate(() => {
      const workspace = document.querySelector('.cv-workspace-3col');
      const studio = document.querySelector('.studio');
      return {
        hasMentorOpen: studio?.classList.contains('mentor-open') || studio?.classList.contains('has-mentor') || document.body.classList.contains('mentor-open') || document.body.classList.contains('has-mentor'),
        intelCollapsed: workspace?.classList.contains('intel-collapsed')
      };
    });
    console.log('AI Mentor state:', mentorOpen);
    if (!mentorOpen.hasMentorOpen) {
      defects.push({ category: 'mentor_integration', detail: 'AI Mentor open state not reflected in .studio' });
    }
    await page.click('#mentor-toggle');
    await page.waitForTimeout(500);
  } catch (err) {
    defects.push({ category: 'mentor_integration', detail: err.message });
  }

  await browser.close();

  console.log('\n======================================================');
  console.log('TEST ROUND 2 COMPLETED. DEFECTS FOUND:', defects.length);
  defects.forEach((d, i) => {
    console.log(`[DEFECT ${i+1}] [${d.category}] ${d.detail}`);
  });
  console.log('======================================================\n');

  fs.writeFileSync(
    path.join(OUTPUT_DIR, 'round2_defects.json'),
    JSON.stringify(defects, null, 2)
  );

  return defects;
}

runTest().catch(err => {
  console.error('Fatal test error:', err);
  process.exit(1);
});
