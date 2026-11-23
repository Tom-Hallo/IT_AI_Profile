import {escape, icon, labelAttr, link} from './ui.js';
import {t} from './i18n.js';

export function radarView(scores, reportCount, scope, range, comparison, insights='') {
  const header = '<header class="radar-header"><div><h2 id="radar-title">' + escape(t('radar.title'))
    + '</h2><p>' + escape(scope + ' · ' + range) + '</p></div><span class="radar-scale">' + escape(t('radar.scale')) + '</span></header>';
  if (!scores.length) {
    return '<section class="panel radar-panel" aria-labelledby="radar-title">' + header
      + '<div class="radar-empty"><span class="radar-mark">' + icon('pulse') + '</span><div><h3>' + escape(t('radar.empty'))
      + '</h3><p>' + escape(t('radar.emptyCopy')) + '</p></div>'
      + link(escape(t('action.openRepo')),'repos','secondary small') + '</div></section>';
  }

  const indicators = scores.map(({key,label,score},index) => {
    const valid = typeof score === 'number' && Number.isFinite(score) && score >= 0 && score <= 100;
    const trend = valid ? comparison?.[key] : null;
    const change = trend?.delta ? (trend.delta > 0 ? '+' + trend.delta : '−' + Math.abs(trend.delta)) : null;
    return '<li><button type="button" class="radar-indicator' + (valid ? '' : ' is-unscored')
      + '" data-radar-axis="' + index + '" data-score="' + (valid ? score : '') + '"'
      + (trend ? ' data-previous="' + trend.before + '"' : '')
      + ' aria-controls="radar-detail-' + key + '" aria-expanded="false">'
      + '<span class="radar-dot" aria-hidden="true"></span><span class="radar-label">' + escape(label) + '</span>'
      + '<span class="radar-number"><strong>' + (valid ? score + '<small>/100</small>' : '—') + '</strong>'
      + (change ? '<span class="radar-change" data-change="' + Math.sign(trend.delta) + '" title="' + escape(t('radar.delta',{change})) + '">'
        + '<span class="sr-only">' + escape(t('radar.delta',{change})) + '</span><span aria-hidden="true">' + change + '</span></span>' : '')
      + '</span></button></li>';
  }).join('');
  const legend = Object.keys(comparison ?? {}).length === scores.length
    ? '<div class="radar-legend"><span>' + escape(t('radar.current')) + '</span><span>' + escape(t('radar.prior')) + '</span></div>' : '';
  return '<section class="panel radar-panel" aria-labelledby="radar-title">' + header
    + '<div class="radar-body"><div class="radar-chart"><div class="radar-plot"><canvas aria-hidden="true"></canvas></div>' + legend + '</div>'
    + '<div class="radar-values"><p>' + escape(t('radar.caption',{count:reportCount})) + '</p>'
    + '<ul class="radar-indicators"' + labelAttr(t('radar.axes')) + '>' + indicators + '</ul>'
    + '<p class="subtle">' + escape(t('radar.missingAxes')) + '</p></div></div>' + insights + '</section>';
}

