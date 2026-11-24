import {mentorSources} from './data.js';
import {getLanguage, sourceLabel, t} from './i18n.js';
import {replyCopy, replySourceLabel} from './mentor-model.js';
import {codeReferenceLabel} from './evidence.js';
import {attr, bot, btn, escape, field, icon, labelAttr, option, tags} from './ui.js';

function replyMood(message) {
  if (message.action && !message.actionApplied && !message.actionDismissed) return 'review';
  return message.used?.length ? 'happy' : 'curious';
}

function formatInline(str) {
  if (!str) return '';
  let escaped = escape(str);
  // markdown links: [label](https://...)
  escaped = escaped.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-link">$1 ↗</a>');
  escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  escaped = escaped.replace(/__(.+?)__/g, '<strong>$1</strong>');
  escaped = escaped.replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, '<em>$1</em>');
  escaped = escaped.replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>');
  escaped = escaped.replace(/\[(E\d+(?:,\s*E\d+)*)\]/g, '<span class="evidence-pill">$1</span>');
  return escaped;
}

function isTableSeparator(line) {
  const trimmed = line.trim();
  return /^\|?[\s\-:|]+\|?$/.test(trimmed) && trimmed.includes('-') && (trimmed.includes('|') || trimmed.includes('+'));
}

function isTableLine(line) {
  const trimmed = line.trim();
  if (trimmed.includes('\t') && trimmed.split('\t').length >= 2) return true;
  if (trimmed.includes('|')) {
    if (trimmed.startsWith('|') || trimmed.endsWith('|')) return true;
    if (trimmed.split('|').length >= 2) return true;
  }
  return false;
}

function parseTableLineCells(line) {
  let trimmed = line.trim();
  if (trimmed.includes('\t')) {
    return trimmed.split('\t').map(c => c.trim()).filter(c => c.length > 0);
  }
  if (trimmed.startsWith('|')) trimmed = trimmed.slice(1);
  if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1);
  return trimmed.split('|').map(c => c.trim());
}

function renderTable(tableLines) {
  if (tableLines.length < 2) {
    return tableLines.map(l => '<p>' + formatInline(l) + '</p>').join('');
  }

  let headerIndex = 0;
  let sepIndex = -1;
  for (let i = 0; i < tableLines.length; i++) {
    if (isTableSeparator(tableLines[i])) {
      sepIndex = i;
      headerIndex = i - 1;
      break;
    }
  }

  let aligns = [];
  let headerCells = [];
  let bodyStartIndex = 1;

  if (sepIndex !== -1 && headerIndex >= 0) {
    headerCells = parseTableLineCells(tableLines[headerIndex]);
    const sepCells = parseTableLineCells(tableLines[sepIndex]);
    aligns = sepCells.map(c => {
      const left = c.startsWith(':');
      const right = c.endsWith(':');
      if (left && right) return 'center';
      if (right) return 'right';
      return 'left';
    });
    bodyStartIndex = sepIndex + 1;
  } else {
    headerCells = parseTableLineCells(tableLines[0]);
    aligns = headerCells.map(() => 'left');
    bodyStartIndex = 1;
  }

  let preHtml = '';
  if (sepIndex !== -1 && headerIndex > 0) {
    preHtml = tableLines.slice(0, headerIndex).map(l => '<p>' + formatInline(l) + '</p>').join('');
  }

  const thHtml = headerCells.map((cell, idx) => {
    const align = aligns[idx] || 'left';
    return '<th style="text-align:' + align + '">' + formatInline(cell) + '</th>';
  }).join('');

  const bodyRows = [];
  for (let i = bodyStartIndex; i < tableLines.length; i++) {
    const rowLine = tableLines[i].trim();
    if (!rowLine || isTableSeparator(rowLine)) continue;
    const cells = parseTableLineCells(rowLine);
    if (cells.length === 0) continue;
    const tdHtml = cells.map((cell, idx) => {
      const align = aligns[idx] || 'left';
      return '<td style="text-align:' + align + '">' + formatInline(cell) + '</td>';
    }).join('');
    bodyRows.push('<tr>' + tdHtml + '</tr>');
  }

  if (bodyRows.length === 0 && headerCells.length === 0) {
    return tableLines.map(l => '<p>' + formatInline(l) + '</p>').join('');
  }

  return preHtml + '<div class="chat-table-wrapper">'
    + '<table class="chat-md-table">'
    + '<thead><tr>' + thHtml + '</tr></thead>'
    + '<tbody>' + bodyRows.join('') + '</tbody>'
    + '</table></div>';
}

