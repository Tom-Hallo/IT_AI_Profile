import {dateLabel, roleLabel, t} from './i18n.js';
import {scoredRepos} from './model.js';
import {connectorPath,connectorPoints} from './roadmap-connectors.js';
import {recommendationFor} from './roadmap-recommendation.js';
import {
  achievementOrder, checklist, evidenceURL, milestonesFor, milestoneText, nextStep,
  paths, planFor, stateOf, stepsDone, taskLabel
} from './roadmap-model.js';
import {attr, badge, btn, escape, field, heading, icon, option, panelHead, progress} from './ui.js';

function mapNode(state,item,index,selected,recentlyUnlocked,isNext) {
  const mode = stateOf(state,index);
  const glyph = mode === 'done' ? 'check' : mode === 'locked' ? 'lock' : item.icon;
  const label = recentlyUnlocked ? 'road.fresh' : isNext ? 'road.next' : 'road.' + mode;
  return '<button class="node' + (recentlyUnlocked ? ' node-fresh' : '') + '" type="button" data-act="milestone"' + attr('id',index) + attr('state',mode)
    + (isNext ? ' aria-current="step"' : '') + ' aria-pressed="' + (selected === index) + '"><span class="map-icon">' + icon(glyph) + '</span><strong>'
    + escape(milestoneText(state.goal,index)) + '</strong><small>' + escape(t(label)) + '</small></button>';
}

function awardCard(state,index) {
  const award = planFor(state).awards[index];
  const milestone = milestonesFor(state)[index];
  const label = award?.link ? 'road.recorded' : award ? 'road.selfConfirmed' : 'road.initialMilestone';
  return '<button class="award-card" type="button" data-act="milestone"' + attr('id',index) + '><span class="award-icon">'
    + icon(milestone.icon) + '</span><span><strong>' + escape(milestoneText(state.goal,index,'achievement')) + '</strong><span class="award-summary">'
    + escape(milestoneText(state.goal,index,'proof')) + '</span><small>' + escape(t(label)) + '</small></span>' + icon('arrow') + '</button>';
}

