import {jobs, radarMetrics, ranges, scopes, sampleUser} from './data.js';
import {dateLabel, getLanguage, roleLabel, setLanguage, sourceLabel, t} from './i18n.js';
import {currentRepos, repoSelected, scoredRepos, wordsIn} from './model.js';
import {answerMentor} from './mentor-model.js';
import {
  addRoadTask, checklist, completeMilestone, dependentMilestones, evidenceURL, milestonesFor,
  milestoneText, nextStep, paths, planFor, setChecklist, stateOf, taskLabel, undoMilestone
} from './roadmap-model.js';
import {findSharedProfile, loadProfile, profileKey, readSession, saveProfile, writeSession} from './profile-store.js';
import {compareSnapshots, createSnapshot} from './analysis-data.js';
import {codeReference, matchesCodeReference} from './evidence.js';
import {escape, landing, login, pages, paintBot, paintBots, paintIcons, refreshBotColors, studioShell} from './ui.js';
import {dashboard, repositoryView} from './assessment-view.js';
import {animateUnlock, paintMap, roadmap} from './roadmap-view.js';
import {recommendationFor} from './roadmap-recommendation.js';
import {jobsView, cvView, dataView, statusView, shareView} from './views.js';
import {mentor} from './mentor-view.js';
import {mountRadar} from './radar.js';
import {mountMentorLayout} from './mentor-resize.js';
import {settingsView, syncThemeControls} from './settings-view.js';
import {applyTheme, colorFields, defaultPreset, hexColor, loadTheme, presets, saveTheme, themeColors, themeKey} from './theme.js';
import {mountAboutMotion} from './about-motion.js';
import {createLiveStudio} from './live.js';
import {renderReferenceCV, serializeCVFromSections, parseCVForReference} from './cv-renderer.js';
import {liveCV,liveDashboard,liveData,liveJobs,livePublic,liveRepos,liveRoadmap,liveStatus,orderedTrackingMilestones,updateCVFitScale} from './live-views.js';

const copy = (vi, en) => getLanguage() === 'en' ? en : vi;

const $ = selector => document.querySelector(selector);
const root = $('#root');
const mentorPanel = $('#mentor-panel');
const dialog = $('#dialog');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const compactMentor = matchMedia('(max-width: 860px)');
const liveMode = document.body.dataset.studioMode === 'live';
const state = liveMode ? {
  access:'none',scope:'public',range:90,goal:'backend',repo:'',template:'plain',plans:{},
  snapshots:[],seededReports:[],skillBasis:[],claimEvidence:[]
} : loadProfile();
let theme = loadTheme();
const session = liveMode ? null : readSession();
let signedIn = Boolean(session);
if (session) Object.assign(state,session);

const initialSources = liveMode ? ['github'] : ['github','report','roadmap'];
const defaultCV = () => ({name:liveMode ? '' : sampleUser.name,role:liveMode ? '' : roleLabel(state.goal),body:''});
const mentorFrames = {
  idle:[['idle',1400],['blink',160],['idle',950],['happy',540]],
  thinking:[['thinking',280],['ponder',340]],
  happy:[['happy',1100],['blink',165],['happy',2400]],
  curious:[['curious',1700],['ponder',430]],
  review:[['review',2100],['blink',165]]
};
const runtime = {
  milestone:liveMode ? 0 : Math.max(0,nextStep(state)), scoreTab:'tech', roleIndex:'backend', radarAxis:null,
  evidenceFocus:null, operation:null, mentorOpen:false, sourcesOpen:false, chosen:new Set(initialSources),
  privateAI:false, messages:[], chatDraft:'', chatSnippet:null, chatPending:false, chatTimer:0, chatSequence:0,
  roadUnlock:null,
  atsChecked:false, jdText:'', jobQuery:'', cvDraft:{...(state.cv ?? defaultCV())}, cvEdited:Boolean(state.cv)
};
const live = liveMode ? createLiveStudio({
  state,runtime,render:updateStudio,drawMentor:updateMentor,showModal,openMentor,navigate,notice:notifyText
}) : null;
const studioViews = live ? {
  dashboard:() => liveDashboard(state,runtime,live.data),
  repos:() => liveRepos(state,live.data,live.active()),
  roadmap:() => liveRoadmap(live.data),
  jobs:() => liveJobs(state,live.data),
  cv:() => liveCV(state,runtime,live.data),
  data:() => liveData(state,live.data),
  status:() => liveStatus(live.data),
  settings:() => settingsView(theme)
} : {
  dashboard,repos:repositoryView,roadmap,jobs:jobsView,cv:cvView,data:dataView,status:statusView,
  settings:() => settingsView(theme)
};
let route;
let mentorTimer;
let mentorCloseTimer;
let mentorOpenFrame;
let aboutMotion;
let toastTimer;
let mapObserver;
let jdTextareaObserver;
let stopRoadAnimation;
let radar;
let cvObserver;
let mentorLayout;
let mentorContextKey;
let mentorOpener;
let compactScroll;
let operationTimers = [];
let modal;
let dialogOpener;
let dialogFocusKey;
let jumpTarget;

const save = () => { if (!live) saveProfile(state,signedIn); };
function setSession(active) {
  signedIn = active;
  writeSession(active);
}

let toastRemaining = 2000;
let toastTotalTime = 2000;
let toastRaf = null;
let toastPaused = false;
let toastDismissTimeout = null;

function dismissToast() {
  const toast = $('#toast');
  if (!toast || toast.hidden || toast.classList.contains('toast-leaving')) return;
  if (toastRaf) cancelAnimationFrame(toastRaf);
  clearTimeout(toastDismissTimeout);
  toast.classList.remove('toast-show');
  toast.classList.add('toast-leaving');
  toastDismissTimeout = setTimeout(() => {
    toast.hidden = true;
    toast.style.display = 'none';
    toast.classList.remove('toast-leaving');
  }, 260);
}

function notify(key,fields) { notifyText(t(key,fields)); }

function notifyText(text) {
  const toast = $('#toast');
  if (!toast) return;
  if (toastRaf) cancelAnimationFrame(toastRaf);
  clearTimeout(toastDismissTimeout);

  // Clean up any inline overrides so CSS transition controls transform/opacity/filter smoothly
  toast.style.removeProperty('display');
  toast.style.removeProperty('transform');
  toast.style.removeProperty('opacity');
  toast.style.removeProperty('filter');

  // Hard-lock position at top-center via inline styles to defeat any stale CSS positioning cache
  toast.style.setProperty('position', 'fixed', 'important');
  toast.style.setProperty('top', '24px', 'important');
  toast.style.setProperty('bottom', 'auto', 'important');
  toast.style.setProperty('left', '50%', 'important');
  toast.style.setProperty('right', 'auto', 'important');
  toast.style.setProperty('z-index', '999999', 'important');

  // Reset animation states
  toast.classList.remove('toast-leaving');
  toast.classList.remove('toast-show');

  const messageText = typeof text === 'string' ? text : (text?.message || JSON.stringify(text));

  toast.innerHTML = 
    '<div class="toast-content">' +
      '<span class="toast-badge-icon" aria-hidden="true">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
          '<circle cx="12" cy="12" r="10"></circle>' +
          '<line x1="12" y1="16" x2="12" y2="12"></line>' +
          '<line x1="12" y1="8" x2="12.01" y2="8"></line>' +
        '</svg>' +
      '</span>' +
      '<span class="toast-message">' + escape(messageText) + '</span>' +
      '<button type="button" class="toast-close-btn" aria-label="Đóng thông báo" title="Đóng">' +
        '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">' +
          '<line x1="18" y1="6" x2="6" y2="18"></line>' +
          '<line x1="6" y1="6" x2="18" y2="18"></line>' +
        '</svg>' +
      '</button>' +
    '</div>' +
    '<div class="toast-progress-bar"><div class="toast-progress-fill"></div></div>';

  toast.hidden = false;

  // Trigger reflow then add .toast-show so CSS entrance transition plays seamlessly
  void toast.offsetWidth;
  toast.classList.add('toast-show');

  const closeBtn = toast.querySelector('.toast-close-btn');
  if (closeBtn) {
    closeBtn.onclick = (e) => {
      e.stopPropagation();
      dismissToast();
    };
  }

  const progressFill = toast.querySelector('.toast-progress-fill');
  toastTotalTime = 2000;
  toastRemaining = toastTotalTime;
  toastPaused = false;
  let lastTime = performance.now();

  function step(now) {
    if (!toastPaused) {
      const delta = now - lastTime;
      toastRemaining -= delta;
      if (progressFill) {
        const pct = Math.max(0, (toastRemaining / toastTotalTime) * 100);
        progressFill.style.width = pct + '%';
      }
      if (toastRemaining <= 0) {
        dismissToast();
        return;
      }
    }
    lastTime = now;
    toastRaf = requestAnimationFrame(step);
  }

  toast.onmouseenter = () => {
    toastPaused = true;
  };
  toast.onmouseleave = () => {
    toastPaused = false;
    lastTime = performance.now();
  };

  toastRaf = requestAnimationFrame(step);
}

function audit(key,fields) {
  state.audit = [{at:Date.now(),key,fields},...state.audit].slice(0,35);
  save();
}