function formatMentorMarkdown(text) {
  if (!text) return '';
  const lines = text.split(/\r?\n/);
  const blocks = [];
  let inCodeBlock = false;
  let codeBlockLang = '';
  let codeBlockLines = [];
  let currentList = null;
  let currentTable = [];

  function flushList() {
    if (currentList && currentList.items.length > 0) {
      const tag = currentList.type === 'ol' ? 'ol' : 'ul';
      const cls = currentList.type === 'ol' ? 'chat-md-list chat-md-ordered' : 'chat-md-list';
      blocks.push('<' + tag + ' class="' + cls + '">' + currentList.items.join('') + '</' + tag + '>');
      currentList = null;
    }
  }

  function flushTable() {
    if (currentTable.length > 0) {
      blocks.push(renderTable(currentTable));
      currentTable = [];
    }
  }

  function flushAll() {
    flushList();
    flushTable();
  }

  for (let rawLine of lines) {
    const line = rawLine.trim();

    if (inCodeBlock) {
      if (line.startsWith('```')) {
        inCodeBlock = false;
        blocks.push(
          '<div class="chat-code-wrapper">'
          + '<div class="chat-code-header">'
          + '<span class="chat-code-lang">' + escape(codeBlockLang || 'code') + '</span>'
          + '<button class="chat-code-copy-btn" type="button" data-act="copy-code">Sao chép</button>'
          + '</div>'
          + '<pre class="chat-code-block"><code>' + escape(codeBlockLines.join('\n')) + '</code></pre>'
          + '</div>'
        );
        codeBlockLang = '';
        codeBlockLines = [];
      } else {
        codeBlockLines.push(rawLine);
      }
      continue;
    }

    if (line.startsWith('```')) {
      flushAll();
      inCodeBlock = true;
      codeBlockLang = line.slice(3).trim();
      codeBlockLines = [];
      continue;
    }

    if (!line) {
      flushAll();
      continue;
    }

    // Table rows (Markdown pipe tables or Tab-separated tables)
    if (isTableLine(line)) {
      flushList();
      currentTable.push(line);
      continue;
    } else {
      flushTable();
    }

    // Headings: #, ##, ###, ####, #####, ######
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushAll();
      const level = headingMatch[1].length;
      const headingText = headingMatch[2].trim();
      const tag = level <= 2 ? 'h3' : level === 3 ? 'h4' : 'h5';
      blocks.push('<' + tag + ' class="chat-md-heading chat-md-h' + level + '">' + formatInline(headingText) + '</' + tag + '>');
      continue;
    }

    // Divider
    if (/^(\-{3,}|\*{3,}|_{3,})$/.test(line)) {
      flushAll();
      blocks.push('<hr class="chat-md-divider" />');
      continue;
    }

    // Blockquote
    const quoteMatch = line.match(/^>\s*(.*)$/);
    if (quoteMatch) {
      flushAll();
      blocks.push('<blockquote class="chat-md-quote">' + formatInline(quoteMatch[1]) + '</blockquote>');
      continue;
    }

    // Unordered list: - item or * item
    const ulMatch = line.match(/^[-*]\s+(.+)$/);
    if (ulMatch) {
      if (!currentList || currentList.type !== 'ul') {
        flushList();
        currentList = { type: 'ul', items: [] };
      }
      currentList.items.push('<li>' + formatInline(ulMatch[1]) + '</li>');
      continue;
    }

    // Ordered list: 1. item, 2. item
    const olMatch = line.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      if (!currentList || currentList.type !== 'ol') {
        flushList();
        currentList = { type: 'ol', items: [] };
      }
      currentList.items.push('<li>' + formatInline(olMatch[1]) + '</li>');
      continue;
    }

    // Normal paragraph
    flushAll();
    blocks.push('<p>' + formatInline(line) + '</p>');
  }

  flushAll();
  if (inCodeBlock) {
    blocks.push(
      '<div class="chat-code-wrapper">'
      + '<div class="chat-code-header">'
      + '<span class="chat-code-lang">' + escape(codeBlockLang || 'code') + '</span>'
      + '<button class="chat-code-copy-btn" type="button" data-act="copy-code">Sao chép</button>'
      + '</div>'
      + '<pre class="chat-code-block"><code>' + escape(codeBlockLines.join('\n')) + '</code></pre>'
      + '</div>'
    );
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
  let actionHtml = '';
  if (msg.action) {
    if (msg.actionApplied) {
      actionHtml = '<div class="chat-action-card applied"><span class="badge green">✓ ' + escape(t('mentor.applied')) + '</span></div>';
    } else if (msg.actionDismissed) {
      const isEn = getLanguage() === 'en';
      const declinedBadge = isEn ? '✕ Proposal declined' : '✕ Đã từ chối đề xuất';
      const reconsiderBtn = isEn ? 'Reconsider' : 'Mở lại (Suy nghĩ thêm)';
      actionHtml = '<div class="chat-action-card dismissed">'
        + '<div class="chat-action-toolbar">'
        + '<span class="badge">' + escape(declinedBadge) + '</span>'
        + '<button class="button secondary small chat-action-reopen" type="button" data-act="agent-reconsider" data-id="' + msg.id + '">' + escape(reconsiderBtn) + '</button>'
        + '</div></div>';
    } else {
      const isEn = getLanguage() === 'en';
      const act = msg.action;
      const targetTitle = act.proposal?.add_milestone?.title || act.proposal?.title || act.proposal?.add_milestone?.skill || '';
      const actionLabel = act.tool === 'update_roadmap'
        ? (isEn ? 'Apply to Roadmap' : 'Áp dụng vào Lộ trình')
        : act.tool === 'create_roadmap' ? (isEn ? 'Create Roadmap' : 'Tạo Lộ trình này')
        : act.tool === 'create_cv' ? (isEn ? 'Save to CV Studio' : 'Lưu vào CV Studio')
        : t('mentor.preview');
      const headerTitle = isEn ? 'AI Action Proposal' : 'Đề xuất cập nhật từ AI';
      const milestoneLabel = isEn ? 'Proposed item:' : 'Cột mốc đề xuất:';
      const declineLabel = isEn ? 'Decline' : 'Từ chối';
      const hintText = isEn
        ? 'Click to apply to your Roadmap, or decline if not needed.'
        : 'Bấm để thêm vào Lộ trình, hoặc từ chối nếu không cần.';
      actionHtml = '<div class="chat-action-card">'
        + '<div class="chat-action-toolbar">'
        + '<div class="chat-action-header chat-action-card-header">'
        + '<span class="chat-action-badge-dot">⚡</span>'
        + '<span class="chat-action-kicker">' + escape(headerTitle) + '</span>'
        + '</div>'
        + '<div class="chat-action-controls-row">'
        + btn(icon('check') + ' ' + escape(actionLabel),'agent-preview','primary small chat-action-trigger',attr('id',msg.id))
        + btn(icon('close') + ' ' + escape(declineLabel),'agent-decline','secondary small chat-action-decline-btn',attr('id',msg.id))
        + '</div>'
        + '</div>'
        + '<div class="chat-action-card-body">'
        + (targetTitle ? '<div class="chat-action-target-banner">'
            + '<div class="chat-action-target-header"><span class="chat-action-target-tag">🎯 ' + escape(milestoneLabel) + '</span></div>'
            + '<div class="chat-action-target-title">' + escape(targetTitle) + '</div>'
            + '</div>' : '')
        + '<p class="chat-action-impact">' + escape(act.impact || '') + '</p>'
        + '</div>'
        + '<p class="chat-action-hint">💡 ' + escape(hintText) + '</p>'
        + '</div>';
    }
  }

  let existingMilestoneCard = '';
  if (msg.existingSkill && !msg.action) {
    const isEn = getLanguage() === 'en';
    const title = msg.existingMilestoneTitle || msg.existingSkill;
    const roadmapName = msg.existingRoadmapTitle ? ` (${msg.existingRoadmapTitle})` : '';
    const cardTitle = isEn ? 'Existing Milestone in Roadmap' : 'Cột mốc đã có trong Lộ trình';
    const cardDesc = isEn
      ? `You already have "${title}" in your roadmap${roadmapName}. Click below to view milestone details and practice tasks.`
      : `Bạn đã có sẵn cột mốc "${title}" trong lộ trình${roadmapName} của mình. Bấm bên dưới để xem chi tiết mục tiêu và kế hoạch rèn luyện.`;
    const btnLabel = isEn ? 'View Milestone in Roadmap' : 'Xem chi tiết cột mốc trong Lộ trình';

    existingMilestoneCard = '<div class="chat-action-card existing-milestone-card">'
      + '<div class="chat-action-toolbar">'
      + '<div class="chat-action-header chat-action-card-header">'
      + '<span class="chat-action-badge-dot">🎯</span>'
      + '<span class="chat-action-kicker">' + escape(cardTitle) + '</span>'
      + '</div>'
      + '<div class="chat-action-controls-row">'
      + '<button class="button primary small chat-action-trigger existing-view-btn" type="button" data-act="view-skill-roadmap" data-skill="' + escape(msg.existingSkill) + '">'
      + icon('target') + ' ' + escape(btnLabel)
      + '</button>'
      + '</div>'
      + '</div>'
      + '<div class="chat-action-card-body">'
      + '<div class="chat-action-target-banner existing-milestone-banner">'
      + '<div class="chat-action-target-header"><span class="chat-action-target-tag">✓ ' + (isEn ? 'Already in Roadmap' : 'Đã có trong Lộ trình') + '</span></div>'
      + '<div class="chat-action-target-title">' + escape(title) + '</div>'
      + '</div>'
      + '<p class="chat-action-impact">' + escape(cardDesc) + '</p>'
      + '</div>'
      + '</div>';
  }

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
    + (msg.used?.length ? tags(msg.used.map(sourceLabel),'green') : '') + source + actionHtml + existingMilestoneCard
    + '</div></div>';
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
    + '<div class="chat-bubble" role="status">'
    + escape(t('mentor.thinking'))
    + ' <span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span>'
    + '</div></div>' : '';
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
