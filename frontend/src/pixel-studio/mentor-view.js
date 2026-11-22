import {mentorSources} from './data.js';
import {sourceLabel, t} from './i18n.js';
import {replyCopy, replySourceLabel} from './mentor-model.js';
import {codeReferenceLabel} from './evidence.js';
import {attr, bot, btn, escape, field, icon, labelAttr, option, tags} from './ui.js';

function replyMood(message) {
  if (message.action && !message.actionApplied && !message.actionDismissed) return 'review';
  return message.used?.length ? 'happy' : 'curious';
}

function formatInline(str) {
  let escaped = escape(str);
  // markdown links: [label](https://...)
  escaped = escaped.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-link">$1 ↗</a>');
  escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  escaped = escaped.replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>');
  escaped = escaped.replace(/\[(E\d+(?:,\s*E\d+)*)\]/g, '<span class="evidence-pill">$1</span>');
  return escaped;
}

function formatMentorMarkdown(text) {
  if (!text) return '';
  const lines = text.split('\n');
  const blocks = [];
  let currentList = null;

  for (let rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      if (currentList) {
        blocks.push('<ul class="chat-md-list">' + currentList.join('') + '</ul>');
        currentList = null;
      }
      continue;
    }

    if (line.startsWith('### ')) {
      if (currentList) {
        blocks.push('<ul class="chat-md-list">' + currentList.join('') + '</ul>');
        currentList = null;
      }
      blocks.push('<h4 class="chat-md-heading">' + formatInline(line.slice(4).trim()) + '</h4>');
    } else if (line.startsWith('## ')) {
      if (currentList) {
        blocks.push('<ul class="chat-md-list">' + currentList.join('') + '</ul>');
        currentList = null;
      }
      blocks.push('<h4 class="chat-md-heading">' + formatInline(line.slice(3).trim()) + '</h4>');
    } else if (/^[-*]\s+/.test(line)) {
      const itemText = line.replace(/^[-*]\s+/, '');
      if (!currentList) currentList = [];
      currentList.push('<li>' + formatInline(itemText) + '</li>');
    } else {
      if (currentList) {
        blocks.push('<ul class="chat-md-list">' + currentList.join('') + '</ul>');
        currentList = null;
      }
      blocks.push('<p>' + formatInline(line) + '</p>');
    }
  }

  if (currentList) {
    blocks.push('<ul class="chat-md-list">' + currentList.join('') + '</ul>');
  }

  return blocks.join('');
}

function renderMessage(msg,animate) {
  const entering = animate ? ' entering' : '';
  if (msg.type === 'user') return '<div class="chat-bubble user' + entering + '">' + escape(msg.text)
    + (msg.snippet ? '<small class="chat-user-source">' + icon('file') + escape(codeReferenceLabel(msg.snippet)) + '</small>' : '') + '</div>';
  let source = '';
  if (msg.source) {
    const label = escape(replySourceLabel(msg.source));
    source = msg.source.action
      ? btn(icon(msg.source.action === 'radar-source' ? 'pulse' : 'file') + ' ' + label,msg.source.action,'link-button',attr('id',msg.source.id)
        + (msg.source.goal ? attr('goal',msg.source.goal) : '') + (msg.source.snippet ? attr('message',msg.id) : ''))
      : '<a class="link-button" href="#studio/' + msg.source.route + '">' + icon('link') + label + '</a>';
  }
  const action = msg.action && !msg.actionApplied && !msg.actionDismissed
    ? '<div class="action-row">' + btn(escape(t('mentor.preview')),'agent-preview','secondary small',attr('id',msg.id)) + '</div>' : '';
  
  const evidenceTray = msg.evidence?.length
    ? '<div class="chat-evidence-tray"><span class="evidence-tray-label">📌 Nguồn dẫn chứng:</span> '
      + msg.evidence.map(e => '<span class="evidence-pill">[' + escape(e.id) + '] ' + escape(e.label) + '</span>').join(' ')
      + '</div>'
    : '';
  const limits = (msg.limitations || []).filter(item => item.code !== 'confidence_unavailable');
  const limitationsTray = limits.length
    ? '<div class="chat-limitation-tray">⚠️ ' + limits.map(item => escape(item.message)).join(' ') + '</div>'
    : '';
  const body = (msg.liveText ?? msg.parts.map(replyCopy)).map(part => formatMentorMarkdown(part)).join('');

  return '<div class="chat-row">' + bot('pixel-small',replyMood(msg)) + '<div class="chat-bubble' + entering + '">'
    + body + evidenceTray + limitationsTray
    + (msg.used?.length ? tags(msg.used.map(sourceLabel),'green') : '') + source + action
    + (msg.actionApplied ? tags([t('mentor.applied')],'green') : '') + '</div></div>';
}