function readRoute() {
  const hash = location.hash.slice(1);
  if (hash.startsWith('share/')) return {kind:'share',id:hash.slice(6)};
  if (!signedIn) {
    if (hash.startsWith('studio/')) history.replaceState(null,'',live ? '#login' : '#about');
    return {kind:hash === 'login' || (live && hash.startsWith('studio/')) ? 'login' : 'about'};
  }
  if (live && (hash === 'about' || hash === 'mentor-preview')) return {kind:'about'};
  if (hash.startsWith('studio/')) {
    const page = hash.slice(7);
    if (Object.hasOwn(studioViews,page)) return {kind:'studio',page};
    if (page === 'mentor') runtime.mentorOpen = true;
  }
  history.replaceState(null,'','#studio/dashboard');
  return {kind:'studio',page:'dashboard'};
}

const isStudio = page => route?.kind === 'studio' && (!page || route.page === page);
const sameRoute = (a,b) => a && a.kind === b.kind && a.page === b.page && a.id === b.id;
function focusKey(element) {
  if (!element) return null;
  if (element.id) return '#' + CSS.escape(element.id);
  if (element.matches('a[href^="#studio/"]')) return 'a[href="' + CSS.escape(element.getAttribute('href')) + '"]';
  if (element.dataset.act) {
    const id = element.dataset.id;
    return '[data-act="' + CSS.escape(element.dataset.act) + '"]' + (id !== undefined ? '[data-id="' + CSS.escape(id) + '"]' : '');
  }
  if (element.name) return '[name="' + CSS.escape(element.name) + '"]'
    + (element.type === 'checkbox' ? '[value="' + CSS.escape(element.value) + '"]' : '');
  if (element.matches('.road-criterion,.road-task')) {
    return '.' + element.classList[0] + '[value="' + CSS.escape(element.value) + '"]';
  }
  return null;
}
function focusMain() {
  const target = $('#main-view') || root.querySelector('main h1');
  if (target) {
    target.tabIndex = -1;
    target.focus({preventScroll:true});
  }
}
function replaceView(view,content) {
  const key = view.contains(document.activeElement) ? focusKey(document.activeElement) : null;
  const openDetails = [...view.querySelectorAll('details[open]')].map(el => el.className);
  view.innerHTML = content;
  view.querySelectorAll('details').forEach(el => { if (openDetails.includes(el.className)) el.open = true; });
  paintBots(view);
  if (key) view.querySelector(key)?.focus({preventScroll:true});
}
// Keep the JD field sized with stable dimensions; height is owned by CSS to prevent jitter.
function resizeJDTextarea(textarea = $('#jd-form textarea[name="jd"]')) {
  if (!textarea) return;
}
function updateStudio() {
  if (!isStudio()) return;
  replaceView($('#main-view'),studioViews[route.page](state,runtime));
  prepareView();
  if (runtime.mentorOpen) renderMentorPanel();
}
function renderRoute(force=false) {
  const previous = route;
  const next = readRoute();
  if (!force && sameRoute(route,next)) {
    renderMentorPanel();
    return;
  }
  if (dialog.open) closeModal('cancel');
  const motion = aboutMotion?.dispose();
  aboutMotion = null;
  mapObserver?.disconnect();
  stopRoadAnimation?.();
  stopRoadAnimation = null;
  radar?.disconnect();
  radar = null;
  cvObserver?.disconnect();
  cvObserver = null;
  if (next.kind !== 'studio') {
    runtime.mentorOpen = false;
    mentorOpener = null;
    compactScroll = undefined;
    clearTimeout(mentorTimer);
    clearTimeout(mentorCloseTimer);
    mentorCloseTimer = undefined;
    cancelAnimationFrame(mentorOpenFrame);
    mentorPanel.classList.remove('panel-visible');
    mentorLayout?.disconnect();
    mentorLayout = null;
    mentorPanel.hidden = true;
    mentorPanel.replaceChildren();
    document.body.append(mentorPanel);
  }
  route = next;
  if (isStudio() && $('.workspace-body') && !force) {
    updateStudioNavigation(next.page);
    replaceView($('#main-view'),studioViews[next.page](state,runtime));
  } else if (isStudio()) {
    const focusInPanel = mentorPanel.contains(document.activeElement) ? focusKey(document.activeElement) : null;
    mentorLayout?.disconnect();
    document.body.append(mentorPanel);
    replaceView(root,studioShell(next.page,studioViews[next.page](state,runtime),live ? {
      name:live.data.user.full_name || live.data.user.email,handle:live.data.user.email
    } : sampleUser,runtime.mentorOpen,Boolean(live)));
    $('.workspace-body').append(mentorPanel);
    mentorLayout = mountMentorLayout($('.workspace'),compactMentor);
    if (focusInPanel) mentorPanel.querySelector(focusInPanel)?.focus({preventScroll:true});
  } else {
    const content = next.kind === 'login' ? login(Boolean(live))
      : next.kind === 'share' ? (live ? livePublic(live.data.publicToken === next.id ? live.data.public : undefined) : shareView(findSharedProfile(next.id),signedIn))
      : landing(Boolean(live));
    replaceView(root,content);
  }
  document.documentElement.lang = getLanguage();
  $('meta[name="description"]').content = t('meta.description');
  const title = next.page ?? ({login:'signin',share:'shared',about:'about'})[next.kind];
  document.title = t('nav.' + title) + ' · IT Talent AI Profile';
  const activeNav = $('.studio-menu [aria-current="page"]');
  if (activeNav) activeNav.parentElement.scrollLeft = Math.max(0,activeNav.offsetLeft - 20);
  if (next.kind === 'about') aboutMotion = mountAboutMotion(root,reduced,force ? motion : undefined);
  prepareView();
  renderMentorPanel();
  if (force) updateMentor();
  if (live && !sameRoute(previous,next)) {
    if (next.kind === 'studio') {
      void live.loadPage(next.page);
      if (runtime.mentorOpen && !previous) void live.loadMentor();
    }
    if (next.kind === 'share') void live.loadPublic(next.id).then(() => {
      if (route.kind === 'share' && route.id === next.id) replaceView(root,livePublic(live.data.public));
    });
  }
}
function updateStudioNavigation(page) {
  for (const link of root.querySelectorAll('.studio-menu .nav-link, .studio-settings')) {
    if (link.hash === '#studio/' + page) link.setAttribute('aria-current','page');
    else link.removeAttribute('aria-current');
  }
  $('.crumb strong').textContent = t('nav.' + page);
}
function navigate(page,target) {
  jumpTarget = target;
  const hash = '#studio/' + page;
  if (location.hash !== hash) {
    location.hash = hash;
    return;
  }
  if (isStudio(page)) updateStudio();
  else renderRoute();
  focusJump();
}
function focusJump() {
  const target = jumpTarget && $(jumpTarget);
  jumpTarget = null;
  if (target) {
    target.tabIndex = -1;
    target.scrollIntoView({block:'nearest',behavior:'instant'});
    target.focus({preventScroll:true});
    if (target.id === 'repo-evidence') target.classList.add('evidence-arrival');
    return true;
  }
  return false;
}
function enter() {
  if (live) {
    if (signedIn) navigate('dashboard');
    else location.hash = 'login';
    return;
  }
  setSession(true);
  if (state.access === 'none') {
    state.access = 'public';
    state.scope = 'public';
  }
  save();
  navigate('dashboard');
}
function prepareView() {
  jdTextareaObserver?.disconnect();
  jdTextareaObserver = null;
  if (isStudio('jobs')) {
    // Keep JD textarea fixed height from CSS, no observer jitter
  }
  if (isStudio('roadmap')) {
    mapObserver?.disconnect();
    stopRoadAnimation?.();
    stopRoadAnimation = null;
    const map = $('.road-map');
    if (map) {
      paintMap(map,state,null,live ? orderedTrackingMilestones(live.data) : null);
      mapObserver = new ResizeObserver(() => paintMap(map,state,null,live ? orderedTrackingMilestones(live.data) : null));
      const repaint = () => paintMap(map,state,null,live?.data.tracking?.milestones);
      repaint();
      mapObserver = new ResizeObserver(repaint);
      mapObserver.observe(map);
      // Some node positions can move without changing the map's outer size.
      // Track their dimensions too, including when the Mentor panel is resized.
      map.querySelectorAll('.node').forEach(node => mapObserver.observe(node));
    }
  }
  if (isStudio('dashboard')) {
    radar?.disconnect();
    radar = mountRadar($('.radar-panel'),runtime.radarAxis,value => {
      runtime.radarAxis = value;
      if (runtime.mentorOpen) renderMentorPanel();
    });
  }
  if (isStudio('cv')) {
    cvObserver?.disconnect();
    const viewport = $('.cv-preview-viewport');
    if (viewport) {
      updateCVFitScale();
      cvObserver = new ResizeObserver(() => updateCVFitScale());
      cvObserver.observe(viewport);
    }
  }
}
function mentorContext() {
  const page = route?.page ?? 'dashboard';
  const glyph = pages.find(item => item[0] === page)?.[1] ?? 'settings';
  const repo = live ? live.active() : page === 'repos' ? repoSelected(state) : null;
  if (live) return {label:page === 'repos' ? repo?.full_name || t('nav.repos') : t('nav.' + page),icon:glyph,repoId:repo?.id};
  const milestone = page === 'roadmap' ? runtime.milestone : undefined;
  const metric = page === 'dashboard' ? radarMetrics[runtime.radarAxis] : undefined;
  const label = repo?.name ?? (metric ? t('metric.' + metric)
    : milestone === undefined ? t('nav.' + page) : milestoneText(state.goal,milestone));
  return {label,icon:glyph,repoId:repo?.id,milestone,metric};
}

