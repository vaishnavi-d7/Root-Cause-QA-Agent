/**
 * Utility functions: escaping, dates, formatting, and safe markdown rendering.
 */

/**
 * Safely escape string for insertion into HTML.
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Format ISO timestamp into a clean, human-readable string.
 */
export function formatTime(isoString) {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return String(isoString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch (err) {
    return String(isoString);
  }
}

/**
 * Shorten Git SHA to 7 characters.
 */
export function shortSha(sha) {
  if (!sha) return '—';
  return String(sha).slice(0, 7);
}

/**
 * Human-readable sentence for explorer step.
 */
export function describeStep(step) {
  if (!step) return '';
  const action = step.action;
  if (action === 'goto') {
    return `Open \`${escapeHtml(step.url)}\``;
  }
  if (action === 'fill') {
    let val = step.value;
    if (val === '') val = '(empty)';
    else if (val && val.length > 40) val = val.slice(0, 37) + '... (' + val.length + ' chars)';
    return `Type \`${escapeHtml(val)}\` into **${escapeHtml(step.selector || 'field')}**`;
  }
  if (action === 'select') {
    return `Choose \`${escapeHtml(step.value)}\` in **${escapeHtml(step.selector || 'dropdown')}**`;
  }
  if (action === 'submit') {
    return `Click the form's submit button`;
  }
  return `${escapeHtml(action)} on \`${escapeHtml(step.selector || step.url || '')}\``;
}

/**
 * Safe markdown renderer: escapes HTML first, then applies formatting.
 */
export function renderMarkdown(md) {
  if (!md) return '';
  const escaped = escapeHtml(md);
  const lines = escaped.split(/\r?\n/);
  const htmlParts = [];
  let inCodeBlock = false;
  let codeBuffer = [];
  let inTable = false;
  let tableRows = [];
  let inList = false;

  function flushList() {
    if (inList) {
      htmlParts.push('</ul>');
      inList = false;
    }
  }

  function flushTable() {
    if (inTable) {
      if (tableRows.length > 0) {
        let tableHtml = '<div class="table-container"><table class="data-table">';
        tableRows.forEach((row, idx) => {
          const cells = row.split('|').map(c => c.trim()).filter((_, i, arr) => i > 0 && i < arr.length - 1);
          if (idx === 0) {
            tableHtml += '<thead><tr>' + cells.map(c => `<th>${c}</th>`).join('') + '</tr></thead><tbody>';
          } else if (idx === 1 && cells.every(c => /^:?-+:?$/.test(c))) {
            // separator row
          } else {
            tableHtml += '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>';
          }
        });
        tableHtml += '</tbody></table></div>';
        htmlParts.push(tableHtml);
      }
      tableRows = [];
      inTable = false;
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Fenced code block
    if (line.trim().startsWith('```')) {
      flushList();
      flushTable();
      if (inCodeBlock) {
        htmlParts.push(`<pre><code>${codeBuffer.join('\n')}</code></pre>`);
        codeBuffer = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      continue;
    }

    // Markdown Table
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      flushList();
      inTable = true;
      tableRows.push(line.trim());
      continue;
    } else if (inTable) {
      flushTable();
    }

    // Headings
    if (line.startsWith('### ')) {
      flushList();
      htmlParts.push(`<h3>${formatInline(line.slice(4))}</h3>`);
      continue;
    }
    if (line.startsWith('## ')) {
      flushList();
      htmlParts.push(`<h2>${formatInline(line.slice(3))}</h2>`);
      continue;
    }
    if (line.startsWith('# ')) {
      flushList();
      htmlParts.push(`<h2>${formatInline(line.slice(2))}</h2>`);
      continue;
    }

    // Blockquote
    if (line.startsWith('&gt; ') || line.startsWith('> ')) {
      flushList();
      const quoteText = line.replace(/^(&gt;|>)\s?/, '');
      htmlParts.push(`<blockquote>${formatInline(quoteText)}</blockquote>`);
      continue;
    }

    // Unordered List
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      if (!inList) {
        htmlParts.push('<ul>');
        inList = true;
      }
      htmlParts.push(`<li>${formatInline(line.trim().slice(2))}</li>`);
      continue;
    } else {
      flushList();
    }

    // Blank line
    if (line.trim() === '') {
      continue;
    }

    // Paragraph
    htmlParts.push(`<p>${formatInline(line)}</p>`);
  }

  flushList();
  flushTable();
  if (inCodeBlock) {
    htmlParts.push(`<pre><code>${codeBuffer.join('\n')}</code></pre>`);
  }

  return `<div class="markdown-body">${htmlParts.join('\n')}</div>`;
}

function formatInline(str) {
  return str
    // bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // inline code
    .replace(/`(.+?)`/g, '<code>$1</code>')
    // links
    .replace(/\[(.+?)\]\((https?:\/\/[^\s)]+|\/[^\s)]+|#[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

/**
 * Trigger client file download.
 */
export function downloadFile(filename, text, mimeType = 'text/markdown') {
  const blob = new Blob([text], { type: `${mimeType};charset=utf-8;` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