export function mentor(runtime,context,animateLast,live) {
  const messages = runtime.messages;
  const latestReply = messages.at(-1);
  const mood = runtime.chatPending ? 'thinking' : latestReply ? replyMood(latestReply) : 'idle';
  const statusKey = latestReply?.actionApplied ? 'applied' : mood === 'idle' ? 'ready' : mood;
  const choices = (live ? mentorSources.filter(key => key !== 'report') : mentorSources).map(key =>
    '<label><input type="checkbox" name="mentor-source" value="' + key + '"' + (runtime.chosen.has(key) ? ' checked' : '')
    + '>' + escape(sourceLabel(key)) + '</label>').join('');
  const sourceOptions = live ? [
    runtime.chosen.has('cv') ? field('CV','<select name="mentor-cv"><option value="">—</option>'
      + live.mentorSources.cvs.map(item => option(item.id,'CV #' + item.id,Number(live.mentorCV))).join('') + '</select>') : '',
    runtime.chosen.has('roadmap') ? field('Roadmap','<select name="mentor-road"><option value="">—</option>'
      + live.mentorSources.roadmaps.map(item => option(item.id,item.title,Number(live.mentorRoad || live.road?.id))).join('') + '</select>') : '',
    runtime.chosen.has('job') ? field('JD','<textarea name="mentor-jd" rows="3" maxlength="20000">'
      + escape(live.mentorJD ?? live.jobText ?? '') + '</textarea>') : ''
  ].join('') : '';
  const prompts = [
    ['mentor.promptEvidence','mentor.qEvidence'],
    ['mentor.promptNext','mentor.qNext'],
    ['mentor.promptAction','road.askTask']
  ];
  const quickPrompt = ([label,prompt],style='quiet small') =>
    btn(escape(t(label)) + (style === 'secondary' ? icon('arrow') : ''),'prompt',style,attr('id',prompt));
  const metricPrompt = style => btn(
    escape(t('mentor.qMetric',{name:t('metric.' + context.metric)})) + (style === 'secondary' ? icon('arrow') : ''),
    'ask-metric',style,attr('id',context.metric));
  const followUps = messages.length && !runtime.chatPending && !runtime.chatSnippet
    ? '<div class="mentor-follow-ups"' + labelAttr(t('mentor.suggestions')) + '>'
      + (context.metric ? metricPrompt('quiet small') + quickPrompt(prompts[1]) : prompts.slice(1).map(item => quickPrompt(item)).join(''))
      + '</div>' : '';
  const starters = '<div class="mentor-start"><div class="mentor-emblem' + (animateLast ? ' greeting-enter' : '') + '">'
    + bot('pixel-login mentor-greeting') + '</div><h3>'
    + escape(t('mentor.start')) + '</h3><p>' + escape(t('mentor.startCopy')) + '</p>'
    + (runtime.chatSnippet ? '' : '<div class="prompt-row">' + (context.metric ? metricPrompt('secondary') : quickPrompt(prompts[0],'secondary'))
      + prompts.slice(1).map(item => quickPrompt(item,'secondary')).join('') + '</div>')
    + '</div>';
  const pending = runtime.chatPending ? '<div class="chat-row' + (animateLast ? ' pending' : '') + '">' + bot('pixel-small','thinking')
    + '<div class="chat-bubble" role="status"><span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span> '
    + escape(t('mentor.thinking')) + '</div></div>' : '';
  const log = messages.length ? messages.map((msg,i) => renderMessage(msg,animateLast && i === messages.length - 1)).join('') + pending : starters;
  const activeSources = [...runtime.chosen].map(sourceLabel).join(', ');
  const snippet = runtime.chatSnippet ? '<div class="composer-snippet"><div>' + icon('file') + '<span><small>'
    + escape(t('mentor.attached')) + '</small><strong title="' + escape(codeReferenceLabel(runtime.chatSnippet)) + '">'
    + escape(codeReferenceLabel(runtime.chatSnippet)) + '</strong></span></div>'
    + btn(icon('close'),'remove-snippet','quiet small',labelAttr(t('mentor.removeSnippet')) + ' title="' + escape(t('mentor.removeSnippet')) + '"')
    + '</div>' : '';
  return '<div class="mentor-shell"><header class="mentor-bar" data-mood="' + mood + '">'
    + '<span class="mentor-avatar">' + bot('',mood) + '</span><div class="mentor-name"><h2 id="mentor-title" tabindex="-1">'
    + escape(t('mentor.name')) + '</h2><small class="mentor-mood">' + escape(t('mentor.' + statusKey)) + '</small></div>'
    + '<div class="mentor-tools">' + btn(icon('plus'),'new-chat','icon-button',labelAttr(t('mentor.newChat')) + ' title="' + escape(t('mentor.newChat')) + '"')
    + btn(icon('close'),'close-mentor','icon-button',labelAttr(t('action.closeMentor')) + ' title="' + escape(t('action.closeMentor')) + '"')
    + '</div></header><p class="mentor-context"><span>' + escape(t('mentor.viewing')) + '</span> ' + icon(context.icon)
    + '<strong title="' + escape(context.label) + '">' + escape(context.label) + '</strong><small>' + escape(live ? 'API' : t('mentor.simulated')) + '</small></p>'
    + '<div class="chat-log" role="log"' + labelAttr(t('mentor.log')) + '>' + log + '</div>'
    + '<div class="chat-compose">' + followUps + '<fieldset class="mentor-sources" id="mentor-sources"'
    + (runtime.sourcesOpen ? '' : ' hidden') + '><legend>' + escape(t('mentor.pickSources')) + '</legend>' + choices + sourceOptions + '</fieldset>'
    + '<form class="chat-form">' + snippet + '<input id="mentor-question" name="question" maxlength="400"' + labelAttr(t('mentor.labelQuestion'))
    + ' placeholder="' + escape(t(runtime.chatSnippet ? 'mentor.snippetPrompt' : 'mentor.placeholder')) + '" required value="' + escape(runtime.chatDraft) + '">'
    + '<div class="composer-actions">' + btn(icon('sources') + ' ' + escape(t('mentor.sources')) + ' <span class="source-count">'
      + runtime.chosen.size + '</span>','toggle-sources','quiet small','aria-controls="mentor-sources" aria-expanded="'
      + runtime.sourcesOpen + '" title="' + escape(t('mentor.chatContext') + (activeSources ? ' · ' + activeSources : '')) + '"')
    + '<button class="button primary mentor-send" type="submit"' + labelAttr(t('mentor.send')) + ' title="' + escape(t('mentor.send'))
    + '"' + (runtime.chatPending ? ' disabled' : '') + '>' + icon('send') + '</button></div></form></div></div>';
}