function renderMentorPanel() {
  if (!isStudio()) return;
  const open = runtime.mentorOpen;
  const changed = open && (mentorPanel.hidden || !mentorPanel.classList.contains('panel-visible'));
  const body = $('.workspace-body');
  const splitter = $('#mentor-resize');
  $('#mentor-toggle').setAttribute('aria-expanded',String(open));
  body.classList.toggle('has-mentor',open);
  if (open) {
    clearTimeout(mentorCloseTimer);
    mentorCloseTimer = undefined;
    mentorPanel.hidden = false;
    mentorPanel.inert = false;
    mentorPanel.removeAttribute('aria-hidden');
    if (changed) {
      cancelAnimationFrame(mentorOpenFrame);
      mentorPanel.getBoundingClientRect();
      mentorOpenFrame = requestAnimationFrame(() => {
        if (runtime.mentorOpen) mentorPanel.classList.add('panel-visible');
      });
    }
  } else if (!mentorPanel.hidden && mentorPanel.classList.contains('panel-visible')) {
    clearTimeout(mentorCloseTimer);
    cancelAnimationFrame(mentorOpenFrame);
    mentorPanel.classList.remove('panel-visible');
    mentorPanel.inert = true;
    mentorPanel.setAttribute('aria-hidden','true');
    const finishClose = () => {
      mentorCloseTimer = undefined;
      if (!runtime.mentorOpen) mentorPanel.hidden = true;
    };
    if (reduced.matches) finishClose();
    else mentorCloseTimer = setTimeout(finishClose,280);
  } else if (!open && !mentorPanel.classList.contains('panel-visible')) {
    cancelAnimationFrame(mentorOpenFrame);
    mentorPanel.inert = true;
    mentorPanel.setAttribute('aria-hidden','true');
    if (!mentorCloseTimer) mentorPanel.hidden = true;
  }
  splitter.hidden = !open;
  splitter.tabIndex = open && !compactMentor.matches ? 0 : -1;
  $('.workspace-content').inert = open && compactMentor.matches;
  mentorLayout?.refresh();
  if (isStudio('cv')) {
    setTimeout(updateCVFitScale, 50);
    setTimeout(updateCVFitScale, 300);
  }
  if (!open) {
    clearTimeout(mentorTimer);
    return;
  }

  const context = mentorContext();
  if (changed || !mentorPanel.firstElementChild || mentorContextKey !== JSON.stringify(context)) {
    updateMentor(false,!mentorPanel.firstElementChild,context);
  }
}

function updateMentor(refocus=false,scrollLatest=false,context=mentorContext()) {
  if (!runtime.mentorOpen || !isStudio()) return;
  const focused = document.activeElement;
  const active = mentorPanel.contains(focused) ? focusKey(focused) : null;
  const caret = focused?.id === 'mentor-question' ? [focused.selectionStart,focused.selectionEnd,focused.selectionDirection] : null;
  const previousScroll = mentorPanel.querySelector('.chat-log')?.scrollTop ?? 0;
  mentorContextKey = JSON.stringify(context);
  mentorPanel.innerHTML = mentor(runtime,context,scrollLatest,live?.data);
  paintBots(mentorPanel);
  animateMentorFace();
  const log = mentorPanel.querySelector('.chat-log');
  log.scrollTop = scrollLatest ? log.scrollHeight : previousScroll;
  const target = active && mentorPanel.querySelector(active);
  if (refocus && !dialog.open) $('#mentor-question')?.focus({preventScroll:true});
  else if (target && !dialog.open) {
    target.focus({preventScroll:true});
    if (caret) target.setSelectionRange(...caret);
  }
}

function animateMentorFace() {
  clearTimeout(mentorTimer);
  if (!runtime.mentorOpen) return;
  const faces = [...mentorPanel.querySelectorAll('.mentor-avatar canvas, .mentor-greeting, .chat-log [data-bot-mood="thinking"]')];
  faces.forEach(face => paintBot(face));
  mentorPanel.classList.toggle('motion-paused',document.hidden || reduced.matches);
  if (document.hidden || reduced.matches || !faces.length) return;
  const mood = faces[0].dataset.botMood;
  const frames = mentorFrames[mood] ?? mentorFrames.idle;
  const draw = index => {
    const [frame,duration] = frames[index];
    faces.forEach(face => paintBot(face,mood,frame));
    mentorTimer = setTimeout(() => draw((index + 1) % frames.length),duration);
  };
  draw(0);
}
function openMentor() {
  if (!isStudio()) return;
  if (live && !runtime.mentorOpen) void live.loadMentor();
  if (!runtime.mentorOpen) {
    mentorOpener = document.activeElement;
    compactScroll = compactMentor.matches ? window.scrollY : undefined;
  }
  runtime.mentorOpen = true;
  renderMentorPanel();
  if (isStudio('cv')) updateStudio();
  if (compactMentor.matches) $('.workspace').scrollIntoView({block:'start',behavior:'instant'});
  $(compactMentor.matches ? '#mentor-title' : '#mentor-question')?.focus({preventScroll:true});
}
function closeMentor(returnFocus=false) {
  runtime.mentorOpen = false;
  if (live?.data) live.data.rightPanelExplicitOpen = false;
  renderMentorPanel();
  if (isStudio('cv')) updateStudio();
  if (returnFocus) {
    const target = mentorOpener?.isConnected && !mentorOpener.disabled ? mentorOpener : $('#mentor-toggle');
    if (compactMentor.matches && compactScroll !== undefined) window.scrollTo({top:compactScroll,behavior:'instant'});
    target?.focus({preventScroll:true});
  }
  compactScroll = undefined;
  mentorOpener = null;
}
function clearChat(keepDraft=false) {
  clearTimeout(runtime.chatTimer);
  runtime.chatPending = false;
  runtime.messages = [];
  runtime.chatSnippet = null;
  if (!keepDraft) runtime.chatDraft = '';
  updateMentor();
}
function sendChat(raw,context=mentorContext(),snippet=runtime.chatSnippet) {
  if (live) return live.send(raw,context);
  const question = raw.trim().slice(0,400);
  if (!question || runtime.chatPending) return;
  const answer = answerMentor(state,question,runtime.chosen,runtime.privateAI,{...context,snippet});
  const attached = answer.source?.snippet;
  if (raw === runtime.chatDraft) runtime.chatDraft = '';
  if (attached) runtime.chatSnippet = null;
  runtime.chatPending = true;
  runtime.messages = [...runtime.messages.slice(-28),{type:'user',text:question,snippet:attached,id:++runtime.chatSequence}];
  updateMentor(true,true);
  const finish = () => {
    runtime.chatPending = false;
    runtime.messages.push({type:'agent',id:++runtime.chatSequence,...answer});
    if (answer.used.length) audit('audit.read',{sources:answer.used});
    if (answer.action) audit('audit.proposed');
    if (isStudio('data')) updateStudio();
    updateMentor(false,true);
  };
  if (reduced.matches) finish();
  else runtime.chatTimer = setTimeout(finish,1050);
}

function showModal(title,content,actionLabel,action,{tone='primary',onCancel,onDecline,declineLabel,cancelLabel}={}) {
  if (!dialog.open) {
    dialogOpener = document.activeElement;
    dialogFocusKey = focusKey(dialogOpener);
  }
  modal = {action,onCancel,onDecline};
  dialog.setAttribute('aria-labelledby','dialog-title');
  const declineBtn = onDecline
    ? '<button class="button secondary" type="submit" value="decline" formnovalidate>' + escape(declineLabel || 'Từ chối') + '</button>'
    : '';
  const cLabel = cancelLabel || t('action.cancel');
  dialog.innerHTML = '<form method="dialog" class="dialog-contents"><h2 id="dialog-title">' + escape(title) + '</h2>' + content
    + '<div class="action-row"><button class="button quiet" type="submit" value="cancel" formnovalidate>' + escape(cLabel) + '</button>'
    + declineBtn
    + '<button class="button ' + tone + '" type="submit" value="confirm">' + escape(actionLabel) + '</button></div></form>';
  if (!dialog.open) {
    dialog.returnValue = '';
    dialog.showModal();
  }
  dialog.querySelector('button[value=cancel]').focus();
}
const paragraph = key => '<p>' + escape(t(key)) + '</p>';

function closeModal(result) {
  const onCancel = result === 'cancel' ? modal?.onCancel : null;
  const onDecline = result === 'decline' ? modal?.onDecline : null;
  const opener = dialogOpener;
  const key = dialogFocusKey;
  modal = null;
  dialogOpener = null;
  dialogFocusKey = null;
  dialog.close(result);
  onCancel?.();
  onDecline?.();
  const target = opener?.isConnected ? opener : key && $(key);
  if (target && target.getClientRects().length && !target.disabled) target.focus({preventScroll:true});
  else if (runtime.mentorOpen) mentorPanel.querySelector('input[name=question]')?.focus({preventScroll:true});
  else if (isStudio() && !jumpTarget) focusMain();
}

