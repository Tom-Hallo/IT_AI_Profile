import { escape } from './ui.js';

const copy = (vi, en) => (typeof document !== 'undefined' && document.documentElement.lang === 'en') ? en : vi;

export function isSectionHeading(str) {
  const clean = String(str || '').trim().replace(/[:\-_#]+$/, '').trim();
  return /^(Education\s*(and|&)?\s*Qualifications|Work\s*Experience|Experience|Professional\s*Experience|Employment\s*History|Additional\s*Information|Additional\s*Info|Projects|Key\s*Projects|Technical\s*Skills|Skills|Certifications|Certificates|Summary|Professional\s*Summary|Profile|Học\s*vấn(?:\s*(&|và)?\s*bằng\s*cấp)?|Kinh\s*nghiệm(?:\s*làm\s*việc)?|Kinh\s*nghiệm\s*chuyên\s*môn|Thông\s*tin\s*(bổ\s*sung|thêm)|Dự\s*án(?:\s*(tiêu\s*biểu|cá\s*nhân|tham\s*gia))?|Kỹ\s*năng(?:\s*(chuyên\s*môn|kỹ\s*thuật|mềm))?|Chứng\s*chỉ|Giải\s*thưởng|Thành\s*tích|Tóm\s*tắt(?:\s*chuyên\s*môn)?|Mục\s*tiêu\s*nghề\s*nghiệp|Giới\s*thiệu(?:\s*bản\s*thân)?)$/i.test(clean);
}

export function parseCVForReference(rawText, draftName = '', draftRole = '') {
  try {
    const lines = String(rawText || '').split(/\r?\n/).map(l => l.trimEnd());
    let idx = 0;

    let headerName = (draftName || '').trim();
    let headerContact = '';
    let headerRole = (draftRole || '').trim();

    // Bỏ qua dòng trống đầu
    while (idx < lines.length && !lines[idx].trim()) idx++;

    // Kiểm tra họ tên ở dòng 0 nếu chưa có hoặc có tên mẫu
    if (idx < lines.length) {
      const line0 = lines[idx].trim();
      if (line0 && line0.length < 80 && !isSectionHeading(line0)) {
        if (!headerName || headerName === 'Dev' || headerName.toLowerCase() === 'bản nháp cv' || headerName.toLowerCase() === 'cv chưa đặt tên') {
          headerName = line0;
        }
        if (line0.toLowerCase() === headerName.toLowerCase() || line0.toLowerCase() === (draftName || '').trim().toLowerCase()) {
          idx++;
        }
      }
    }

    // Kiểm tra thông tin liên hệ ở dòng tiếp theo
    while (idx < lines.length && !lines[idx].trim()) idx++;
    if (idx < lines.length) {
      const line1 = lines[idx].trim();
      if (line1 && (/^(e-mail|email|tel|phone|đt|sđt|contact|địa chỉ|address|linkedin|github)/i.test(line1) || line1.includes('@'))) {
        headerContact = line1;
        idx++;
      }
    }

    const sections = [];
    let currentSection = null;
    let currentEntry = null;

    function flushEntry() {
      if (currentEntry && currentSection) {
        if (!Array.isArray(currentEntry.bullets)) currentEntry.bullets = [];
        currentSection.entries.push(currentEntry);
        currentEntry = null;
      }
    }

    function flushSection() {
      flushEntry();
      if (currentSection) {
        sections.push(currentSection);
        currentSection = null;
      }
    }

    // Regex hỗ trợ cả tiếng Anh và tiếng Việt có dấu
    const DATE_PREFIX_REGEX = /^((?:(?:Tháng\s*)?\d{1,2}\/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/ ]*\d{2,4}|\d{4})\s*(?:[–—\-]|\bto\b|\bđến\b)\s*(?:(?:Tháng\s*)?\d{1,2}\/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/ ]*\d{2,4}|\d{4}|Present|Current|Hiện tại|Nay)\b|\d{4}\s*[-–—]\s*\d{4}|\d{4}\b)/i;
    const LABEL_PREFIX_REGEX = /^([A-Z\u00C0-\u024F\u1EA0-\u1EF9][a-zA-Z\u00C0-\u024F\u1EA0-\u1EF9\s]{1,35}):\s*(.*)$/;
    const BULLET_PREFIX_REGEX = /^[\uf0b7•\-\*\–\+]\s*(.*)$/;

    for (; idx < lines.length; idx++) {
      const raw = lines[idx];
      const trimmed = raw.trim();
      if (!trimmed) continue;

      if (isSectionHeading(trimmed)) {
        flushSection();
        currentSection = {
          title: trimmed.replace(/[:\-_]+$/, ''),
          entries: []
        };
        continue;
      }

      if (!currentSection) {
        currentSection = {
          title: '',
          entries: []
        };
      }

      // Mốc thời gian (cột trái)
      const dateMatch = trimmed.match(DATE_PREFIX_REGEX);
      if (dateMatch) {
        flushEntry();
        const dateStr = dateMatch[1];
        const remainder = trimmed.slice(dateMatch[0].length).trim();

        let org = remainder;
        let loc = '';
        const splitMultiSpace = remainder.split(/\s{2,}|\t+/);
        if (splitMultiSpace.length >= 2) {
          org = splitMultiSpace[0].trim();
          loc = splitMultiSpace.slice(1).join(' ').trim();
        } else if (org.includes(' - ')) {
          const parts = org.split(' - ');
          org = parts[0].trim();
          loc = parts.slice(1).join(' - ').trim();
        } else if (org.includes(' | ')) {
          const parts = org.split(' | ');
          org = parts[0].trim();
          loc = parts.slice(1).join(' | ').trim();
        }

        currentEntry = {
          type: 'dated',
          date: dateStr,
          org: org,
          loc: loc,
          role: '',
          subLoc: '',
          bullets: []
        };
        continue;
      }

      // Nhãn phân mục (cột trái)
      const labelMatch = trimmed.match(LABEL_PREFIX_REGEX);
      if (labelMatch) {
        flushEntry();
        currentEntry = {
          type: 'labeled',
          label: labelMatch[1] + ':',
          content: labelMatch[2],
          bullets: []
        };
        continue;
      }

      // Gạch đầu dòng
      const bulletMatch = trimmed.match(BULLET_PREFIX_REGEX);
      if (bulletMatch) {
        if (currentEntry) {
          if (!Array.isArray(currentEntry.bullets)) {
            currentEntry.bullets = [];
          }
          currentEntry.bullets.push(bulletMatch[1]);
        } else {
          currentEntry = {
            type: 'bullet_only',
            bullets: [bulletMatch[1]]
          };
        }
        continue;
      }

      // Dòng phụ nối tiếp
      if (currentEntry && currentEntry.type === 'dated') {
        if (!currentEntry.role && (!currentEntry.bullets || currentEntry.bullets.length === 0)) {
          const splitMultiSpace = trimmed.split(/\s{2,}|\t+/);
          if (splitMultiSpace.length >= 2) {
            currentEntry.role = splitMultiSpace[0].trim();
            currentEntry.subLoc = splitMultiSpace.slice(1).join(' ').trim();
          } else {
            currentEntry.role = trimmed;
          }
        } else if (currentEntry.bullets && currentEntry.bullets.length > 0) {
          currentEntry.bullets[currentEntry.bullets.length - 1] += ' ' + trimmed;
        } else {
          currentEntry.role = currentEntry.role ? currentEntry.role + ' ' + trimmed : trimmed;
        }
        continue;
      }

      if (currentEntry && currentEntry.type === 'labeled') {
        if (!Array.isArray(currentEntry.bullets)) {
          currentEntry.bullets = [];
        }
        if (trimmed.startsWith('- ') || trimmed.startsWith('• ') || trimmed.startsWith('\uf0b7 ')) {
          currentEntry.bullets.push(trimmed.replace(/^[\uf0b7•\-\*\–\+]\s*/, ''));
        } else if (currentEntry.bullets.length > 0) {
          currentEntry.bullets[currentEntry.bullets.length - 1] += ' ' + trimmed;
        } else if (
          (currentSection?.title || '').toLowerCase().includes('achievement') ||
          (currentEntry.label || '').toLowerCase().includes('achievement') ||
          (currentSection?.title || '').toLowerCase().includes('thành tích')
        ) {
          currentEntry.bullets.push(trimmed);
        } else {
          currentEntry.content = (currentEntry.content ? currentEntry.content + ' ' : '') + trimmed;
        }
        continue;
      }

      if (!currentEntry) {
        currentEntry = {
          type: 'text',
          text: trimmed,
          bullets: []
        };
      } else if (currentEntry.type === 'text') {
        currentEntry.text += '\n' + trimmed;
      } else {
        flushEntry();
        currentEntry = {
          type: 'text',
          text: trimmed,
          bullets: []
        };
      }
    }

    flushSection();

    return {
      name: headerName || (draftName || '').trim() || 'Forename SURNAME',
      role: headerRole || (draftRole || '').trim(),
      contact: headerContact,
      sections: sections
    };
  } catch (err) {
    console.error('Error parsing reference CV:', err);
    return {
      name: draftName || 'Forename SURNAME',
      role: draftRole || '',
      contact: '',
      sections: [
        {
          title: '',
          entries: [{ type: 'text', text: String(rawText || ''), bullets: [] }]
        }
      ]
    };
  }
}

