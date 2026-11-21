import {t} from './i18n.js';

const preference = 'it-talent-pixel:mentor-width-v1';
const minimum = 300;
const defaultWidth = 374;
const compactAt = 344;
const hardMaximum = 552;
const minimumContent = 450;
const comfortableContent = 706;

export function mentorColumns(total, preferred, sidebar, rail, divider, open) {
  const bound = nav => Math.max(minimum,Math.min(hardMaximum,total - nav - divider - minimumContent));
  const panelWidth = Math.min(preferred,bound(rail));
  const centerWithMenu = total - sidebar - divider - panelWidth;
  const compact = open && (panelWidth >= compactAt || centerWithMenu < comfortableContent);
  const maximum = bound(compact ? rail : sidebar);
  return {compact,width:Math.round(Math.min(preferred,maximum)),maximum};
}

export function mountMentorLayout(workspace, compactScreen) {
  const studio = workspace.closest('.studio');
  const toolbar = workspace.querySelector('.workspace-top');
  const body = workspace.querySelector('.workspace-body');
  const splitter = body.querySelector('#mentor-resize');
  let preferred = defaultWidth;
  try {
    const stored = Number(localStorage.getItem(preference));
    if (stored >= minimum && stored <= hardMaximum) preferred = stored;
  } catch {}
  let width = preferred;
  let maximum = hardMaximum;
  let measures;
  let drag = null;
  let frame = 0;
  let pendingWidth;

  function place() {
    const {total,sidebar,rail,divider} = measures;
    const open = !splitter.hidden && !compactScreen.matches;
    const layout = mentorColumns(total,preferred,sidebar,rail,divider,open);
    width = layout.width;
    maximum = layout.maximum;
    studio.classList.toggle('compact-nav',layout.compact);
    body.style.setProperty('--mentor-width',width + 'px');
    splitter.setAttribute('aria-valuemax',String(maximum));
    splitter.setAttribute('aria-valuenow',String(width));
    splitter.setAttribute('aria-valuetext',t('mentor.widthValue',{width}));
  }
  function refresh() {
    const style = getComputedStyle(studio);
    measures = {
      total:studio.clientWidth,
      sidebar:parseFloat(style.getPropertyValue('--side')),
      rail:parseFloat(style.getPropertyValue('--side-rail')),
      divider:parseFloat(style.getPropertyValue('--mentor-divider'))
    };
    workspace.style.setProperty('--toolbar-height',toolbar.offsetHeight + 'px');
    place();
  }
  function readingPosition() {
    const element = body.querySelector('#repo-evidence') ?? body.querySelector('#repo-details');
    if (!element) return null;
    const {top,bottom} = element.getBoundingClientRect();
    return top < window.innerHeight && bottom > toolbar.getBoundingClientRect().bottom ? {element,top} : null;
  }
  function keepReadingPosition(position) {
    if (!position?.element.isConnected) return;
    const drift = position.element.getBoundingClientRect().top - position.top;
    if (Math.abs(drift) < 1) return;
    const viewport = document.scrollingElement;
    const missing = Math.ceil(viewport.scrollTop + drift + viewport.clientHeight - viewport.scrollHeight);
    if (missing > 0) {
      const report = position.element.closest('.repo-layout');
      const existing = parseInt(report.style.getPropertyValue('--reading-space'),10) || 0;
      report.style.setProperty('--reading-space',(existing + missing) + 'px');
    }
    window.scrollBy({top:drift,behavior:'instant'});
  }
  function setWidth(value,position) {
    const {total,rail,divider} = measures;
    const limit = Math.max(minimum,Math.min(hardMaximum,total - rail - divider - minimumContent));
    const next = Math.round(Math.max(minimum,Math.min(value,limit)));
    if (next === preferred) return;
    preferred = next;
    place();
    keepReadingPosition(position);
  }
  function markResizing(resizing) {
    body.classList.toggle('resizing-mentor',resizing);
    studio.classList.toggle('resizing-mentor',resizing);
  }
  function remember() {
    try { localStorage.setItem(preference,String(preferred)); } catch {}
  }

  splitter.addEventListener('pointerdown',event => {
    if (!event.isPrimary || event.button !== 0) return;
    event.preventDefault();
    splitter.focus({preventScroll:true});
    splitter.setPointerCapture(event.pointerId);
    drag = {id:event.pointerId,x:event.clientX,width,position:readingPosition()};
    markResizing(true);
  });
  splitter.addEventListener('pointermove',event => {
    if (drag?.id !== event.pointerId) return;
    pendingWidth = drag.width + drag.x - event.clientX;
    if (!frame) frame = requestAnimationFrame(() => {
      frame = 0;
      setWidth(pendingWidth,drag.position);
    });
  });
  splitter.addEventListener('lostpointercapture',() => {
    if (!drag) return;
    if (frame) {
      cancelAnimationFrame(frame);
      frame = 0;
      setWidth(pendingWidth,drag.position);
    }
    keepReadingPosition(drag.position);
    drag = null;
    markResizing(false);
    remember();
  });
  splitter.addEventListener('keydown',event => {
    const limit = Math.max(minimum,Math.min(hardMaximum,measures.total - measures.rail - measures.divider - minimumContent));
    const widths = {ArrowLeft:width + 24,ArrowRight:width - 24,Home:minimum,End:limit};
    if (!Object.hasOwn(widths,event.key)) return;
    event.preventDefault();
    const position = readingPosition();
    markResizing(true);
    setWidth(widths[event.key],position);
    // Apply the final column widths before restoring the open and close transition.
    splitter.getBoundingClientRect();
    markResizing(false);
    remember();
  });

  const observer = new ResizeObserver(refresh);
  observer.observe(toolbar);
  observer.observe(studio);
  refresh();
  return {
    refresh,
    disconnect() {
      cancelAnimationFrame(frame);
      observer.disconnect();
    }
  };
}