dialog.addEventListener('submit',event => {
  event.preventDefault();
  const val = event.submitter?.value;
  if (val === 'confirm') {
    if (modal?.action(new FormData(event.target),event.target) !== false && dialog.open) closeModal('confirm');
  } else if (val === 'decline') {
    closeModal('decline');
  } else {
    closeModal('cancel');
  }
});
dialog.addEventListener('cancel',event => {
  event.preventDefault();
  closeModal('cancel');
});

function cancelOperation() {
  operationTimers.forEach(clearTimeout);
  operationTimers = [];
  runtime.operation = null;
}
function sync() {
  if (runtime.operation || state.access === 'none') return;
  runtime.operation = {kind:'sync'};
  updateStudio();
  operationTimers = [setTimeout(() => {
    cancelOperation();
    state.synced = true;
    save();
    updateStudio();
    notify('analysis.syncDone',{count:currentRepos(state).length});
  },750)];
}
function analyze() {
  const repo = repoSelected(state);
  if (!repo || runtime.operation) return;
  state.repo = repo.id;
  runtime.operation = {kind:'analysis',id:repo.id,phase:0};
  updateStudio();
  operationTimers = [1,2].map(phase => setTimeout(() => {
    runtime.operation.phase = phase;
    if (isStudio('repos')) updateStudio();
  },620 * phase));
  operationTimers.push(setTimeout(() => {
    cancelOperation();
    const failure = state.simulateFailure;
    const at = Date.now();
    state.simulateFailure = false;
    state.attempts = [{repo:repo.id,at,scope:state.scope,range:state.range,state:failure ? 'failed' : 'success'},...state.attempts].slice(0,60);
    if (!failure) {
      state.snapshots = [createSnapshot(repo,state,at),...state.snapshots];
      state.focusScore = repo.id;
    }
    save();
    updateStudio();
    notify(failure ? 'analysis.timedout' : 'analysis.updated',{repo:repo.name});
  },1870));
}

function applyScope(scope) {
  if (state.scope !== scope) {
    clearChat(true);
    runtime.evidenceFocus = null;
    runtime.radarAxis = null;
  }
  state.scope = scope;
  if (scope === 'public') runtime.chosen.delete('private');
  state.repoTab = 'code';
  state.synced = false;
  save();
  updateStudio();
  updateMentor();
}
function requestScope(scope) {
  if (!scopes.includes(scope) || state.access === 'none' || runtime.operation) return;
  if (scope === 'public' || state.access === 'combined') {
    applyScope(scope);
    return;
  }
  updateStudio();
  showModal(t('privacy.repoTitle'),paragraph('privacy.repoBody'),t('privacy.allowRepo'),() => {
    state.access = 'combined';
    applyScope(scope);
  });
}

function privateConsent(selectSource=false) {
  if (state.access !== 'combined' || runtime.privateAI) return;
  showModal(t('privacy.aiStepOne'),paragraph('privacy.aiStepOneCopy'),t('action.continue'),() => {
    showModal(t('privacy.aiStepTwo'),paragraph('privacy.aiStepTwoCopy')
      + '<label class="option-row"><input type="checkbox" name="agree" required><span>' + escape(t('privacy.aiCheckbox')) + '</span></label>',
      t('action.confirm'),() => {
        if (state.access !== 'combined') return;
        runtime.privateAI = true;
        if (selectSource) runtime.chosen.add('private');
        audit('audit.approved');
        updateStudio();
        updateMentor();
      });
    return false;
  });
}
function revokePrivate() {
  runtime.privateAI = false;
  runtime.chosen.delete('private');
  clearChat();
}

function openEvidence(id,{tab='code',reference=null,fromMentor=false}={}) {
  const repo = scoredRepos(state).find(item => item.id === id);
  if (!repo || (reference && !matchesCodeReference(repo,reference))) {
    notify('repos.evidenceUnavailable');
    return;
  }
  if (runtime.operation?.kind === 'analysis' && runtime.operation.id !== repo.id) {
    notify('analysis.waitRepo');
    return;
  }
  if (compactMentor.matches && fromMentor) closeMentor();
  state.repo = repo.id;
  state.repoTab = tab;
  runtime.evidenceFocus = tab === 'code' ? repo.id : null;
  save();
  navigate('repos',tab === 'collab' ? '#repo-details' : '#repo-evidence');
}

function selectRepository(id) {
  if (runtime.operation?.kind === 'analysis') return;
  if (!currentRepos(state).some(repo => repo.id === id)) return;
  state.repo = id;
  state.repoTab = 'code';
  runtime.evidenceFocus = null;
  save();
  updateStudio();
}

function askMetric(key) {
  if (!radarMetrics.includes(key)) return;
  openMentor();
  sendChat(t('mentor.qMetric',{name:t('metric.' + key)}),{...mentorContext(),requestedMetric:key},null);
}

function selectMilestone(index,goal=state.goal,jump=false) {
  if (!Object.hasOwn(paths,goal) || !paths[goal][index]) return;
  if (goal !== state.goal) {
    state.goal = goal;
    save();
  }
  runtime.milestone = index;
  navigate('roadmap',jump ? '#milestone-detail' : undefined);
}

function toggleComplete() {
  const index = runtime.milestone;
  const status = stateOf(state,index);
  if (status === 'locked') return;
  if (status === 'done') {
    const affected = dependentMilestones(state,index).slice(1);
    const text = affected.length ? t('road.undoCopy',{names:affected.map(i => milestoneText(state.goal,i)).join(', ')}) : t('road.undoSingle');
    showModal(t('road.undoQ'),'<p>' + escape(text) + '</p>',t('road.undo'),() => {
      undoMilestone(state,index);
      runtime.roadUnlock = null;
      save();
      updateStudio();
      notify('road.historyUndo',{name:milestoneText(state.goal,index,'achievement')});
    });
    return;
  }
  if (checklist(state,index).some(item => !item.done)) return;
  const previousLink = planFor(state).awards[index]?.link ?? '';
  const locked = milestonesFor(state).map((_,i) => i).filter(i => stateOf(state,i) === 'locked');
  showModal(t('road.recordTitle'),paragraph('road.recordCopy')
    + '<label class="field"><span>' + escape(t('road.optionalLink')) + '</span><input type="url" name="evidence" maxlength="900"'
    + ' placeholder="https://" value="' + escape(previousLink) + '"></label>',
    t('road.complete'),(values,form) => {
      const raw = String(values.get('evidence') ?? '').trim();
      const url = raw ? evidenceURL(raw) : null;
      if (raw && !url) {
        form.elements.evidence.setCustomValidity(t('road.https'));
        form.elements.evidence.reportValidity();
        return false;
      }
      if (!completeMilestone(state,index,url)) return;
      const unlocked = locked.filter(i => stateOf(state,i) === 'ready');
      runtime.roadUnlock = {goal:state.goal,completed:index,indices:unlocked};
      save();
      updateStudio();
      $('#milestone-detail .milestone-proof')?.classList.add('award-earned');
      $('.milestone-pips [data-step="' + index + '"]')?.classList.add('completed-now');
      $('.award-card[data-id="' + index + '"]')?.classList.add('award-earned');
      unlocked.forEach(i => $('.node[data-id="' + i + '"]')?.classList.add('milestone-unlocked'));
      stopRoadAnimation = animateUnlock($('.road-map'),state,index,unlocked,reduced);
      const name = milestoneText(state.goal,index,'achievement');
      notify(unlocked.length ? 'road.unlockNext' : 'road.unlocked',
        {name,next:unlocked.map(i => milestoneText(state.goal,i)).join(', ')});
    });
}

function draftRoadmap() {
  const {snapshot,previous,index,source,task} = recommendationFor(state);
  const goal = state.goal;
  if (index < 0) {
    notify('road.finished');
    return;
  }
  const delta = compareSnapshots(snapshot,previous);
  const copy = delta === null ? '' : delta === 0 ? t('analysis.same',{score:snapshot.score})
    : t('analysis.changed',{delta:(delta > 0 ? '+' : '') + delta});
  const report = snapshot ? '<small>' + escape(t('road.reportDate',{date:dateLabel(snapshot.at)})) + '</small>' : '';
  const description = source
    ? '<div class="notice"><strong>' + escape(t('road.proposalSource')) + '</strong><code>' + escape(source.file + ' · ' + source.commit)
      + '</code>' + report + (copy ? '<p>' + escape(copy) + '</p>' : '') + '</div>'
    : paragraph('road.proposalNoEvidence');
  showModal(t('road.proposal'),'<p><strong>' + escape(milestoneText(goal,index)) + '</strong></p><p>'
    + escape(taskLabel(task)) + '</p>' + description + paragraph('road.proposalCopy'),t('road.apply'),() => {
      if (state.goal !== goal || stateOf(state,index) !== 'ready') return;
      const added = addRoadTask(state,index,task);
      if (snapshot) planFor(state).reviewed.push(snapshot.id);
      save();
      selectMilestone(index);
      notify(added ? 'road.applied' : 'road.alreadyAdded',{name:milestoneText(goal,index)});
    });
}

