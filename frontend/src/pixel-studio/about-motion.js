import {getLanguage} from './i18n.js';
import {paintBot} from './ui.js';

const faces = ['happy','wink','excited','blink','love','curious'];
const readingPause = 2750;

export function mountAboutMotion(root,reduced,initial={}) {
  const preview = root.querySelector('#mentor-preview');
  const hero = root.querySelector('.about-copy');
  const line = hero.querySelector('.hero-typed-text');
  const segmenter = typeof Intl.Segmenter === 'function' ? new Intl.Segmenter(getLanguage(),{granularity:'grapheme'}) : null;
  const phrases = Array.from(hero.querySelectorAll('.hero-phrase-size'),
    ({textContent}) => segmenter ? Array.from(segmenter.segment(textContent),part => part.segment) : Array.from(textContent));
  const avatar = preview.querySelector('.pixel-hero');
  const stage = preview.querySelector('.bot-stage');
  const chat = preview.querySelector('.preview-chat');
  const replyAvatar = chat.querySelector('.bot-sprite');
  const visible = new Set();
  const pointer = matchMedia('(hover: hover) and (pointer: fine)');
  let paused = initial.paused ?? false;
  let phrase = initial.phrase ?? 0;
  let count = initial.full ? phrases[phrase].length : Math.min(initial.count ?? 0,phrases[phrase].length);
  let erasing = Boolean(initial.erasing);
  let face = initial.face ?? 0;
  let typingTimer;
  let faceTimer;
  let replyTimer;
  let replyVisible = false;
  let replyPlayed = Boolean(initial.replyPlayed);
  let tiltFrame = 0;
  let pointerAt;

  const running = element => !paused && !reduced.matches && !document.hidden && visible.has(element);
  const observer = new IntersectionObserver(entries => {
    for (const {target,isIntersecting} of entries) {
      if (isIntersecting) visible.add(target);
      else visible.delete(target);
    }
    schedule();
  },{threshold:.08});
  const replyObserver = new IntersectionObserver(([entry]) => {
    replyVisible = entry.isIntersecting && entry.intersectionRatio >= .5;
    syncReply();
  },{threshold:.5});

  function cancelReply() {
    clearTimeout(replyTimer);
    replyTimer = undefined;
  }
  function syncReply() {
    if (paused || reduced.matches) {
      cancelReply();
      chat.dataset.reply = 'shown';
      paintBot(replyAvatar,'happy');
      return;
    }
    if (replyPlayed) return;
    if (!replyVisible || document.hidden) {
      cancelReply();
      chat.dataset.reply = 'waiting';
      return;
    }
    if (replyTimer !== undefined) return;
    chat.dataset.reply = 'typing';
    paintBot(replyAvatar,'thinking');
    replyTimer = setTimeout(() => {
      replyTimer = undefined;
      replyPlayed = true;
      chat.dataset.reply = 'sent';
      paintBot(replyAvatar,'happy');
    },1180);
  }
  function showReply() {
    cancelReply();
    replyPlayed = false;
    syncReply();
  }

  function paintFace() {
    const mood = faces[face];
    paintBot(avatar,mood);
    stage.dataset.mood = mood;
  }
  function paintLine(full=false) {
    line.textContent = phrases[phrase].slice(0,full ? undefined : count).join('');
    const typing = hero.classList.contains('typing-active') && (erasing || count < phrases[phrase].length);
    stage.classList.toggle('orbit-muted',typing);
  }
  function type() {
    const length = phrases[phrase].length;
    let delay = 58;
    if (erasing) {
      count--;
      delay = 30;
      if (count <= 0) {
        erasing = false;
        phrase = (phrase + 1) % phrases.length;
        count = 0;
        delay = 215;
      }
    } else if (count < length) {
      count++;
      delay = count === length ? readingPause : phrases[phrase][count - 1] === ' ' ? 82 : 57;
    } else {
      erasing = true;
      count = length - 1;
      delay = 30;
    }
    paintLine();
    typingTimer = setTimeout(type,delay);
  }
  function schedule() {
    clearTimeout(typingTimer);
    clearInterval(faceTimer);
    syncReply();
    const typeVisible = running(hero);
    const botVisible = running(stage);
    stage.classList.toggle('motion-paused',!botVisible);
    hero.classList.toggle('typing-active',typeVisible);
    paintLine(paused || reduced.matches);
    if (typeVisible) typingTimer = setTimeout(type,count >= phrases[phrase].length ? readingPause : 140);
    if (!botVisible) {
      resetTilt();
      return;
    }
    faceTimer = setInterval(() => {
      face = (face + 1) % faces.length;
      paintFace();
    },1000);
  }
  function resetTilt() {
    cancelAnimationFrame(tiltFrame);
    tiltFrame = 0;
    stage.removeAttribute('data-orbit-active');
    stage.style.removeProperty('--orbit-x');
    stage.style.removeProperty('--orbit-y');
  }
  function tilt(event) {
    if (!pointer.matches || !running(stage)) return;
    pointerAt = {x:event.clientX,y:event.clientY};
    if (tiltFrame) return;
    tiltFrame = requestAnimationFrame(() => {
      tiltFrame = 0;
      const bounds = stage.getBoundingClientRect();
      const x = (pointerAt.x - bounds.left) / bounds.width - .5;
      const y = (pointerAt.y - bounds.top) / bounds.height - .5;
      stage.setAttribute('data-orbit-active','');
      stage.style.setProperty('--orbit-x',(-y * 15).toFixed(2) + 'deg');
      stage.style.setProperty('--orbit-y',(x * 18).toFixed(2) + 'deg');
    });
  }
  function dispose() {
    observer.disconnect();
    replyObserver.disconnect();
    document.removeEventListener('visibilitychange',schedule);
    reduced.removeEventListener('change',schedule);
    stage.removeEventListener('pointermove',tilt);
    stage.removeEventListener('pointerleave',resetTilt);
    resetTilt();
    clearTimeout(typingTimer);
    clearInterval(faceTimer);
    cancelReply();
    return {paused,phrase,face,count,erasing,replyPlayed,full:paused || count >= phrases[phrase].length};
  }

  paintFace();
  observer.observe(hero);
  observer.observe(stage);
  replyObserver.observe(chat);
  stage.addEventListener('pointermove',tilt);
  stage.addEventListener('pointerleave',resetTilt);
  document.addEventListener('visibilitychange',schedule);
  reduced.addEventListener('change',schedule);
  schedule();
  return {showReply,dispose};
}