function selectedMilestone(state,index,unlocked) {
  const milestone = milestonesFor(state)[index];
  const plan = planFor(state);
  const mode = stateOf(state,index);
  const checklistItems = checklist(state,index);
  const noteRows = plan.notes.filter(note => note.i === index && (!note.repo || scoredRepos(state).some(repo => repo.id === note.repo)));
  const evidence = state.access !== 'none' && scoredRepos(state).find(repo => repo.id === milestone.repo);
  const award = mode === 'done' ? plan.awards[index] : null;
  const url = award?.link && evidenceURL(award.link);
  const checked = mode === 'done' ? checklistItems.length : checklistItems.filter(item => item.done).length;
  const canComplete = mode === 'ready' && checked === checklistItems.length;
  return '<article class="panel road-detail" id="milestone-detail"><div class="detail-top">'
    + badge(t('road.' + mode),mode === 'done' ? 'green' : mode === 'locked' ? 'amber' : 'blue')
    + '<small>' + escape(t('road.time',{minutes:milestone.minutes})) + '</small></div>'
    + '<h2>' + escape(milestoneText(state.goal,index)) + '</h2><p>' + escape(milestoneText(state.goal,index,'task')) + '</p>'
    + (mode === 'locked' ? '<div class="milestone-block"><h3>' + escape(t('road.unlock')) + '</h3><ul class="criteria-list">'
      + milestone.needs.map(i => '<li>' + btn(icon(stateOf(state,i) === 'done' ? 'check' : 'lock') + escape(milestoneText(state.goal,i)),
        'milestone','quiet small',attr('id',i)) + '</li>').join('') + '</ul></div>' : '')
    + '<div class="milestone-block"><div class="checklist-heading"><h3>' + escape(t('road.criteria')) + '</h3><span>'
    + escape(t('road.criteriaCount',{done:checked,total:checklistItems.length})) + '</span></div><div class="checklist-progress">'
    + progress(checked / checklistItems.length * 100,t('road.criteriaCount',{done:checked,total:checklistItems.length})) + '</div><ul class="criteria-list">'
    + checklistItems.map(item => '<li><label class="option-row"><input type="checkbox" class="road-criterion" value="' + item.field + '"'
      + (item.done || mode === 'done' ? ' checked' : '') + (mode !== 'ready' ? ' disabled' : '') + '><span>' + escape(item.label) + '</span></label></li>').join('')
    + '</ul></div><div class="milestone-proof"><span class="feature-icon">' + icon('award') + '</span><div><h3>'
    + escape(mode === 'done' ? milestoneText(state.goal,index,'achievement') : t('road.proof')) + '</h3><p>'
    + escape(milestoneText(state.goal,index,'proof')) + '</p>'
    + (award ? '<small>' + escape(dateLabel(award.at)) + ' · ' + escape(t(award.link ? 'road.recorded' : 'road.selfConfirmed')) + '</small>' : '')
    + (url ? '<a class="link-button" href="' + escape(url) + '" target="_blank" rel="noopener noreferrer">' + icon('arrow') + escape(t('road.linkEvidence')) + '</a>' : '')
    + (mode === 'done' && !award ? '<small>' + escape(t('road.initialMilestone')) + '</small>' : '')
    + '</div></div>'
    + (unlocked.length ? '<section class="road-unlock-result"><h3>' + escape(t('road.fresh')) + '</h3><div class="action-row">'
      + unlocked.map(i => btn(escape(milestoneText(state.goal,i)) + icon('arrow'),'focus-milestone','secondary small',attr('id',i))).join('')
      + '</div></section>' : '')
    + (evidence ? '<div class="road-evidence"><small>' + escape(t('road.evidenceScope')) + '</small>'
      + btn(icon('file') + ' ' + escape(evidence.file),'evidence','link-button',attr('id',evidence.id)) + '</div>' : '')
    + (noteRows.length ? '<div class="milestone-block"><h3>' + escape(t('road.tasks')) + '</h3><ul class="criteria-list">'
      + noteRows.map(note => '<li><label class="option-row"><input type="checkbox" class="road-task" value="' + escape(note.id) + '"'
        + (note.done ? ' checked' : '') + (mode === 'locked' ? ' disabled' : '') + '><span>' + escape(taskLabel(note)) + '</span></label></li>').join('')
      + '</ul></div>' : '')
    + '<div class="action-row">' + btn(icon(mode === 'done' ? 'close' : 'check') + escape(t(mode === 'done' ? 'road.undo' : 'road.complete')),
      'complete',mode === 'done' ? 'quiet small' : 'primary small',
      mode !== 'done' && !canComplete ? 'disabled' : '')
    + btn(icon('bot') + escape(t('action.askMentor')),'ask-step','secondary small') + '</div>'
    + (mode === 'ready' && !canComplete ? '<small>' + escape(t('road.completeLocked')) + '</small>' : '') + '</article>';
}