function confirmAgent(id) {
  const reply = runtime.messages.find(msg => (String(msg.id) === id || String(msg.action?.id) === id) && msg.action && !msg.actionApplied);
  if (!reply) return;
  const {goal,i,task} = reply.action;
  showModal(t('mentor.agentTitle'),'<p>' + escape(t('mentor.agentCopy',{name:milestoneText(goal,i)}))
    + '</p><div class="notice">' + escape(taskLabel(task)) + '</div>' + paragraph('mentor.agentSource'),t('mentor.addConfirm'),() => {
      if (!runtime.messages.includes(reply) || !runtime.chosen.has('roadmap') || goal !== state.goal || stateOf(state,i) !== 'ready') {
        notify('mentor.agentLocked');
        return;
      }
      const added = addRoadTask(state,i,task);
      reply.actionApplied = true;
      if (added) audit('audit.agent',{goal,i});
      if (isStudio('roadmap') || isStudio('data')) updateStudio();
      updateMentor();
      notify(added ? 'road.applied' : 'road.alreadyAdded',{name:milestoneText(goal,i)});
    },{
      onDecline:() => {
        reply.actionDismissed = true;
        audit('audit.declined');
        if (isStudio('data')) updateStudio();
        updateMentor();
        notifyText('Đã từ chối đề xuất.');
      },
      declineLabel:'Từ chối',
      cancelLabel:'Để sau (Hủy)',
      onCancel:() => {
        notifyText('Đã đóng hộp thoại. Đề xuất vẫn được giữ để bạn suy nghĩ thêm.');
        updateMentor();
      }
    });
}

function shareStart() {
  const eligible = scoredRepos({...state,scope:'public'});
  const preview = '<div class="notice"><strong>' + escape(sampleUser.name + ' · ' + sampleUser.handle) + '</strong><span>'
    + escape(eligible.map(repo => repo.name).join(', ') || t('data.shareNoRepos')) + '</span></div>';
  const checkbox = (name,label,checked=false) => '<label class="option-row"><input type="checkbox" name="'
    + name + '"' + (checked ? ' checked' : '') + '><span>' + escape(t(label)) + '</span></label>';
  showModal(t('data.sharePreview'),preview + checkbox('repos','data.sharePublicRepos',true)
    + checkbox('scores','data.sharePublicScores') + checkbox('skills','profile.self') + paragraph('data.shareIntro'),t('data.shareCreate'),form => {
      const share = {
        id:crypto.randomUUID(), repos:form.has('repos') ? eligible.map(repo => repo.name) : [],
        scores:form.has('scores') ? eligible.map(repo => ({repo:repo.id,score:repo.score})) : [],
        declared:form.has('skills') ? [...state.skillBasis] : []
      };
      if (!share.repos.length && !share.scores.length && !share.declared.length) {
        notify('data.shareSelect');
        return false;
      }
      state.share = share;
      save();
      updateStudio();
      notify('data.shareCreated');
    });
}

function exportCV() {
  const {name,role,body} = runtime.cvDraft;
  if (!body.trim()) { notify('cv.needContent'); return; }
  const url = URL.createObjectURL(new Blob([name,'\n',role,'\n\n',body,'\n'],{type:'text/plain;charset=utf-8'}));
  const download = document.createElement('a');
  download.href = url;
  download.download = 'IT-Talent-CV.txt';
  download.click();
  setTimeout(() => URL.revokeObjectURL(url),1500);
}
function previewCV() {
  try {
    if (state.template === 'reference') {
      const paper = $('.cv-paper');
      if (paper) {
        paper.outerHTML = renderReferenceCV(runtime.cvDraft);
      }
      return;
    }
    const {name,role,body} = runtime.cvDraft;
    const nameEl = $('#cv-name');
    const roleEl = $('#cv-role');
    const bodyEl = $('#cv-body');
    if (nameEl) nameEl.textContent = name;
    if (roleEl) roleEl.textContent = role;
    if (bodyEl) bodyEl.textContent = body || t('cv.empty');
  } catch (err) {
    console.error('Error in previewCV:', err);
  }
}

function syncStructuredForm() {
  const form = document.querySelector('#cv-form');
  if (!form) return;

  // Round-trip parse the existing draft body so non-focused sections are NEVER wiped
  const structured = parseCVForReference(runtime.cvDraft.body, runtime.cvDraft.name, runtime.cvDraft.role);
  if (!Array.isArray(structured.sections)) structured.sections = [];

  // Update contact if contact field exists in DOM
  const contactInput = form.querySelector('input[name="cv-struct-contact"]');
  if (contactInput) {
    structured.contact = contactInput.value;
  }

  // Update focused section if currently editing a specific section
  const focusedEditor = form.querySelector('.cv-focused-sec-editor');
  if (focusedEditor) {
    const titleInput = focusedEditor.querySelector('.cv-struct-title');
    const entryEls = focusedEditor.querySelectorAll('.cv-struct-entry');
    const sIdxAttr = focusedEditor.querySelector('[data-sec]')?.dataset.sec ?? (live?.data?.activeSection ?? -1);
    const sIdx = Number(sIdxAttr);
    if (sIdx >= 0 && structured.sections[sIdx]) {
      if (titleInput && titleInput.value.trim()) {
        structured.sections[sIdx].title = titleInput.value.trim();
      }
      const updatedEntries = [];
      entryEls.forEach(entryEl => {
        const type = entryEl.dataset.type;
        if (type === 'dated') {
          const date = entryEl.querySelector('[data-field="date"]')?.value || '';
          const org = entryEl.querySelector('[data-field="org"]')?.value || '';
          const role = entryEl.querySelector('[data-field="role"]')?.value || '';
          const loc = entryEl.querySelector('[data-field="loc"]')?.value || '';
          const bulletsText = entryEl.querySelector('[data-field="bullets"]')?.value || '';
          const bullets = bulletsText.split('\n').map(b => b.trim().replace(/^[-•*]\s*/, '')).filter(Boolean);
          updatedEntries.push({ type: 'dated', date, org, role, loc, bullets });
        } else if (type === 'labeled') {
          const label = entryEl.querySelector('[data-field="label"]')?.value || '';
          const content = entryEl.querySelector('[data-field="content"]')?.value || '';
          updatedEntries.push({ type: 'labeled', label, content, bullets: [] });
        } else {
          const text = entryEl.querySelector('[data-field="text"]')?.value || '';
          updatedEntries.push({ type: 'text', text, bullets: [] });
        }
      });
      structured.sections[sIdx].entries = updatedEntries;
    }
  }

  // Also support full section list if ever rendered simultaneously
  const secEls = form.querySelectorAll('.cv-struct-section-full');
  if (secEls.length > 0) {
    const sections = [];
    secEls.forEach(secEl => {
      const title = secEl.querySelector('.cv-struct-title')?.value || '';
      const entries = [];
      secEl.querySelectorAll('.cv-struct-entry').forEach(entryEl => {
        const type = entryEl.dataset.type;
        if (type === 'dated') {
          const date = entryEl.querySelector('[data-field="date"]')?.value || '';
          const org = entryEl.querySelector('[data-field="org"]')?.value || '';
          const role = entryEl.querySelector('[data-field="role"]')?.value || '';
          const loc = entryEl.querySelector('[data-field="loc"]')?.value || '';
          const bulletsText = entryEl.querySelector('[data-field="bullets"]')?.value || '';
          const bullets = bulletsText.split('\n').map(b => b.trim().replace(/^[-•*]\s*/, '')).filter(Boolean);
          entries.push({ type: 'dated', date, org, role, loc, bullets });
        } else if (type === 'labeled') {
          const label = entryEl.querySelector('[data-field="label"]')?.value || '';
          const content = entryEl.querySelector('[data-field="content"]')?.value || '';
          entries.push({ type: 'labeled', label, content, bullets: [] });
        } else {
          const text = entryEl.querySelector('[data-field="text"]')?.value || '';
          entries.push({ type: 'text', text, bullets: [] });
        }
      });
      if (title || entries.length) sections.push({ title, entries });
    });
    if (sections.length > 0) structured.sections = sections;
  }

  runtime.cvDraft.body = serializeCVFromSections(structured);
  const rawTextarea = form.querySelector('textarea[name="body"]');
  if (rawTextarea) rawTextarea.value = runtime.cvDraft.body;
  runtime.cvEdited = true;
  runtime.atsChecked = false;
  if (live) live.data.ats = null;
  $('#ats-result')?.replaceChildren();
  previewCV();
}
function checkCV() {
  runtime.atsChecked = true;
  updateStudio();
}
function leaveStudio() {
  cancelOperation();
  closeMentor();
  revokePrivate();
  setSession(false);
  state.access = 'public';
  state.scope = 'public';
  state.synced = false;
  runtime.chosen = new Set(initialSources);
  runtime.evidenceFocus = null;
  runtime.roadUnlock = null;
  runtime.sourcesOpen = false;
  save();
  location.hash = 'about';
}
function updateLanguage(next) {
  if (getLanguage() === next) return;
  setLanguage(next);
  document.documentElement.lang = next;
  $('#toast').hidden = true;
  if (!runtime.cvEdited) runtime.cvDraft = defaultCV();
  renderRoute(true);
}

function refreshTheme(editing=null) {
  applyTheme(theme);
  refreshBotColors(document);
  if (isStudio('settings')) syncThemeControls($('#main-view'),theme,editing);
  radar?.repaint();
  if (isStudio('roadmap')) paintMap($('.road-map'),state);
}

