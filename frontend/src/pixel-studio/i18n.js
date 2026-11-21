import {messages} from './messages.js';

const localeKey = 'it-talent-pixel:locale';
let language = 'vi';
try {
  if (localStorage.getItem(localeKey) === 'en') language = 'en';
} catch {}

export const getLanguage = () => language;
export function setLanguage(next) {
  if (next !== 'vi' && next !== 'en') return;
  language = next;
  try { localStorage.setItem(localeKey, next); } catch {}
}

export function t(key, fields = {}) {
  const entry = messages[key];
  if (!entry) return key;
  const copy = entry[language === 'en' ? 1 : 0];
  return copy.replace(/\{(\w+)\}/g, (pattern, name) => Object.hasOwn(fields, name) ? String(fields[name]) : pattern);
}

export const dateLabel = (time, options = {day:'numeric',month:'short',year:'numeric'}) =>
  new Intl.DateTimeFormat(language === 'vi' ? 'vi-VN' : 'en-GB', options).format(time);

export const scopeLabel = key => t('scope.' + key);
export const roleLabel = key => t('role.' + key);
export const rangeLabel = days => t('range.' + days);
export const sourceLabel = key => t('source.' + key);
