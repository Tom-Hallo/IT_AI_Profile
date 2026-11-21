export const themeKey = 'it-talent-pixel:theme-v1';
export const defaultPreset = 'slate';
export const colorFields = ['background','surface','accent'];

export const presets = {
  slate:{background:'#15171d',surface:'#20242c',accent:'#afc4f4'},
  violet:{background:'#181620',surface:'#242130',accent:'#c8b8f4'},
  copper:{background:'#1b1917',surface:'#282420',accent:'#e1bc95'},
  mint:{background:'#151b22',surface:'#202932',accent:'#a7dbc7'}
};

export function hexColor(value, allowShort=false) {
  if (typeof value !== 'string') return null;
  const hex = value.trim().replace(/^#/,'').toLowerCase();
  if (/^[0-9a-f]{6}$/.test(hex)) return '#' + hex;
  if (allowShort && /^[0-9a-f]{3}$/.test(hex)) {
    return '#' + [...hex].map(digit => digit.repeat(2)).join('');
  }
  return null;
}

export function loadTheme() {
  let stored = null;
  try { stored = JSON.parse(localStorage.getItem(themeKey)); } catch {}
  let custom = null;
  if (colorFields.every(field => hexColor(stored?.custom?.[field]))) {
    custom = Object.fromEntries(colorFields.map(field => [field,hexColor(stored.custom[field])]));
  }
  const selected = stored?.preset;
  const preset = Object.hasOwn(presets,selected) || (selected === 'custom' && custom) ? selected : defaultPreset;
  return {preset,custom};
}

export function saveTheme(theme) {
  try { localStorage.setItem(themeKey,JSON.stringify(theme)); } catch {}
}

export const themeColors = theme => theme.preset === 'custom' ? theme.custom : presets[theme.preset];

const rgb = hex => [1,3,5].map(offset => parseInt(hex.slice(offset,offset + 2),16));

function mix(color, other, amount) {
  const end = rgb(other);
  return '#' + rgb(color).map((channel,i) => Math.round(channel + (end[i] - channel) * amount)
    .toString(16).padStart(2,'0')).join('');
}

function luminance(color) {
  const [red,green,blue] = rgb(color).map(byte => {
    const n = byte / 255;
    return n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4;
  });
  return .2126 * red + .7152 * green + .0722 * blue;
}

function contrast(first,second) {
  const a = luminance(first);
  const b = luminance(second);
  return (Math.max(a,b) + .05) / (Math.min(a,b) + .05);
}

function adjust(color, target, meetsConstraint) {
  if (meetsConstraint(color)) return color;
  let lower = 0;
  let upper = 1;
  for (let pass = 0; pass < 10; pass++) {
    const amount = (lower + upper) / 2;
    if (meetsConstraint(mix(color,target,amount))) upper = amount;
    else lower = amount;
  }
  return mix(color,target,upper);
}

function inkFor(background) {
  return contrast(background,'#ffffff') >= contrast(background,'#000000') ? '#ffffff' : '#000000';
}

function fade(hex, opacity) {
  return hex + Math.round(opacity * 255).toString(16).padStart(2,'0');
}

function paletteFor(base,accent) {
  const ink = inkFor(base);
  const readable = value => contrast(value,base) >= 4.58;
  const fromBase = (target,amount) => mix(base,target,amount);
  const gentle = (target,amount) => {
    const proposed = fromBase(target,amount);
    return adjust(proposed,base,value => contrast(value,ink) >= 4.58);
  };
  const variant = gentle(ink,.075);
  const inset = gentle(ink === '#ffffff' ? '#000000' : '#ffffff',.16);
  const panel = gentle(accent,.12);
  const selected = gentle(accent,.20);
  const textOnAll = value => [base,variant,inset,panel,selected].every(color => contrast(value,color) >= 4.5);
  const accessibleAccent = adjust(accent,ink,textOnAll);
  return {
    ink:adjust(ink === '#ffffff' ? '#edf2f7' : '#14171c',ink,textOnAll),
    muted:adjust(fromBase(ink,.68),ink,textOnAll),
    accent:accessibleAccent,
    accentStrong:mix(accessibleAccent,ink,.30),
    variant,inset,panel,selected,
    line:fromBase(ink,.16),
    lineStrong:fromBase(ink,.36),
    border:fromBase(accessibleAccent,.45),
    glow:fade(accessibleAccent,.12)
  };
}

export function botPalette(accent) {
  return {
    shadow:mix(accent,'#161321',.83),
    metal:mix(accent,'#1d1b27',.48),
    frame:mix(accent,'#5c5669',.27),
    edge:mix(accent,'#ffffff',.40),
    screen:mix(accent,'#13131d',.84),
    lens:mix(accent,'#ffffff',.62),
    light:mix(accent,'#ffffff',.72),
    signal:mix(accent,'#ffffff',.24)
  };
}

export function resolvePalette({background,surface,accent}) {
  const page = paletteFor(background,accent);
  const card = paletteFor(surface,accent);
  const accentInk = inkFor(accent);
  return {
    bg:background,surface,
    'page-ink':page.ink,'page-muted':page.muted,'page-accent':page.accent,
    'page-accent-strong':page.accentStrong,'page-line':page.line,'page-glow':page.glow,
    'surface-ink':card.ink,'surface-muted':card.muted,'surface-accent':card.accent,'surface-accent-strong':card.accentStrong,
    'surface-2':card.variant,inset:card.inset,line:card.line,'line-strong':card.lineStrong,
    'accent-panel':card.panel,'accent-wash':card.selected,'accent-border':card.border,'accent-glow':card.glow,
    'accent-fill':accent,'accent-ink':accentInk,
    'accent-hover':mix(accent,accentInk === '#ffffff' ? '#000000' : '#ffffff',.13),
    ...Object.fromEntries(Object.entries(botPalette(accent)).map(([key,value]) => ['bot-' + key,value]))
  };
}

export function applyTheme(theme) {
  const palette = resolvePalette(themeColors(theme));
  const style = document.documentElement.style;
  const surfaceInk = inkFor(palette.surface);
  style.colorScheme = surfaceInk === '#ffffff' ? 'dark' : 'light';
  for (const [key,color] of Object.entries(palette)) style.setProperty('--' + key,color);
  document.querySelector('meta[name="theme-color"]').content = palette.bg;
}