function changeTheme(next,editing=null) {
  theme = next;
  saveTheme(theme);
  refreshTheme(editing);
}

function changeThemeColor(control,commit) {
  const field = control.dataset.themeColor;
  if (!colorFields.includes(field) || !isStudio('settings')) return;
  const color = hexColor(control.value,commit);
  if (!color) {
    control.setAttribute('aria-invalid','true');
    if (commit) notify('theme.invalid');
    return;
  }
  control.removeAttribute('aria-invalid');
  const custom = {...themeColors(theme),[field]:color};
  changeTheme({preset:'custom',custom},commit ? null : control);
}

const actions = {
  enter,
  'copy-code':button => {
    const codeBlock = button.closest('.chat-code-wrapper')?.querySelector('code');
    if (codeBlock && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(codeBlock.innerText).then(() => {
        const prev = button.innerText;
        button.innerText = 'Đã chép!';
        setTimeout(() => { button.innerText = prev; }, 1800);
      }).catch(() => {});
    }
  },
  'scope-option':button => {
    const dropdown = button.closest('details');
    dropdown.open = false;
    dropdown.querySelector('summary').focus();
    if (button.dataset.id !== state.scope) requestScope(button.dataset.id);
  },
  'range-option':button => {
    const range = Number(button.dataset.id);
    if (runtime.operation || !ranges.includes(range)) return;
    const dropdown = button.closest('details');
    dropdown.open = false;
    dropdown.querySelector('summary').focus();
    if (range === state.range) return;
    clearChat(true);
    state.range = range;
    state.synced = false;
    runtime.evidenceFocus = null;
    runtime.radarAxis = null;
    save();
    updateStudio();
  },
  'show-mentor-preview':() => aboutMotion?.showReply(),
  oauth:() => showModal(t('login.github'),paragraph('login.setup'),t('login.sample'),enter),
  language:button => updateLanguage(button.dataset.id),
  'theme-preset':button => {
    const {id} = button.dataset;
    if (Object.hasOwn(presets,id) || id === 'custom' && theme.custom) changeTheme({...theme,preset:id});
  },
  'theme-reset':() => changeTheme({preset:defaultPreset,custom:null}),
  logout:leaveStudio,
  'toggle-mentor':() => runtime.mentorOpen ? closeMentor(true) : openMentor(),
  'close-mentor':() => closeMentor(true),
  'toggle-sources':() => {
    runtime.sourcesOpen = !runtime.sourcesOpen;
    updateMentor();
  },
  'new-chat':() => {
    clearChat();
    $('#mentor-question')?.focus({preventScroll:true});
  },
  prompt:button => sendChat(t(button.dataset.id)),
  'agent-preview':button => confirmAgent(button.dataset.id),
  'agent-decline':button => {
    const reply = runtime.messages.find(msg => (String(msg.id) === button.dataset.id || String(msg.action?.id) === button.dataset.id) && msg.action);
    if (reply) {
      reply.actionDismissed = true;
      audit?.('audit.declined');
      notifyText('Đã từ chối đề xuất.');
      updateMentor();
    }
  },
  'agent-reconsider':button => {
    const reply = runtime.messages.find(msg => (String(msg.id) === button.dataset.id || String(msg.action?.id) === button.dataset.id) && msg.action);
    if (reply) {
      reply.actionDismissed = false;
      updateMentor();
    }
  },
  'score-tab':button => { runtime.scoreTab = button.dataset.id; updateStudio(); },
  score:button => { state.focusScore = button.dataset.id; save(); updateStudio(); },
  'role-score':button => { runtime.roleIndex = button.dataset.id; updateStudio(); },
  evidence:button => {
    const {id,message,file,commit,start,end} = button.dataset;
    const reference = message ? runtime.messages.find(item => String(item.id) === message)?.source?.snippet
      : file ? {repoId:id,file,commit,start:Number(start),end:Number(end)} : null;
    if (message && !reference) return;
    openEvidence(id,{reference,fromMentor:mentorPanel.contains(button)});
  },
  'metric-evidence':button => openEvidence(button.dataset.id,{tab:button.dataset.tab}),
  'ask-metric':button => askMetric(button.dataset.id),
  'radar-source':button => {
    const metric = button.dataset.id;
    const index = radarMetrics.indexOf(metric);
    if (index < 0) return;
    if (compactMentor.matches) closeMentor();
    runtime.radarAxis = index;
    navigate('dashboard','#radar-detail-' + metric);
  },
  'ask-snippet':button => {
    const repo = scoredRepos(state).find(item => item.id === button.dataset.id);
    if (!repo) return;
    runtime.chatSnippet = codeReference(repo);
    openMentor();
    updateMentor(true);
  },
  'remove-snippet':() => {
    runtime.chatSnippet = null;
    updateMentor(true);
  },
  'ask-evidence':button => {
    const repo = scoredRepos(state).find(item => item.id === button.dataset.id);
    if (!repo) return;
    openMentor();
    sendChat(t('mentor.qEvidence'),{...mentorContext(),repoId:repo.id},null);
  },
  repo:button => selectRepository(button.dataset.id),
  'repo-tab':button => { state.repoTab = button.dataset.id; save(); updateStudio(); },
  sync,
  analyze,
  'cancel-analysis':() => {
    if (runtime.operation?.kind !== 'analysis') return;
    cancelOperation();
    updateStudio();
    notify('analysis.canceled');
  },
  milestone:button => {
    const fromMentor = mentorPanel.contains(button);
    const inMap = Boolean(button.closest('.road-map'));
    if (compactMentor.matches && fromMentor) closeMentor();
    selectMilestone(Number(button.dataset.id),button.dataset.goal,fromMentor || !inMap || $('.workspace-content').clientWidth <= 790);
  },
  'focus-milestone':button => selectMilestone(Number(button.dataset.id),state.goal,true),
  complete:toggleComplete,
  'ask-step':() => {
    openMentor();
    sendChat(t('road.ask',{name:milestoneText(state.goal,runtime.milestone)}),mentorContext(),null);
  },
  'road-draft':draftRoadmap,
  'use-job':button => {
    const job = jobs.find(item => item.id === button.dataset.id);
    if (!job) return;
    state.job = job;
    runtime.atsChecked = false;
    save();
    updateStudio();
  },
  'save-job':button => {
    const id = button.dataset.id;
    const saved = state.savedJobs.includes(id);
    state.savedJobs = saved ? state.savedJobs.filter(item => item !== id) : [...state.savedJobs,id];
    save();
    updateStudio();
    notify(saved ? 'jobs.unsaved' : 'jobs.saved');
  },
  'remove-skill':button => {
    state.skillBasis = state.skillBasis.filter(skill => skill !== button.dataset.id);
    state.claimEvidence = state.claimEvidence.filter(item => item.skill !== button.dataset.id);
    save();
    updateStudio();
  },
  'cv-example':() => {
    runtime.cvDraft.body = t('cv.exampleBody');
    runtime.cvEdited = true;
    runtime.atsChecked = false;
    updateStudio();
  },
  'cv-template':button => { state.template = button.dataset.id; save(); updateStudio(); },
  'cv-intel-tab': button => { runtime.intelTab = button.dataset.id; updateStudio(); },
  'cv-editor-mode': button => { runtime.editorMode = button.dataset.id; updateStudio(); },
  'cv-zoom': button => { runtime.zoomLevel = button.dataset.id; updateStudio(); },
  'cv-zoom-panel': button => { runtime.zoomLevel = button.dataset.id; updateStudio(); },
  'cv-toggle-intel': () => { runtime.rightPanelCollapsed = !runtime.rightPanelCollapsed; updateStudio(); },
  'cv-del-entry': button => {
    const sIdx = Number(button.dataset.sec);
    const eIdx = Number(button.dataset.entry);
    const structured = parseCVForReference(runtime.cvDraft.body, runtime.cvDraft.name, runtime.cvDraft.role);
    if (structured.sections?.[sIdx]?.entries) {
      structured.sections[sIdx].entries.splice(eIdx, 1);
      runtime.cvDraft.body = serializeCVFromSections(structured);
      runtime.cvEdited = true;
      updateStudio();
    }
  },
  'cv-del-section': button => {
    const sIdx = Number(button.dataset.sec);
    const structured = parseCVForReference(runtime.cvDraft.body, runtime.cvDraft.name, runtime.cvDraft.role);
    if (structured.sections?.[sIdx]) {
      structured.sections.splice(sIdx, 1);
      runtime.cvDraft.body = serializeCVFromSections(structured);
      runtime.cvEdited = true;
      if (runtime.activeSection === sIdx) {
        runtime.activeSection = null;
      } else if (runtime.activeSection > sIdx) {
        runtime.activeSection -= 1;
      }
      updateStudio();
    }
  },
  'live-cv-select': button => {
    button.closest('details')?.removeAttribute('open');
    const id = Number(button.dataset.id);
    const item = runtime.cvList?.find(c => c.id === id);
    if (item) {
      runtime.cvDraft = { name: item.name || '', role: item.role || '', body: item.body || '' };
      runtime.cv = item;
      updateStudio();
    }
  },
  'live-document-select': button => {
    button.closest('details')?.removeAttribute('open');
    const docId = button.dataset.id;
    const item = runtime.documentList?.find(d => d.document_id === docId);
    if (item) {
      runtime.document = item;
      updateStudio();
    }
  },
  'live-version-select': button => {
    button.closest('details')?.removeAttribute('open');
    updateStudio();
  },
  'road-goal-select': button => {
    button.closest('details')?.removeAttribute('open');
    const goal = button.dataset.id;
    if (goal && Object.hasOwn(paths, goal)) {
      state.goal = goal;
      runtime.milestone = Math.max(0, nextStep(state));
      save();
      updateStudio();
    }
  },
  'road-select-option': button => {
    button.closest('details')?.removeAttribute('open');
    updateStudio();
  },
  'cv-add-entry': button => {
    const sIdx = Number(button.dataset.sec);
    const structured = parseCVForReference(runtime.cvDraft.body, runtime.cvDraft.name, runtime.cvDraft.role);
    if (structured.sections?.[sIdx]) {
      const firstEntry = structured.sections[sIdx].entries?.[0];
      const type = firstEntry ? firstEntry.type : 'dated';
      let newEntry = { type, bullets: [] };
      if (type === 'dated') {
        newEntry = { type: 'dated', date: '', org: 'Tên công ty / Trường', role: 'Vị trí công việc', loc: 'Địa điểm', bullets: ['Mô tả kết quả đạt được...'] };
      } else if (type === 'labeled') {
        newEntry = { type: 'labeled', label: 'Kỹ năng mới:', content: 'Công nghệ 1, 2...', bullets: [] };
      } else {
        newEntry = { type: 'text', text: 'Nội dung chi tiết...', bullets: [] };
      }
      if (!Array.isArray(structured.sections[sIdx].entries)) structured.sections[sIdx].entries = [];
      structured.sections[sIdx].entries.push(newEntry);
      runtime.cvDraft.body = serializeCVFromSections(structured);
      runtime.cvEdited = true;
      updateStudio();
    }
  },
  'cv-add-section': button => {
    const type = button.dataset.type || 'Custom';
    const structured = parseCVForReference(runtime.cvDraft.body, runtime.cvDraft.name, runtime.cvDraft.role);
    if (!Array.isArray(structured.sections)) structured.sections = [];
    let title = 'MỤC TÙY CHỌN';
    let entry = { type: 'dated', bullets: [] };
    if (type === 'Experience') {
      title = 'KINH NGHIỆM LÀM VIỆC';
      entry = { type: 'dated', date: '', org: 'Tên công ty', role: 'Vị trí công việc', loc: '', bullets: [] };
    } else if (type === 'Projects') {
      title = 'DỰ ÁN TIÊU BIỂU';
      entry = { type: 'dated', date: '', org: 'Tên dự án', role: 'Vai trò của bạn', loc: 'GitHub', bullets: [] };
    } else if (type === 'Skills') {
      title = 'KỸ NĂNG CHUYÊN MÔN';
      entry = { type: 'labeled', label: 'Ngôn ngữ & Framework:', content: '', bullets: [] };
    } else if (type === 'Education') {
      title = 'HỌC VẤN & BẰNG CẤP';
      entry = { type: 'dated', date: '', org: 'Đại học', role: 'Tên bằng cấp', loc: '', bullets: [] };
    } else {
      entry = { type: 'text', text: 'Nội dung chi tiết...', bullets: [] };
    }
    structured.sections.push({ title, entries: [entry] });
    runtime.cvDraft.body = serializeCVFromSections(structured);
    runtime.cvEdited = true;
    updateStudio();
  },
  'cv-export':exportCV,
  'cv-print':() => { document.body.classList.add('print-cv'); window.print(); },
  'cv-check':checkCV,
  'private-ai':() => privateConsent(),
  'revoke-ai':() => {
    revokePrivate();
    audit('audit.revoked');
    updateStudio();
    notify('privacy.aiRevoked');
  },
  reconnect:() => {
    cancelOperation();
    state.access = 'public';
    state.scope = 'public';
    state.synced = false;
    revokePrivate();
    save();
    updateStudio();
    notify('repos.connected');
  },
  disconnect:() => showModal(t('privacy.disconnectQ'),paragraph('privacy.disconnectCopy'),t('privacy.disconnect'),() => {
    cancelOperation();
    state.access = 'none';
    state.scope = 'public';
    state.synced = false;
    revokePrivate();
    save();
    updateStudio();
    notify('privacy.disconnected');
  },{tone:'danger'}),
  'share-start':shareStart,
  'copy-share':async () => {
    const input = $('#share-link');
    if (!input) return;
    try {
      await navigator.clipboard.writeText(input.value);
      notify('data.shareCopied');
    } catch {
      input.select();
      notify('data.shareSelected');
    }
  },
  'revoke-share':() => showModal(t('data.shareRevokeQ'),paragraph('data.shareRevokeCopy'),t('data.shareRevoke'),() => {
    state.share = null;
    save();
    updateStudio();
    notify('data.shareRevoked');
  },{tone:'danger'})
};

