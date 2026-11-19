import {t} from './i18n.js';
import {colorFields, presets, themeColors} from './theme.js';
import {attr, btn, escape, heading, icon, labelAttr, panelHead} from './ui.js';

const colorLabel = name => t('theme.' + name);

export function settingsView(theme) {
  const colors = themeColors(theme);
  return heading(t('nav.settings'),t('theme.intro'))
    + '<div class="settings-layout"><section class="panel settings-palette">'
    + panelHead(t('theme.presets'),t('theme.presetsCopy'))
    + '<div class="palette-grid" role="group"' + labelAttr(t('theme.presets')) + '>'
    + Object.entries(presets).map(([id, swatches]) => {
      const style = '--sample-bg:' + swatches.background + ';--sample-surface:' + swatches.surface + ';--sample-accent:' + swatches.accent;
      return '<button type="button" class="palette-choice" data-act="theme-preset"' + attr('id',id)
        + ' aria-pressed="' + (theme.preset === id) + '"><span class="palette-diagram" style="' + style
        + '" aria-hidden="true"><i></i><i></i><i></i></span><span class="palette-name">'
        + escape(t('theme.' + id)) + '<span class="palette-check">' + icon('check') + '</span></span></button>';
    }).join('') + '</div></section><section class="panel settings-preview">'
    + panelHead(t('theme.preview'))
    + '<div class="theme-example"><div class="theme-example-card"><span class="feature-icon">' + icon('branch')
    + '</span><div><h3>' + escape(t('theme.previewTitle')) + '</h3><p>' + escape(t('theme.previewCopy'))
    + '</p></div><span aria-hidden="true" class="button primary small">' + escape(t('theme.previewButton'))
    + '</span></div></div></section>'
    + '<section class="panel settings-custom">' + panelHead(t('theme.custom'),t('theme.customCopy'))
    + '<div class="theme-color-grid">' + colorFields.map(name => {
      const color = colors[name];
      const label = colorLabel(name);
      return '<div class="theme-color-row"><label for="theme-picker-' + name + '">' + escape(label) + '</label>'
        + '<div class="theme-color-inputs"><input id="theme-picker-' + name + '" type="color" value="' + color + '"'
        + attr('theme-color',name) + '><input id="theme-hex-' + name + '" type="text" maxlength="7" value="' + color.toUpperCase() + '"'
        + attr('theme-color',name) + labelAttr(t('theme.hexLabel',{color:label})) + ' spellcheck="false" autocomplete="off"></div></div>';
    }).join('') + '</div><p class="theme-local">' + escape(t('theme.local')) + '</p><div class="action-row">'
    + btn(escape(t('theme.useCustom')),'theme-preset','secondary small',
      'id="use-custom-theme"' + attr('id','custom') + (!theme.custom || theme.preset === 'custom' ? ' hidden' : ''))
    + btn(escape(t('theme.restore')),'theme-reset','quiet small','id="reset-theme"') + '</div></section></div>';
}

export function syncThemeControls(view, theme, editing) {
  for (const button of view.querySelectorAll('.palette-choice')) {
    button.setAttribute('aria-pressed',String(button.dataset.id === theme.preset));
  }
  const custom = view.querySelector('#use-custom-theme');
  if (!custom) return;
  const hideCustom = !theme.custom || theme.preset === 'custom';
  const restoreFocus = hideCustom && custom === document.activeElement;
  custom.hidden = hideCustom;
  for (const field of view.querySelectorAll('[data-theme-color]')) {
    if (field === editing) continue;
    const value = themeColors(theme)[field.dataset.themeColor];
    field.value = field.type === 'color' ? value : value.toUpperCase();
    field.removeAttribute('aria-invalid');
  }
  if (restoreFocus) view.querySelector('#theme-hex-background').focus({preventScroll:true});
}