export function renderReferenceCV(draft) {
  try {
    const rawText = (draft?.body || '').trim();
    if (!rawText) {
      return '<div class="cv-paper cv-reference-paper" data-template="reference">'
        + '<header class="cv-ref-header">'
        + '<h1 class="cv-ref-name" id="cv-name" contenteditable="true" spellcheck="false">' + escape(draft?.name || copy('Họ và tên', 'Full Name')) + '</h1>'
        + (draft?.role
          ? '<p class="cv-ref-role" id="cv-role" contenteditable="true" spellcheck="false">' + escape(draft.role) + '</p>'
          : '<p class="cv-ref-role" id="cv-role" contenteditable="true" spellcheck="false" style="display:none"></p>')
        + '</header>'
        + '<div class="cv-body cv-ref-body" id="cv-body" contenteditable="true" spellcheck="false"><p class="subtle">' + escape(copy('Chưa có nội dung CV. Hãy nhập thông tin hoặc tải tệp lên.', 'Empty CV content. Enter details or upload a file.')) + '</p></div>'
        + '</div>';
    }

    const data = parseCVForReference(rawText, draft?.name, draft?.role);

    let html = '<div class="cv-paper cv-reference-paper" data-template="reference">';

    // Header chuẩn Executive: Tên căn giữa, thông tin liên lạc ngay dưới (hỗ trợ chỉnh sửa trực tiếp)
    html += '<header class="cv-ref-header">';
    html += '<h1 class="cv-ref-name" id="cv-name" contenteditable="true" spellcheck="false">' + escape(data.name || draft?.name || 'Forename SURNAME') + '</h1>';
    if (data.role || draft?.role) {
      html += '<p class="cv-ref-role" id="cv-role" contenteditable="true" spellcheck="false">' + escape(data.role || draft?.role || '') + '</p>';
    } else {
      html += '<p class="cv-ref-role" id="cv-role" contenteditable="true" spellcheck="false" style="display:none"></p>';
    }
    if (data.contact) {
      html += '<div class="cv-ref-contact" id="cv-contact" contenteditable="true" spellcheck="false">' + escape(data.contact) + '</div>';
    }
    html += '</header>';

    // Thân CV bố cục 2 cột chuẩn 1:1 theo mẫu gửi kèm (hỗ trợ chỉnh sửa trực tiếp)
    html += '<div class="cv-body cv-ref-body" id="cv-body" contenteditable="true" spellcheck="false">';

    for (const sec of data.sections) {
      html += '<section class="cv-ref-section">';
      if (sec.title) {
        html += '<h2 class="cv-ref-section-title">' + escape(sec.title) + '</h2>';
      }
      html += '<div class="cv-ref-section-content">';

      for (const entry of (sec.entries || [])) {
        if (entry.type === 'dated') {
          html += '<article class="cv-ref-entry cv-ref-dated-entry">';
          html += '<div class="cv-ref-col-date">' + escape(entry.date) + '</div>';
          html += '<div class="cv-ref-col-details">';
          if (entry.org || entry.loc) {
            html += '<div class="cv-ref-entry-head"><strong class="cv-ref-org">' + escape(entry.org) + '</strong>';
            if (entry.loc) {
              html += '<span class="cv-ref-loc">' + escape(entry.loc) + '</span>';
            }
            html += '</div>';
          }
          if (entry.role || entry.subLoc) {
            html += '<div class="cv-ref-entry-sub"><span class="cv-ref-role-title">' + escape(entry.role) + '</span>';
            if (entry.subLoc) {
              html += '<span class="cv-ref-sub-loc">' + escape(entry.subLoc) + '</span>';
            }
            html += '</div>';
          }
          if (entry.bullets && entry.bullets.length > 0) {
            html += '<ul class="cv-ref-bullets">';
            for (const b of entry.bullets) {
              html += '<li>' + escape(b) + '</li>';
            }
            html += '</ul>';
          }
          html += '</div></article>';
        } else if (entry.type === 'labeled') {
          html += '<article class="cv-ref-entry cv-ref-labeled-entry">';
          html += '<div class="cv-ref-col-date"><strong>' + escape(entry.label) + '</strong></div>';
          html += '<div class="cv-ref-col-details">';
          if (entry.content) {
            html += '<div class="cv-ref-label-desc">' + escape(entry.content) + '</div>';
          }
          if (entry.bullets && entry.bullets.length > 0) {
            html += '<ul class="cv-ref-bullets cv-ref-sub-bullets">';
            for (const b of entry.bullets) {
              html += '<li>' + escape(b) + '</li>';
            }
            html += '</ul>';
          }
          html += '</div></article>';
        } else if (entry.type === 'bullet_only') {
          html += '<article class="cv-ref-entry cv-ref-bullet-entry">';
          html += '<div class="cv-ref-col-date"></div>';
          html += '<div class="cv-ref-col-details"><ul class="cv-ref-bullets">';
          for (const b of (entry.bullets || [])) {
            html += '<li>' + escape(b) + '</li>';
          }
          html += '</ul></div></article>';
        } else {
          html += '<article class="cv-ref-entry cv-ref-text-entry">';
          html += '<div class="cv-ref-col-details"><p class="cv-ref-text">' + escape(entry.text || '') + '</p></div>';
          html += '</article>';
        }
      }

      html += '</div></section>';
    }

    html += '</div>'; // .cv-ref-body
    html += '</div>'; // .cv-reference-paper
    return html;
  } catch (err) {
    console.error('Error rendering reference CV:', err);
    return '<div class="cv-paper cv-reference-paper" data-template="reference">'
      + '<header class="cv-ref-header">'
      + '<h1 class="cv-ref-name" id="cv-name" contenteditable="true" spellcheck="false">' + escape(draft?.name || 'Forename SURNAME') + '</h1>'
      + (draft?.role ? '<p class="cv-ref-role" id="cv-role" contenteditable="true" spellcheck="false">' + escape(draft.role) + '</p>' : '')
      + '</header>'
      + '<div class="cv-body cv-ref-body" id="cv-body" contenteditable="true" spellcheck="false" style="white-space:pre-wrap">' + escape(draft?.body || '') + '</div>'
      + '</div>';
  }
}