document.addEventListener('click',event => {
  document.querySelectorAll('.filter-dropdown[open]').forEach(dropdown => {
    if (!dropdown.contains(event.target)) dropdown.open = false;
  });
  if (event.target.closest('.skip-link')) {
    event.preventDefault();
    focusMain();
    return;
  }
  if (runtime.mentorOpen && compactMentor.matches
    && event.target.closest('.studio-settings, .studio-menu a, .sidebar > .brand')) closeMentor();
  const trigger = event.target.closest('[data-act]');
  if (trigger && !trigger.disabled) {
    const action = live?.actions[trigger.dataset.act] ?? actions[trigger.dataset.act];
    action?.(trigger);
  }
});

document.addEventListener('keydown',event => {
  if (event.key !== 'Escape') return;
  const dropdown = event.target.closest('.filter-dropdown[open]');
  if (!dropdown) return;
  dropdown.open = false;
  dropdown.querySelector('summary')?.focus();
});

document.addEventListener('change',async event => {
  const control = event.target;
  if (control.dataset.themeColor) {
    changeThemeColor(control,true);
    return;
  }
  if (live?.change(control)) return;
  if (control.id === 'repo-switch') selectRepository(control.value);
  if (control.id === 'road-goal' && Object.hasOwn(paths,control.value)) {
    state.goal = control.value;
    runtime.milestone = Math.max(0,nextStep(state));
    save();
    updateStudio();
  }
  if (control.name === 'mentor-source') {
    if (control.checked && control.value === 'private' && !runtime.privateAI) {
      control.checked = false;
      if (state.access === 'combined') privateConsent(true);
      else notify('mentor.privateFirst');
    } else {
      if (control.checked) runtime.chosen.add(control.value);
      else runtime.chosen.delete(control.value);
      updateMentor();
    }
  }
  if (control.name === 'simulate-error') { state.simulateFailure = control.checked; save(); }
  if (control.classList.contains('road-criterion')) {
    setChecklist(state,runtime.milestone,control.value,control.checked);
    save();
    updateStudio();
  }
  if (control.classList.contains('road-task')) {
    const note = planFor(state).notes.find(item => item.id === control.value);
    if (note && stateOf(state,note.i) !== 'locked') {
      note.done = control.checked;
      save();
    }
  }
  if (control.id === 'cv-upload') {
    const file = control.files[0];
    if (!file) return;
    if (!/\.(txt|md)$/i.test(file.name) || file.size > 100000) {
      notify('cv.fileRule');
      control.value = '';
      return;
    }
    try {
      const text = await file.text();
      if (!signedIn) return;
      runtime.cvDraft.body = text.slice(0,6000);
      runtime.cvEdited = true;
      runtime.atsChecked = false;
      if (isStudio('cv')) updateStudio();
      notify('cv.imported');
    } catch {
      notify('cv.failed');
    }
  }
});

document.addEventListener('input',event => {
  const control = event.target;
  if (control.dataset.themeColor) {
    changeThemeColor(control,false);
    return;
  }
  if (control.name === 'question') runtime.chatDraft = control.value;
  if (live) {
    if (control.name === 'query') live.data.jobQuery = control.value;
    if (control.name === 'jd' && control.closest('#jd-form')) live.data.jobText = control.value;
    if (control.name === 'jd-url') live.data.jobURL = control.value;
    if (control.name === 'ats-jd') live.data.atsJD = control.value;
    if (control.name === 'mentor-jd') live.data.mentorJD = control.value;
  }
  if (control.name === 'evidence') control.setCustomValidity('');
  const paper = control.closest?.('.cv-paper');
  if (paper) {
    runtime.cvEdited = true;
    runtime.atsChecked = false;
    if (live) live.data.ats = null;
    $('#ats-result')?.replaceChildren();

    const nameEl = paper.querySelector('#cv-name');
    const roleEl = paper.querySelector('#cv-role');
    const bodyEl = paper.querySelector('#cv-body');

    if (nameEl && (control === nameEl || nameEl.contains(control))) {
      runtime.cvDraft.name = nameEl.innerText.trim();
      const input = document.querySelector('#cv-form input[name="name"]');
      if (input && input !== control) input.value = runtime.cvDraft.name;
    }
    if (roleEl && (control === roleEl || roleEl.contains(control))) {
      runtime.cvDraft.role = roleEl.innerText.trim();
      const input = document.querySelector('#cv-form input[name="role"]');
      if (input && input !== control) input.value = runtime.cvDraft.role;
    }
    if (bodyEl && (control === bodyEl || bodyEl.contains(control))) {
      runtime.cvDraft.body = bodyEl.innerText.trim();
      const textarea = document.querySelector('#cv-form textarea[name="body"]');
      if (textarea && textarea !== control) textarea.value = runtime.cvDraft.body;
    }
    return;
  }
  if (control.closest('#cv-form')) {
    if (control.classList.contains('cv-struct-field') || control.name === 'cv-struct-contact') {
      syncStructuredForm();
      return;
    }
    if (Object.hasOwn(runtime.cvDraft,control.name)) {
      runtime.cvDraft[control.name] = control.value;
      runtime.cvEdited = true;
      runtime.atsChecked = false;
      if (live) live.data.ats = null;
      $('#ats-result')?.replaceChildren();
      previewCV();
    }
  }
  if (control.name === 'jd' && control.closest('#jd-form')) resizeJDTextarea(control);
  if (control.name === 'jd') runtime.jdText = control.value;
  if (control.name === 'query') runtime.jobQuery = control.value;
});