export function mountRadar(panel, selectedAxis, selectAxis) {
  const plot = panel?.querySelector('.radar-plot');
  const canvas = plot?.querySelector('canvas');
  const ctx = canvas?.getContext('2d');
  if (!ctx) return null;

  const axes = [...panel.querySelectorAll('[data-radar-axis]')];
  const insights = axes.map(axis => document.getElementById(axis.getAttribute('aria-controls')));
  const values = axes.map(axis =>
    axis.dataset.score === '' ? null : Number(axis.dataset.score) / 100
  );
  const previous = axes.map(axis =>
    axis.dataset.previous === undefined ? null : Number(axis.dataset.previous) / 100
  );
  const labels = axes.map(axis => axis.querySelector('.radar-label').textContent);
  const angles = axes.map((_, i) => (i / axes.length) * Math.PI * 2 - Math.PI / 2);
  const ringValues = [.25,.5,.75,1].map(level => axes.map(() => level));
  let active = selectedAxis;
  let geometry;
  function paint() {
    if (!panel.isConnected) return;
    const width = plot.clientWidth;
    const height = plot.clientHeight;
    geometry = null;
    if (!width || !height) return;
    const style = getComputedStyle(panel);
    const color = name => style.getPropertyValue(name).trim();
    const accent = color('--accent');
    const highlight = color('--accent-strong');
    const grid = color('--line-strong');
    const scale = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    ctx.scale(scale,scale);
    const centerX = width / 2;
    const centerY = height / 2 + 4;
    const showLabels = width >= 285;
    ctx.font = (width < 370 ? '10px' : '11px') + ' Inter, system-ui, sans-serif';
    const sideLabel = Math.max(ctx.measureText(labels[1]).width, ctx.measureText(labels[2]).width,
      ctx.measureText(labels[3]).width, ctx.measureText(labels[4]).width);
    const radius = Math.min((width - (showLabels ? 2 * (sideLabel + 13) : 44)) / 2, (height - 48) / 2, 116);
    if (radius < 24) return;
    geometry = {centerX,centerY,radius};

    function point(angle, length) {
      return [centerX + Math.cos(angle) * length,centerY + Math.sin(angle) * length];
    }
    function polygon(levels) {
      ctx.beginPath();
      angles.forEach((angle, i) => {
        const [x,y] = point(angle,radius * levels[i]);
        if (i === 0) ctx.moveTo(x,y);
        else ctx.lineTo(x,y);
      });
      ctx.closePath();
    }
    ctx.lineWidth = 1;
    for (const ring of ringValues) {
      polygon(ring);
      ctx.strokeStyle = grid + (ring[0] === 1 ? 'ae' : '67');
      ctx.stroke();
    }
    angles.forEach((angle,i) => {
      ctx.beginPath();
      ctx.moveTo(centerX,centerY);
      ctx.lineTo(...point(angle,radius));
      ctx.strokeStyle = i === active ? highlight : grid + '49';
      ctx.stroke();
    });

    const complete = values.every(value => typeof value === 'number' && Number.isFinite(value));
    if (complete) {
      polygon(values);
      const fill = ctx.createLinearGradient(0,centerY - radius,0,centerY + radius);
      fill.addColorStop(0,accent + '52');
      fill.addColorStop(1,accent + '13');
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = accent;
      ctx.lineWidth = 1.8;
      ctx.stroke();
    } else {
      // Missing evidence is not zero: only connect adjacent measured axes.
      ctx.strokeStyle = accent;
      ctx.lineWidth = 1.8;
      values.forEach((value, i) => {
        const next = (i + 1) % values.length;
        if (value === null || values[next] === null) return;
        ctx.beginPath();
        ctx.moveTo(...point(angles[i], radius * value));
        ctx.lineTo(...point(angles[next], radius * values[next]));
        ctx.stroke();
      });
    }

    if (previous.every(value => typeof value === 'number' && Number.isFinite(value))) {
      polygon(previous);
      ctx.strokeStyle = color('--muted');
      ctx.lineWidth = 1.3;
      ctx.setLineDash([4,4]);
      ctx.stroke();
      ctx.setLineDash([]);
      angles.forEach((angle, i) => {
        const [px,py] = point(angle, radius * previous[i]);
        ctx.beginPath();
        ctx.arc(px,py,2.5,0,Math.PI * 2);
        ctx.fillStyle = color('--muted');
        ctx.fill();
      });
    }

    angles.forEach((angle, i) => {
      if (values[i] === null) return;
      const [x,y] = point(angle,radius * values[i]);
      if (i === active) {
        ctx.beginPath();
        ctx.arc(x,y,9,0,Math.PI * 2);
        ctx.fillStyle = accent + '3b';
        ctx.fill();
      }
      ctx.beginPath();
      ctx.arc(x,y,i === active ? 4.6 : 3.2,0,Math.PI * 2);
      ctx.fillStyle = i === active ? highlight : accent;
      ctx.fill();
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = color('--inset');
      ctx.stroke();
    });

    if (!showLabels) return;
    ctx.textBaseline = 'middle';
    angles.forEach((angle,i) => {
      const [x,y] = point(angle,radius + (width < 370 ? 7 : 10));
      const side = Math.cos(angle);
      ctx.textAlign = Math.abs(side) < .1 ? 'center' : side > 0 ? 'left' : 'right';
      ctx.fillStyle = i === active ? color('--ink') : color('--muted');
      ctx.fillText(labels[i],x,y);
    });
  }

  function refresh() {
    axes.forEach((axis,index) => {
      axis.setAttribute('aria-expanded',String(index === active));
      if (insights[index]) insights[index].hidden = index !== active;
    });
    paint();
  }
  function toggle(index,moveFocus=false) {
    active = active === index ? null : index;
    selectAxis(active);
    refresh();
    if (moveFocus) axes[index].focus({preventScroll:true});
    if (insights[active]?.getBoundingClientRect().bottom > window.innerHeight) {
      insights[active].scrollIntoView({block:'nearest',behavior:'instant'});
    }
  }
  function axisAt(event) {
    if (!geometry) return null;
    const bounds = canvas.getBoundingClientRect();
    const {centerX,centerY,radius} = geometry;
    const x = event.clientX - bounds.left - centerX;
    const y = event.clientY - bounds.top - centerY;
    const distance = Math.hypot(x,y);
    if (distance < radius * .25 || distance > radius + 30) return null;
    const direction = Math.atan2(y,x);
    const alignment = angles.map(angle => Math.cos(direction - angle));
    return alignment.indexOf(Math.max(...alignment));
  }
  axes.forEach((axis,index) => axis.addEventListener('click',() => toggle(index)));
  canvas.addEventListener('pointermove',event => { canvas.style.cursor = axisAt(event) === null ? '' : 'pointer'; });
  canvas.addEventListener('click',event => {
    const index = axisAt(event);
    if (index !== null) toggle(index,true);
  });
  const observer = new ResizeObserver(paint);
  observer.observe(plot);
  refresh();
  return {disconnect:() => observer.disconnect(),repaint:paint};
}
