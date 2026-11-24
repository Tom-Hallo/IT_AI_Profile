import assert from 'node:assert/strict';
import test from 'node:test';
import { liveCV } from '../src/pixel-studio/live-views.js';
import { setLanguage } from '../src/pixel-studio/i18n.js';

function createCVData(overrides = {}) {
  return {
    cvList: [],
    documentList: [],
    versions: [],
    cv: null,
    document: null,
    scores: [
      { technology: 'Python', score: 85, repo: { full_name: 'org/repo1' } }
    ],
    ats: null,
    atsJD: '',
    references: null,
    referencesQuery: { company: '', role: '' },
    busy: new Set(),
    errors: {},
    messages: {},
    editorMode: 'structured',
    intelTab: 'design',
    zoomLevel: 'fit',
    focusMode: false,
    previewOnly: false,
    rightPanelCollapsed: false,
    ...overrides
  };
}

function createCVRuntime(overrides = {}) {
  return {
    cvDraft: {
      name: 'Nguyen Van A',
      role: 'Fullstack Engineer',
      body: 'KINH NGHIỆM LÀM VIỆC\n2022 - Hiện tại | CÔNG TY X\nKỹ sư phần mềm\n- Phát triển backend FastAPI và React frontend.'
    },
    cvEdited: false,
    mentorOpen: false,
    cvFocusMode: false,
    ...overrides
  };
}

test('CV Studio: Focus Mode activation adds in-focus-mode class and active toolbar state', () => {
  setLanguage('vi');
  const state = { template: 'reference' };
  const runtime = createCVRuntime({ cvFocusMode: true });
  const data = createCVData({ focusMode: true });

  const html = liveCV(state, runtime, data);
  assert.match(html, /class="[^"]*cv-workspace-3col[^"]*in-focus-mode/);
  assert.match(html, /class="button secondary small cv-focus-btn active"/);
  assert.match(html, /Thoát tập trung/);
});

test('CV Studio: Focus Mode deactivation restores normal button label', () => {
  setLanguage('vi');
  const state = { template: 'reference' };
  const runtime = createCVRuntime({ cvFocusMode: false });
  const data = createCVData({ focusMode: false });

  const html = liveCV(state, runtime, data);
  assert.doesNotMatch(html, /in-focus-mode/);
  assert.match(html, /class="button secondary small cv-focus-btn"/);
  assert.match(html, /Tập trung/);
});

test('CV Studio: Preview Only mode toggles single-column preview view', () => {
  const state = { template: 'reference' };
  const runtime = createCVRuntime();
  const data = createCVData({ previewOnly: true });

  const html = liveCV(state, runtime, data);
  assert.match(html, /class="[^"]*cv-workspace-3col[^"]*preview-only/);
  assert.match(html, /class="button secondary small cv-preview-only-btn active"/);
});

test('CV Studio: AI Mentor opening cleanly collapses right tools panel (2-column workspace)', () => {
  const state = { template: 'reference' };
  const runtime = createCVRuntime({ mentorOpen: true });
  const data = createCVData({ rightPanelCollapsed: false });

  const html = liveCV(state, runtime, data);
  assert.match(html, /class="[^"]*cv-workspace-3col[^"]*intel-collapsed/);
  assert.doesNotMatch(html, /intel-explicit-open/);
});

test('CV Studio: Toolbar contains single unified controls without duplicate exports or zoom', () => {
  const state = { template: 'reference' };
  const runtime = createCVRuntime();
  const data = createCVData();

  const html = liveCV(state, runtime, data);
  assert.match(html, /data-act="cv-insert-github"/);
  assert.match(html, /data-act="cv-generate"/);
  assert.match(html, /data-act="cv-toggle-focus"/);
  assert.match(html, /data-act="cv-save-bar"/);
  assert.match(html, /data-act="cv-print"/);
  assert.match(html, /data-act="cv-toggle-intel"/);

  // Bottom exports row under preview must be removed
  assert.doesNotMatch(html, /class="action-row cv-exports"/);
});

test('CV Studio: Structured mode hides permanent raw textarea and shows section builder', () => {
  const state = { template: 'reference' };
  const runtime = createCVRuntime();
  const data = createCVData({ editorMode: 'structured' });

  const html = liveCV(state, runtime, data);
  assert.match(html, /class="cv-mode-tabs"/);
  assert.match(html, /class="button active"[^>]*data-id="structured"/);
  assert.match(html, /class="cv-hidden-raw" style="display:none"/);
});

test('CV Studio: Raw mode displays comfortable multi-line markdown textarea', () => {
  const state = { template: 'reference' };
  const runtime = createCVRuntime();
  const data = createCVData({ editorMode: 'raw' });

  const html = liveCV(state, runtime, data);
  assert.match(html, /class="button active"[^>]*data-id="raw"/);
  assert.match(html, /<textarea name="body"[^>]*rows="20"/);
});

test('CV Studio: Contextual tools panel supports Templates tab with recommended badge', () => {
  const state = { template: 'reference' };
  const runtime = createCVRuntime();
  const data = createCVData({ intelTab: 'templates' });

  const html = liveCV(state, runtime, data);
  assert.match(html, /class="button active"[^>]*data-id="templates"/);
  assert.match(html, /Theo mẫu \(Executive 2 Cột\)/);
  assert.match(html, /★ Recommended/);
  assert.match(html, /Kỹ thuật \(Tech Modern\)/);
  assert.match(html, /Tối giản \(Classic Plain\)/);
});

test('CV Studio: Design tab contains typography standards without duplicate zoom controls', () => {
  const state = { template: 'reference' };
  const runtime = createCVRuntime();
  const data = createCVData({ intelTab: 'design' });

  const html = liveCV(state, runtime, data);
  assert.match(html, /Kiểu chữ & Cỡ chữ chuẩn A4/);
  assert.doesNotMatch(html, /class="cv-zoom-btn-group"/);
});

test('CV Studio: Preserves unsaved draft body and role attributes across rendering', () => {
  const state = { template: 'reference' };
  const customDraft = {
    name: 'Le Thi B',
    role: 'Senior DevOps Architect',
    body: 'KỸ NĂNG\n- Kubernetes, Terraform, AWS, Docker'
  };
  const runtime = createCVRuntime({ cvDraft: customDraft });
  const data = createCVData();

  const html = liveCV(state, runtime, data);
  assert.match(html, /Le Thi B/);
  assert.match(html, /Senior DevOps Architect/);
  assert.match(html, /Kubernetes, Terraform, AWS, Docker/);
});