document.addEventListener('submit',event => {
  const form = event.target;
  if (form.method === 'dialog') return;
  event.preventDefault();
  const values = new FormData(form);
  if (form.classList.contains('chat-form')) sendChat(String(values.get('question') ?? ''));
  if (live) {
    void live.forms[form.id]?.(values, form);
    return;
  }
  if (form.id === 'skill-form') {
    const value = String(values.get('skill') ?? '').trim();
    if (!value || state.skillBasis.some(skill => skill.toLowerCase() === value.toLowerCase())) {
      notify('profile.skillDuplicate');
      return;
    }
    const evidence = String(values.get('evidence') ?? '').trim();
    const url = evidenceURL(evidence);
    if (evidence && !url) {
      form.elements.evidence.setCustomValidity(t('road.https'));
      form.elements.evidence.reportValidity();
      return;
    }
    state.skillBasis.push(value);
    if (url) state.claimEvidence.push({skill:value,url});
    save();
    updateStudio();
    notify('profile.skillAdded');
  }
  if (form.id === 'job-search') {
    runtime.jobQuery = String(values.get('query') ?? '').slice(0,100);
    updateStudio();
  }
  if (form.id === 'jd-form') {
    const text = String(values.get('jd') ?? '').trim();
    if (!text) { notify('jobs.enter'); return; }
    const needs = wordsIn(text).join(', ');
    showModal(t('jobs.review'),paragraph('jobs.reviewCopy') + '<label class="field"><span>' + escape(t('jobs.reviewSkills'))
      + '</span><textarea name="required-skills" rows="3" maxlength="400">' + escape(needs) + '</textarea></label>',
    t('jobs.matchAction'),values => {
      const unique = new Map();
      for (const part of String(values.get('required-skills') ?? '').split(/[,\n]/)) {
        const skill = part.trim().slice(0,50);
        if (skill && !unique.has(skill.toLowerCase())) unique.set(skill.toLowerCase(),skill);
      }
      state.job = {needs:[...unique.values()].slice(0,20)};
      runtime.atsChecked = false;
      save();
      updateStudio();
      notify('jobs.compared');
    });
  }
  if (form.id === 'cv-form') {
    if (!String(values.get('body')).trim()) { notify('cv.needContent'); return; }
    state.cv = {...runtime.cvDraft};
    save();
    notify('cv.saved');
  }
});

document.addEventListener('keydown',event => {
  const field = event.target;
  if (event.key === 'Enter' && field.dataset.themeColor && field.type === 'text') {
    event.preventDefault();
    changeThemeColor(field,true);
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    const cvForm = document.getElementById('cv-form');
    if (cvForm) {
      event.preventDefault();
      document.querySelector('[data-act="cv-save-bar"]')?.click();
      return;
    }
  }
  if (event.defaultPrevented || event.key !== 'Escape') return;
  if (dialog.open) return;
  if (live && live.data) {
    if (live.data.previewOnly) {
      event.preventDefault();
      live.data.previewOnly = false;
      live.render();
      setTimeout(live.updateCVFitScale, 50);
      return;
    }
    if (live.data.focusMode) {
      event.preventDefault();
      live.data.focusMode = false;
      runtime.cvFocusMode = false;
      try { localStorage.setItem('cv_focus_mode', '0'); } catch (_) {}
      document.querySelector('.studio')?.classList.remove('cv-focus-mode');
      document.body.classList.remove('cv-focus-mode');
      live.render();
      setTimeout(live.updateCVFitScale, 50);
      return;
    }
  }
  if (!runtime.mentorOpen) return;
  event.preventDefault();
  closeMentor(true);
});
window.addEventListener('resize', () => {
  if (isStudio('jobs')) resizeJDTextarea();
});
window.addEventListener('afterprint',() => document.body.classList.remove('print-cv'));
window.addEventListener('hashchange',() => {
  const previous = route;
  const focusWasInMentor = mentorPanel.contains(document.activeElement);
  if (location.hash !== '#studio/cv') {
    document.querySelector('.studio')?.classList.remove('cv-focus-mode');
    document.body.classList.remove('cv-focus-mode');
    if (live && live.data) {
      live.data.focusMode = false;
      live.data.previewOnly = false;
    }
  }
  if (runtime.mentorOpen && compactMentor.matches && location.hash !== '#studio/mentor') closeMentor();
  renderRoute();
  if (location.hash === '#mentor-preview' && route.kind === 'about') {
    $('#mentor-preview')?.scrollIntoView({block:'start'});
    return;
  }
  if (focusJump()) return;
  if (!sameRoute(previous,route) || location.hash === '#about') {
    window.scrollTo({top:0,behavior:'instant'});
    if (!focusWasInMentor || compactMentor.matches) focusMain();
  }
});
window.addEventListener('storage',event => {
  if (!live && event.key === profileKey && route?.kind === 'share') renderRoute(true);
  if (event.key === themeKey) {
    theme = loadTheme();
    refreshTheme();
  }
});
reduced.addEventListener('change',animateMentorFace);
document.addEventListener('visibilitychange',animateMentorFace);
compactMentor.addEventListener('change',() => {
  renderMentorPanel();
  if (runtime.mentorOpen && document.activeElement === document.body) $('#mentor-title')?.focus({preventScroll:true});
});
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    if (location.hash.includes('cv')) {
      event.preventDefault();
      const saveBtn = document.querySelector('.cv-command-actions button[data-act="cv-save-bar"]')
        || document.querySelector('#cv-form button[type="submit"]');
      saveBtn?.click();
    }
  }
});
window.addEventListener('resize', () => {
  if (isStudio('cv')) updateCVFitScale();
});
paintIcons(document.documentElement);
applyTheme(theme);
refreshBotColors(document);
async function start() {
  if (live) {
    const legacy = {
      '/dashboard':'dashboard','/repositories':'repos','/role-scores':'dashboard','/activity':'repos',
      '/analysis':'repos','/job-matching':'jobs','/cvs':'cv','/cvs/references':'cv','/cv-studio':'cv',
      '/ats-review':'cv','/mentor':'mentor','/privacy':'data','/profile-sharing':'data',
      '/ai-audit':'data','/system-status':'status','/roadmap':'roadmap'
    };
    const deepRepo = location.pathname.match(/^\/(?:repositories\/(\d+)\/(?:analysis|activity)|(?:analysis|activity)\/(\d+))\/?$/);
    const share = location.pathname.match(/^\/share\/([A-Za-z0-9_-]+)\/?$/);
    const cleanPath = location.pathname.replace(/\/$/,'');
    const callbackError = new URLSearchParams(location.search).get('auth_error');
    if (deepRepo) live.data.requestedRepo = deepRepo[1] || deepRepo[2];
    const page = deepRepo ? 'repos' : legacy[cleanPath];
    if (share) history.replaceState(null,'','/#share/' + share[1]);
    else if (page && !location.hash) history.replaceState(null,'','/#studio/' + page);
    else if (callbackError) history.replaceState(null,'','/#login');
    signedIn = await live.session();
    if (signedIn) {
      runtime.cvDraft.name = live.data.user.full_name || '';
      const privateReturn = sessionStorage.getItem('ita-studio-private-return');
      if (privateReturn) {
        sessionStorage.removeItem('ita-studio-private-return');
        if (!callbackError) {
          state.scope = 'private';
          history.replaceState(null,'','/#studio/repos');
        }
      }
    }
    document.documentElement.lang = getLanguage();
    if (callbackError) notifyText({
      github_access_denied: copy('Bạn đã từ chối cấp quyền GitHub.', 'You denied GitHub permissions.'),
      oauth_state_invalid: copy('Phiên GitHub đã hết hạn. Hãy đăng nhập lại.', 'GitHub session expired. Please sign in again.'),
      github_account_conflict: copy('GitHub đã liên kết với một tài khoản khác.', 'GitHub is linked to another account.')
    }[callbackError] ?? copy('GitHub chưa hoàn tất đăng nhập. Hãy thử lại.', 'GitHub sign-in not completed. Please try again.'));
  }
  renderRoute();
  if (location.hash === '#mentor-preview') $('#mentor-preview')?.scrollIntoView({block:'start'});
}

void start();