export function roadmap(state,runtime) {
  const goal = state.goal;
  const plan = planFor(state);
  const milestones = milestonesFor(state);
  const next = nextStep(state);
  const selected = runtime.milestone;
  const recent = runtime.roadUnlock?.goal === goal ? runtime.roadUnlock : null;
  const unlocked = recent?.indices ?? [];
  const count = stepsDone(state);
  const {snapshot} = recommendationFor(state);
  const reference = next >= 0 && scoredRepos(state).find(repo => repo.id === milestones[next].repo);
  const readyCount = milestones.filter((_,index) => stateOf(state,index) === 'ready').length;
  const goalPicker = field(t('road.goal'),'<select id="road-goal">' + Object.keys(paths).map(id => option(id,roleLabel(id),goal)).join('') + '</select>');
  const history = plan.history.length ? '<details class="panel road-history"><summary>' + escape(t('road.history')) + '</summary><ul class="audit-list">'
    + plan.history.map(item => '<li><time>' + escape(dateLabel(item.at)) + '</time><span>' + escape(t('road.history' + item.kind,
      {name:milestoneText(goal,item.index,item.kind === 'Plan' ? 'name' : 'achievement')})) + '</span></li>').join('') + '</ul></details>' : '';
  return heading(t('road.heading'),t('road.intro'),goalPicker)
    + '<div class="road-banner"><section class="panel road-next"><div><p class="eyebrow">' + escape(t(next === -1 ? 'road.done' : 'road.next')) + '</p><h2>'
    + escape(next === -1 ? t('road.finished') : milestoneText(goal,next)) + '</h2><p>'
    + escape(next === -1 ? t('road.finishedCopy') : milestoneText(goal,next,'task')) + '</p>'
    + (reference ? '<p class="road-source">' + icon('file') + '<code>' + escape(reference.file) + '</code></p>' : '') + '</div>'
    + (next >= 0 ? '<div class="road-achievement-ahead"><span class="award-icon">' + icon('award') + '</span><div><small>'
      + escape(t('road.achievementAhead')) + '</small><strong>' + escape(milestoneText(goal,next,'achievement')) + '</strong><p>'
      + escape(milestoneText(goal,next,'proof')) + '</p></div></div>' : '')
    + (next === -1 ? '<span class="road-emblem" aria-hidden="true">' + icon('award') + '</span>'
      : btn(escape(t('profile.pickNext')) + icon('arrow'),'focus-milestone','primary',attr('id',next))) + '</section>'
    + '<section class="panel road-progress"><div><p class="eyebrow">' + escape(t('road.progress')) + '</p><strong>' + count + '<span> / ' + milestones.length
    + '</span></strong><p>' + escape(t('road.progressCount',{done:count,total:milestones.length})) + '</p></div>'
    + '<div class="milestone-pips" aria-hidden="true">' + milestones.map((_,i) => '<i' + attr('step',i) + attr('state',stateOf(state,i)) + '></i>').join('') + '</div>'
    + '<div class="sr-only">' + progress(count / milestones.length * 100,t('road.progress')) + '</div>'
    + (readyCount ? '<p class="ready-count">' + escape(t('road.readyCount',{count:readyCount})) + '</p>' : '') + '</section></div>'
    + (next >= 0 ? '<section class="road-update"><div>' + icon('pulse') + '<span>'
      + escape(snapshot ? t('road.newReport') : t('road.recommendation')) + '</span></div>'
      + btn(escape(t(snapshot ? 'road.reviewUpdate' : 'road.propose')),'road-draft',snapshot ? 'primary small' : 'secondary small') + '</section>' : '')
    + '<div class="road-layout"><section class="panel map-panel">' + panelHead(t('road.map'),t('road.mapCaption'))
    + '<div class="map-legend" aria-label="' + escape(t('road.progress')) + '">' + ['done','ready','locked'].map(mode => '<span data-state="' + mode + '"><i></i>' + escape(t('road.' + mode)) + '</span>').join('') + '</div>'
    + '<div class="road-map"><svg class="road-map-lines" aria-hidden="true" focusable="false"></svg><canvas aria-hidden="true"></canvas>'
    + milestones.map((item,i) => mapNode(state,item,i,selected,unlocked.includes(i),i === next)).join('') + '</div></section>'
    + selectedMilestone(state,selected,recent?.completed === selected ? unlocked : []) + (count || history ? '<div class="road-records stack">'
      + (count ? '<section class="panel achievements">' + panelHead(t('road.trophies'),t('road.trophiesCopy')) + '<div class="award-list">'
        + achievementOrder(state).map(index => awardCard(state,index)).join('') + '</div></section>' : '')
      + history + '</div>' : '') + '</div>';
}