/**
 * Chuyển đổi dữ liệu cấu trúc thành văn bản Markdown/Plain-text hai chiều (Round-trip safe).
 */
export function serializeCVFromSections(data) {
  if (!data || !Array.isArray(data.sections)) return '';
  const lines = [];
  if (data.contact && data.contact.trim()) {
    lines.push(data.contact.trim());
    lines.push('');
  }
  for (const sec of data.sections) {
    if (!sec || !sec.title) continue;
    lines.push(sec.title.trim().toUpperCase());
    for (const entry of (sec.entries || [])) {
      if (entry.type === 'dated') {
        let head = (entry.date || '').trim();
        if (entry.org) head += (head ? ' | ' : '') + entry.org.trim();
        if (entry.loc) head += ' | ' + entry.loc.trim();
        if (head) lines.push(head);
        if (entry.role || entry.subLoc) {
          lines.push(entry.subLoc ? `${entry.role.trim()}  ${entry.subLoc.trim()}` : entry.role.trim());
        }
        for (const b of (entry.bullets || [])) {
          if (b && b.trim()) lines.push(`- ${b.trim()}`);
        }
        lines.push('');
      } else if (entry.type === 'labeled') {
        const lbl = (entry.label || '').trim().replace(/:$/, '');
        const cnt = (entry.content || '').trim();
        lines.push(lbl ? `${lbl}: ${cnt}` : cnt);
        for (const b of (entry.bullets || [])) {
          if (b && b.trim()) lines.push(`- ${b.trim()}`);
        }
        lines.push('');
      } else if (entry.type === 'bullet_only') {
        for (const b of (entry.bullets || [])) {
          if (b && b.trim()) lines.push(`- ${b.trim()}`);
        }
        lines.push('');
      } else {
        if (entry.text && entry.text.trim()) lines.push(entry.text.trim());
        for (const b of (entry.bullets || [])) {
          if (b && b.trim()) lines.push(`- ${b.trim()}`);
        }
        lines.push('');
      }
    }
  }
  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

export function getSectionIcon(title) {
  const t = String(title || '').toLowerCase();
  if (t.includes('học vấn') || t.includes('education') || t.includes('bằng cấp')) return '🎓';
  if (t.includes('kinh nghiệm') || t.includes('experience') || t.includes('employment') || t.includes('làm việc')) return '💼';
  if (t.includes('dự án') || t.includes('project')) return '🚀';
  if (t.includes('kỹ năng') || t.includes('skill')) return '⚡';
  if (t.includes('chứng chỉ') || t.includes('certification') || t.includes('certificate')) return '📜';
  if (t.includes('tóm tắt') || t.includes('summary') || t.includes('giới thiệu') || t.includes('profile')) return '📝';
  if (t.includes('hoạt động') || t.includes('activity') || t.includes('volunteer')) return '🤝';
  if (t.includes('giải thưởng') || t.includes('thành tích') || t.includes('award') || t.includes('honor')) return '🏆';
  return '📌';
}
