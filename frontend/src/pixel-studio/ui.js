import {getLanguage, rangeLabel, scopeLabel, t} from './i18n.js';
import {ranges, scopes} from './data.js';
import {codeReference, codeReferenceLabel} from './evidence.js';
import {botPalette, presets} from './theme.js';

export const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
export const icon = (name, extra='') => '<span aria-hidden="true" class="icon i-' + name + ' ' + extra + '"></span>';
export const bot = (css='', mood='idle') => '<canvas class="bot-sprite ' + css + '" data-bot-mood="' + mood + '" width="24" height="24" aria-hidden="true"></canvas>';
export const attr = (name,value) => ' data-' + name + '="' + escape(value) + '"';
export const labelAttr = text => ' aria-label="' + escape(text) + '"';
export const badge = (label,tone='') => '<span class="badge ' + tone + '">' + escape(label) + '</span>';
export const btn = (label,act,style='secondary',attributes='') => '<button class="button ' + style + '" type="button" data-act="' + act + '" ' + attributes + '>' + label + '</button>';
export const heading = (title,copy,actions='') => '<header class="page-heading"><div><h1>' + escape(title) + '</h1><p>' + escape(copy) + '</p></div>' + (actions ? '<div class="action-row">' + actions + '</div>' : '') + '</header>';
export const blank = (title,copy,action='') => '<div class="empty"><h3>' + escape(title) + '</h3><p>' + escape(copy) + '</p>' + action + '</div>';
export const progress = (value,label) => '<progress max="100" value="' + Number(value) + '"' + labelAttr(label) + '></progress>';
export const option = (value,label,selected) => '<option value="' + escape(value) + '"' + (value === selected ? ' selected' : '') + '>' + escape(label) + '</option>';
export const field = (label,control) => '<label class="field"><span>' + escape(label) + '</span>' + control + '</label>';
export const link = (label,page,style='secondary') => '<a class="button ' + style + '" href="#studio/' + page + '">' + label + '</a>';
export const panelHead = (title,copy='') => '<header class="panel-head"><div><h2>' + escape(title) + '</h2>' + (copy ? '<p class="subtle">' + escape(copy) + '</p>' : '') + '</div></header>';
export const tags = (items,tone='') => '<div class="badge-list">' + items.map(item => badge(item,tone)).join('') + '</div>';
export function formatSkillName(key) {
  const clean = String(key || '').trim().toLowerCase();
  const map = {
    python: 'Python', typescript: 'TypeScript', javascript: 'JavaScript', java: 'Java',
    golang: 'Go', rust: 'Rust', csharp: 'C#', cpp: 'C++', c: 'C', php: 'PHP', kotlin: 'Kotlin',
    swift: 'Swift', sql: 'SQL', fastapi: 'FastAPI', django: 'Django', flask: 'Flask',
    nodejs: 'Node.js', express: 'Express.js', nestjs: 'NestJS', springboot: 'Spring Boot',
    react: 'React', vue: 'Vue.js', nextjs: 'Next.js', angular: 'Angular', tailwind: 'Tailwind CSS',
    postgresql: 'PostgreSQL', mysql: 'MySQL', mongodb: 'MongoDB', redis: 'Redis',
    elasticsearch: 'Elasticsearch', sqlite: 'SQLite', docker: 'Docker', kubernetes: 'Kubernetes',
    aws: 'AWS', gcp: 'GCP', azure: 'Azure', cicd: 'CI/CD', git: 'Git', terraform: 'Terraform',
    linux: 'Linux', rest_api: 'REST API', graphql: 'GraphQL', microservices: 'Microservices',
    unit_testing: 'Unit Testing', agile_scrum: 'Agile/Scrum', android: 'Android', apache: 'Apache',
    data_science: 'Data Science', net: '.NET'
  };
  return map[clean] || clean.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
export const details = rows => '<dl class="detail-list">' + rows.map(([name,html]) => '<div><dt>' + escape(name) + '</dt><dd>' + html + '</dd></div>').join('') + '</dl>';
export const checkRow = (label,name,checked=false) => '<label class="option-row"><input type="checkbox" name="' + name + '"' + (checked ? ' checked' : '') + '><span>' + escape(label) + '</span></label>';

export const pages = [
  ['dashboard','grid'],['repos','repo'],['roadmap','branch'],['jobs','job'],
  ['cv','file'],['data','lock'],['status','pulse']
];

export function brand(inStudio=false) {
  const destination = inStudio ? '#studio/dashboard' : '#about';
  return '<a class="brand" href="' + destination + '"' + labelAttr('IT Talent AI Profile · ' + t(inStudio ? 'nav.dashboard' : 'nav.about'))
    + '><span class="brand-symbol" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span>IT Talent<span class="brand-sub">AI PROFILE</span></span></a>';
}

export function languagePicker() {
  const buttons = [['vi','VI','Tiếng Việt'],['en','EN','English']].map(([locale,label,name]) =>
    '<button type="button" data-act="language" lang="' + locale + '"' + attr('id',locale) + labelAttr(name)
    + ' aria-pressed="' + (locale === getLanguage()) + '">' + label + '</button>').join('');
  return '<div class="language-picker" role="group"' + labelAttr(t('language')) + '>' + buttons + '</div>';
}

export function codeBlock(repo, selected=false) {
  const reference = codeReference(repo);
  return '<figure id="repo-evidence" class="code-block' + (selected ? ' active-evidence' : '') + '" tabindex="-1">'
    + '<figcaption class="code-file"><div class="code-file-title">' + icon('file') + '<div><strong>' + escape(repo.file)
    + '</strong><small>' + escape(t('repos.codeLines',reference) + ' · ' + repo.commit + ' · PR #' + repo.pull) + '</small></div></div>'
    + btn(icon('bot') + escape(t('repos.askSnippet')),'ask-snippet','secondary small',attr('id',repo.id)
      + ' title="' + escape(codeReferenceLabel(reference)) + '"')
    + '</figcaption><pre><code>' + repo.code.map((line,i) => '<span class="code-line"><span aria-hidden="true">' + (repo.startLine + i) + '</span>'
    + escape(line) + '</span>').join('\n') + '</code></pre></figure>';
}

export function filterControls(state, busy=false) {
  const disabled = busy || state.access === 'none';
  const picker = (label, value, entries, action, glyph) => {
    const title = '<span class="filter-glyph">' + icon(glyph) + '</span><span class="filter-value">' + escape(value)
      + '</span><span class="filter-chevron" aria-hidden="true"></span>';
    const control = disabled ? '<button class="filter-trigger" type="button" aria-label="' + escape(label + ': ' + value) + '" disabled>' + title + '</button>'
      : '<details class="filter-dropdown"><summary id="' + (action === 'scope-option' ? 'repo-scope-trigger' : 'repo-range-trigger') + '" class="filter-trigger" aria-label="' + escape(label + ': ' + value) + '">'
        + title + '</summary><div class="filter-menu" role="group" aria-label="' + escape(label) + '">'
        + entries.map(([id,name]) => '<button type="button" class="filter-option" data-act="' + action + '"' + attr('id',id)
          + ' aria-label="' + escape(name) + '" aria-pressed="' + (name === value) + '"><span>' + escape(name) + '</span>'
          + (name === value ? icon('check') : '') + '</button>').join('') + '</div></details>';
    return '<div class="filter-field"><span class="filter-label">' + escape(label) + '</span>' + control + '</div>';
  };
  return '<div class="toolbar-group" role="group"' + labelAttr(t('profile.filters')) + '>'
    + picker(t('scope.label'),scopeLabel(state.scope),scopes.map(key => [key,scopeLabel(key)]),'scope-option','repo')
    + picker(t('range.label'),rangeLabel(state.range),ranges.map(days => [days,rangeLabel(days)]),'range-option','pulse')
    + '</div>';
}

const heroPhrases = ['about.rotateCode','about.rotateProjects','about.rotateFixes'];

function aboutContent(live=false) {
  const phrases = heroPhrases.map(key => '<span class="hero-phrase-size">' + escape(t(key)) + '<span class="hero-caret"></span></span>').join('');
  const features = [['evidence','repo'],['mentor','bot'],['road','branch']];
  return '<section class="about-hero" aria-labelledby="about-title"><div class="about-copy">'
    + '<p class="section-kicker"><span class="status-dot"></span>' + escape(t('about.kicker')) + '</p>'
    + '<h1 id="about-title">' + escape(t('about.title')) + '<span class="sr-only"> ' + escape(t(heroPhrases[0]))
    + '</span><span class="hero-rotation" aria-hidden="true">' + phrases + '<span class="hero-typed"><span class="hero-typed-text">'
    + escape(t(heroPhrases[0])) + '</span><span class="hero-caret"></span></span></span></h1>'
    + '<p class="hero-lede">' + escape(t('about.lede')) + '</p>'
    + '<div class="action-row">' + btn(escape(t('about.tryStudio')) + icon('arrow'),'enter','primary')
    + '<a class="button secondary" data-act="show-mentor-preview" href="#mentor-preview">' + escape(t('about.lookInside')) + '</a></div>'
    + '<p class="sample-entry-note">' + escape(live ? (getLanguage() === 'en' ? 'Connect GitHub to access live data.' : 'Kết nối GitHub để truy cập dữ liệu thật.') : t('about.sampleNote')) + '</p></div>'
    + '<section class="terminal" id="mentor-preview"' + labelAttr(t('about.chatLabel')) + '><header class="terminal-bar"><span class="terminal-mark">' + icon('bot') + '</span><strong>AI Mentor</strong>'
    + '</header>'
    + '<div class="bot-stage" aria-hidden="true"><div class="bot-orbit-plane"><span class="orbit orbit-outer"><i></i></span><span class="orbit orbit-inner"><i></i></span><span class="art-star s1"></span><span class="art-star s2"></span><span class="art-star s3"></span><span class="art-star s4"></span>'
    + '<span class="bot-float">' + bot('pixel-hero') + '</span><span class="bot-shadow"></span></div></div>'
    + '<div class="preview-chat"><div class="preview-question"><p>' + escape(t('about.ask')) + '</p><span class="tiny-avatar" aria-hidden="true">M</span></div>'
    + '<div class="preview-answer">' + bot('pixel-small','happy') + '<div><strong>IT Talent Mentor</strong><div class="preview-response">'
    + '<p class="preview-typing" aria-hidden="true"><span class="typing-dots"><i></i><i></i><i></i></span>'
    + escape(t('about.mentorReading')) + '</p><div class="about-reply"><p>'
    + escape(t('about.replyOne')) + '</p><p>' + escape(t('about.replyTwo'))
    + '</p><span class="inline-source">' + icon('file') + ' tests/test_clubs.py</span></div></div></div></div></div>'
    + '</section></section><section class="public-features">' + features.map(([key,glyph]) => '<article><span class="feature-icon">' + icon(glyph) + '</span><div><h2>'
      + escape(t('about.' + key + 'Title')) + '</h2><p>' + escape(t('about.' + key + 'Copy')) + '</p></div></article>').join('') + '</section>';
}

export function landing(live=false) {
  return '<div class="public-page"><header class="public-top"><div class="site-shell">' + brand()
    + '<div class="public-menu"><a aria-current="page" href="#about">' + escape(t('nav.about')) + '</a></div><div class="public-actions">' + languagePicker()
    + '<a class="button small secondary" href="#login">' + escape(t('nav.signin')) + ' ' + icon('arrow') + '</a></div></div></header>'
    + '<main class="site-shell">' + aboutContent(live) + '</main><footer class="public-foot site-shell"><span>IT Talent AI Profile</span></footer></div>';
}

export function login(live=false) {
  return '<main class="login-page"><div class="login-shell"><div class="login-top"><a class="back-link" href="#about">← ' + escape(t('nav.about')) + '</a>'
    + languagePicker() + '</div><article class="login-card"><div class="login-emblem">' + bot('pixel-login') + '</div><h1>' + escape(t('login.title'))
    + '</h1><p>' + escape(live ? (document.documentElement.lang === 'en' ? 'Connect GitHub to open your Studio.' : 'Kết nối GitHub để mở Studio của bạn.') : t('login.copy')) + '</p><div class="login-actions">' + btn('<svg class="github-mark" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .8a11.2 11.2 0 0 0-3.54 21.82c.56.1.77-.24.77-.54v-1.9c-3.13.68-3.79-1.33-3.79-1.33-.51-1.3-1.25-1.64-1.25-1.64-1.02-.7.08-.69.08-.69 1.13.08 1.72 1.16 1.72 1.16 1 1.72 2.63 1.22 3.27.93.1-.73.39-1.22.71-1.5-2.5-.28-5.13-1.25-5.13-5.54 0-1.23.44-2.23 1.15-3.02-.12-.28-.5-1.42.11-2.97 0 0 .94-.3 3.08 1.15a10.7 10.7 0 0 1 5.6 0c2.13-1.45 3.07-1.15 3.07-1.15.61 1.55.23 2.69.12 2.97.72.79 1.15 1.79 1.15 3.02 0 4.3-2.63 5.25-5.14 5.53.4.35.76 1.04.76 2.09v2.89c0 .3.2.65.77.54A11.2 11.2 0 0 0 12 .8Z"/></svg> ' + escape(t('login.github')),'oauth','primary')
    + (live ? '<a class="button secondary" href="#about">' + escape(getLanguage() === 'en' ? 'Back to About' : 'Quay lại giới thiệu') + icon('arrow') + '</a>'
      : btn(escape(t('login.sample')) + ' ' + icon('arrow'),'enter')) + '</div><p class="login-note">' + icon('lock') + ' '
    + escape(live ? (document.documentElement.lang === 'en' ? 'Private repository access is optional.' : 'Quyền repository riêng tư là tùy chọn.') : t('login.note')) + '</p></article></div></main>';
}

export function studioShell(page,content,user,mentorOpen,live=false) {
  const label = t('nav.' + page);
  const links = items => items.map(([key,glyph]) => {
    const name = t('nav.' + key);
    return '<a class="nav-link" href="#studio/' + key + '"' + labelAttr(name)
      + (page === key ? ' aria-current="page"' : '') + '>' + icon(glyph) + '<span class="nav-label">' + escape(name) + '</span></a>';
  }).join('');
  return '<div class="studio"><a class="skip-link" href="#main-view">' + escape(t('nav.skip')) + '</a><aside class="sidebar">' + brand(true)
    + '<nav id="studio-menu" class="studio-menu" aria-label="Studio">' + links(pages.slice(0,5)) + '<div class="nav-divider"></div>' + links(pages.slice(5)) + '</nav>'
    + '<div class="sidebar-foot"><div class="demo-profile"><span class="profile-avatar" aria-hidden="true">' + escape(user.name?.slice(0,1).toUpperCase() || '?') + '</span><div><strong>' + escape(user.name)
    + '</strong><small>' + escape((live ? '' : '@') + user.handle) + '</small></div></div>' + btn(icon('logout') + '<span class="nav-label">'
      + escape(t('nav.signout')) + '</span>','logout','quiet small',labelAttr(t('nav.signout')))
    + '</div></aside>'
    + '<div class="workspace"><header class="workspace-top"><div class="crumb"><span>Studio</span><span aria-hidden="true">/</span><strong>' + escape(label)
    + '</strong></div><div class="top-actions"><span class="workspace-demo"><span class="status-dot"></span> ' + escape(live ? 'GitHub' : t('nav.sample'))
    + '</span>' + languagePicker()
    + '<a class="button quiet small studio-settings" href="#studio/settings"' + labelAttr(t('nav.settings'))
    + (page === 'settings' ? ' aria-current="page"' : '') + ' title="' + escape(t('nav.settings')) + '">' + icon('settings')
    + '</a>'
    + btn(icon('panel') + escape(t('action.askMentor')),'toggle-mentor','small studio-mentor',
      'id="mentor-toggle" aria-controls="mentor-panel" aria-expanded="' + mentorOpen + '"')
    + '</div></header><div class="workspace-body' + (mentorOpen ? ' has-mentor' : '') + '">'
    + '<div class="workspace-content"><main class="main-view page-enter" id="main-view" tabindex="-1">' + content + '</main></div>'
    + '<div id="mentor-resize" role="separator" tabindex="0" aria-orientation="vertical" aria-controls="mentor-panel"'
    + labelAttr(t('mentor.resize')) + ' title="' + escape(t('mentor.resizeHelp')) + '" aria-valuemin="300"'
    + (mentorOpen ? '' : ' hidden') + '></div></div></div></div>';
}
const glyphs = {
  grid:['1110111','1010101','1110111','0000000','1110111','1010101','1110111'],
  repo:['1111100','1000100','1011110','1010010','1110010','0011110','0000000'],
  bot:['0001000','0111110','1010101','1010101','1000001','0111110','0000000'],
  branch:['1100011','1100011','0100010','0100110','0111000','0100000','1100000'],
  job:['0011100','0010100','1111111','1000001','1111111','1000001','1111111'],
  file:['1111100','1000110','1000001','1011101','1000001','1011101','1111111'],
  lock:['0011100','0100010','0100010','1111111','1001001','1001001','1111111'],
  info:['0111110','1100011','1001001','1000001','1001001','1101011','0111110'],
  pulse:['0001000','0001000','0011100','1110111','0000100','0000100','0000000'],
  arrow:['0011110','0000110','0001010','0010010','0100000','1000000','0000000'],
  award:['1111111','1101011','1101011','0111110','0001000','0001000','0011100'],
  pause:['0110110','0110110','0110110','0110110','0110110','0110110','0110110'],
  play:['1000000','1110000','1111100','1111110','1111100','1110000','1000000'],
  terminal:['1111111','1000001','1100011','1010001','1100111','1000001','1111111'],
  check:['0000001','0000011','0000110','1001100','1111000','0110000','0000000'],
  database:['0111110','1000001','1111111','1000001','1111111','1000001','0111110'],
  plus:['0001000','0001000','0001000','1111111','0001000','0001000','0001000'],
  close:['1000001','0100010','0010100','0001000','0010100','0100010','1000001'],
  search:['0111000','1000100','1000100','1000100','0111000','0000100','0000010'],
  link:['0011110','0100010','0101110','0001000','0111010','0100010','0111100'],
  send:['0001000','0011100','0111110','1101011','0001000','0001000','0001000'],
  sources:['1111111','1000001','1011101','1000001','1011101','1000001','1111111'],
  settings:['0011100','0110110','1100011','1000001','1100011','0110110','0011100'],
  panel:['1111111','1001101','1001101','1001101','1001101','1001101','1111111'],
  logout:['1111000','1001000','1001010','1011111','1001010','1001000','1111000']
};

export function paintIcons(root) {
  const layer = document.createElement('canvas');
  layer.width = layer.height = 7;
  const context = layer.getContext('2d');
  if (!context) return;
  for (const [name, rows] of Object.entries(glyphs)) {
    context.clearRect(0,0,7,7);
    context.fillStyle = '#fff';
    rows.forEach((row, y) => [...row].forEach((bit, x) => { if (bit === '1') context.fillRect(x,y,1,1); }));
    root.style.setProperty('--i-' + name, 'url("' + layer.toDataURL() + '")');
  }
}

const faces = {
  idle: [
    '..........', '.11....11.', '.11....11.', '.11....11.', '..........', '...2..2...', '....22....'
  ],
  blink: [
    '..........', '..........', '..........', '.22....22.', '..........', '...2..2...', '....22....'
  ],
  thinking: [
    '..........', '.......33.', '.11....33.', '.11.......', '..........', '...3.3.3..', '..........'
  ],
  ponder: [
    '..........', '.33.......', '.33....11.', '.......11.', '..........', '..3.3.3...', '..........'
  ],
  happy: [
    '..........', '..1....1..', '.1.1..1.1.', '..........', '.5......5.', '...1..1...', '....11....'
  ],
  curious: [
    '..33......', '.......33.', '.......33.', '..33......', '....33....', '...3..3...', '....33....'
  ],
  wink: [
    '..........', '.11.......', '.11.......', '.11....22.', '..........', '...1..1...', '....11....'
  ],
  excited: [
    '.1......1.', '111....111', '.1......1.', '..........', '.5.1111.5.', '...1551...', '....11....'
  ],
  love: [
    '.55.5.55.5', '.5555.5555', '..55...55.', '..........', '..........', '...1..1...', '....11....'
  ],
  review: [
    '..........', '.444..444.', '..44..44..', '..44..44..', '..........', '....44....', '..........'
  ]
};
const defaultBotColors = botPalette(presets.slate.accent);
let botColors = defaultBotColors;
const paintedBots = new WeakMap();

export function refreshBotColors(root) {
  const style = getComputedStyle(document.documentElement);
  botColors = Object.fromEntries(Object.entries(defaultBotColors)
    .map(([key,fallback]) => [key,style.getPropertyValue('--bot-' + key).trim() || fallback]));
  root.querySelectorAll('.bot-sprite').forEach(canvas => drawBot(canvas,canvas.dataset.botFrame || canvas.dataset.botMood || 'idle'));
}

export function paintBot(canvas, mood=canvas.dataset.botMood || 'idle', frame=mood) {
  canvas.dataset.botMood = mood;
  drawBot(canvas,frame);
}

function drawBot(canvas,frame) {
  const old = paintedBots.get(canvas);
  if (old?.frame === frame && old.colors === botColors) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const {shadow,metal,frame:body,edge,screen,lens,light,signal} = botColors;
  const faceColors = {'1':light,'2':signal,'3':'#ffdb9b','4':lens,'5':'#f8b6ab'};
  const rect = (color,x,y,w,h) => { ctx.fillStyle = color; ctx.fillRect(x,y,w,h); };
  ctx.clearRect(0,0,24,24);
  rect(shadow,5,22,14,1);
  rect(metal,10,2,4,3);
  rect(lens,11,1,2,2);
  rect(edge,5,6,14,1);
  rect(body,3,7,18,12);
  rect(edge,5,19,14,2);
  rect(metal,2,10,2,6);
  rect(metal,20,10,2,6);
  rect(edge,5,7,14,11);
  rect(metal,5,8,14,9);
  rect(screen,6,9,12,7);
  rect(lens,6,18,2,1);
  rect(signal,17,18,1,1);
  faces[frame].forEach((row,y) => [...row].forEach((pixel,x) => {
    if (pixel !== '.') rect(faceColors[pixel],x+7,y+9,1,1);
  }));
  canvas.dataset.botFrame = frame;
  paintedBots.set(canvas,{frame,colors:botColors});
}

export function paintBots(root) {
  root.querySelectorAll('.bot-sprite').forEach(canvas => paintBot(canvas));
}