export function paintMap(map,state,trace,liveMilestones) {
  const canvas = map?.querySelector('canvas');
  const ctx = canvas?.getContext('2d');
  if (!ctx || !map.isConnected) return;
  const scale = Math.min(devicePixelRatio || 1,2);
  const {clientWidth:width,clientHeight:height} = map;
  if (!width || !height) return;
  const widthPx = Math.round(width * scale);
  const heightPx = Math.round(height * scale);
  if (canvas.width !== widthPx) canvas.width = widthPx;
  if (canvas.height !== heightPx) canvas.height = heightPx;
  ctx.setTransform(scale,0,0,scale,0,0);
  ctx.clearRect(0,0,width,height);
  const points = [...map.querySelectorAll('.node')].map(node => ({
    x:node.offsetLeft + node.offsetWidth / 2, y:node.offsetTop + node.offsetHeight / 2
  }));
  const vertical = points.length > 1 && points[0].y < points[1].y;
  const styles = getComputedStyle(map);
  const activeLine = styles.getPropertyValue('--accent').trim();
  const quietLine = styles.getPropertyValue('--line-strong').trim();
  const traceColor = trace && styles.getPropertyValue('--accent-strong').trim();

  // The SVG is decorative only. Keep the canvas for the existing unlock trace
  // and as a fallback, using the exact same node centers and elbow coordinates.
  const svg = map.querySelector('.road-map-lines');
  const existing = svg ? new Map([...svg.querySelectorAll('g[data-connector]')].map(group => [group.dataset.connector,group])) : null;
  if (svg) svg.setAttribute('viewBox','0 0 ' + width + ' ' + height);
  const milestones = liveMilestones ? liveMilestones.map((item,index) => ({
    ...item,needs:index ? [index - 1] : []
  })) : milestonesFor(state);
  for (const [i,item] of milestones.entries()) {
    for (const dep of item.needs) {
      const from = points[dep];
      const to = points[i];
      if (!from || !to) continue;
      const done = liveMilestones ? liveMilestones[dep].status === 'completed' : stateOf(state,dep) === 'done';
      const route = connectorPoints(from,to,vertical);

      if (svg) {
        const key = dep + ':' + i;
        let group = existing.get(key);
        if (!group) {
          group = document.createElementNS('http://www.w3.org/2000/svg','g');
          group.dataset.connector = key;
          for (const name of ['road-connector-stroke','road-connector-flow']) {
            const path = document.createElementNS('http://www.w3.org/2000/svg','path');
            path.setAttribute('class',name);
            path.setAttribute('vector-effect','non-scaling-stroke');
            if (name === 'road-connector-flow') path.setAttribute('pathLength','100');
            group.append(path);
          }
          svg.append(group);
        }
        group.classList.toggle('is-solid',done);
        group.classList.toggle('is-dashed',!done);
        const d = connectorPath(route);
        for (const path of group.children) path.setAttribute('d',d);
        existing.delete(key);
      }

      ctx.strokeStyle = done ? activeLine : quietLine;
      ctx.lineWidth = done ? 2 : 1.5;
      ctx.setLineDash(done ? [] : [4,6]);
      ctx.beginPath();
      ctx.moveTo(route[0].x,route[0].y);
      for (const point of route.slice(1)) ctx.lineTo(point.x,point.y);
      if (!svg) ctx.stroke();
      if (trace?.from === dep && trace.targets.includes(i)) {
        const length = Math.abs(to.x - from.x) + Math.abs(to.y - from.y);
        ctx.setLineDash([length * trace.progress,length + 1]);
        ctx.globalAlpha = trace.opacity;
        ctx.lineWidth = 3;
        ctx.strokeStyle = traceColor;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }
  }
  if (existing) for (const group of existing.values()) group.remove();
}

export function animateUnlock(map,state,from,targets,reduced) {
  if (!map || !targets.length || reduced.matches) return;
  let frame;
  let start;
  function draw(time) {
    if (!map.isConnected) return;
    start ??= time;
    const elapsed = time - start;
    if (elapsed >= 920 || reduced.matches) {
      paintMap(map,state);
      delete map.dataset.tracing;
      return;
    }
    const progress = Math.min(elapsed / 625,1);
    const opacity = elapsed < 625 ? 1 : 1 - (elapsed - 625) / 295;
    paintMap(map,state,{from,targets,progress,opacity});
    frame = requestAnimationFrame(draw);
  }
  const observer = new IntersectionObserver(([entry]) => {
    if (!entry.isIntersecting) return;
    observer.disconnect();
    map.dataset.tracing = 'true';
    frame = requestAnimationFrame(draw);
  });
  observer.observe(map);
  return () => {
    observer.disconnect();
    cancelAnimationFrame(frame);
    delete map.dataset.tracing;
  };
}
