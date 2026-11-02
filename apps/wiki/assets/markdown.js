/* 轻量 Markdown 渲染器（自包含，无外部 CDN 依赖）
 * 支持：标题、加粗、斜体、行内代码、围栏代码块、有序/无序列表、
 *       引用、分隔线、链接、图片、删除线、简易表格。
 * 安全性：先转义 HTML，链接仅放行 http/https/mailto/相对路径，阻断 javascript: 等。
 */
(function () {
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function sanitizeUrl(u) {
    u = String(u || '').trim();
    if (/^(https?:|mailto:|#|\/|\.\/|\.\.\/)/i.test(u)) return u;
    if (/^[\w.+-]+@[\w.-]+\.\w+$/.test(u)) return 'mailto:' + u;
    return '#';
  }

  function inline(text) {
    // 图片 ![alt](url)
    text = text.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, function (_, alt, url) {
      return '<img alt="' + alt + '" src="' + sanitizeUrl(url) + '">';
    });
    // 链接 [文本](url)
    text = text.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (_, t, url) {
      return '<a href="' + sanitizeUrl(url) + '" target="_blank" rel="noopener">' + t + '</a>';
    });
    // 行内代码 `code`
    text = text.replace(/`([^`]+)`/g, function (_, c) {
      return '<code>' + c + '</code>';
    });
    // 加粗 **text** / __text__
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    // 斜体 *text* / _text_
    text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    text = text.replace(/(^|[^_\w])_([^_]+)_(?![\w_])/g, '$1<em>$2</em>');
    // 删除线 ~~text~~
    text = text.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    return text;
  }

  function renderTable(rows) {
    // rows: 字符串数组（每行原始 markdown，已去首尾空格）
    var out = '<table>';
    for (var i = 0; i < rows.length; i++) {
      var cells = rows[i].split('|').map(function (c) { return c.trim(); });
      // 跳过分隔行（如 ---|--- ）
      if (cells.every(function (c) { return /^:?-{2,}:?$/.test(c); })) continue;
      out += '<tr>';
      cells.forEach(function (c) {
        out += '<td>' + inline(escapeHtml(c)) + '</td>';
      });
      out += '</tr>';
    }
    out += '</table>';
    return out;
  }

  function render(src) {
    src = String(src || '').replace(/\r\n?/g, '\n');

    // 保护围栏代码块
    var codeBlocks = [];
    src = src.replace(/```([\s\S]*?)```/g, function (_, code) {
      var i = codeBlocks.length;
      codeBlocks.push(code.replace(/^\n/, '').replace(/\n$/, ''));
      return '%%CODE' + i + '%%';
    });

    var lines = src.split('\n');
    var html = '';
    var i = 0;
    var listType = null;   // 'ul' | 'ol'
    var listItems = [];

    function flushList() {
      if (listType) {
        html += '<' + listType + '>';
        listItems.forEach(function (it) { html += '<li>' + inline(escapeHtml(it)) + '</li>'; });
        html += '</' + listType + '>';
        listType = null;
        listItems = [];
      }
    }

    while (i < lines.length) {
      var line = lines[i];

      var ph = line.match(/^%%CODE(\d+)%%$/);
      if (ph) {
        flushList();
        html += '<pre><code>' + escapeHtml(codeBlocks[+ph[1]]) + '</code></pre>';
        i++;
        continue;
      }
      if (/^\s*$/.test(line)) { flushList(); i++; continue; }

      var h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        flushList();
        var lvl = h[1].length;
        html += '<h' + lvl + '>' + inline(escapeHtml(h[2])) + '</h' + lvl + '>';
        i++;
        continue;
      }
      if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
        flushList();
        html += '<hr>';
        i++;
        continue;
      }
      if (/^\s*>\s?/.test(line)) {
        flushList();
        var q = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
          q.push(lines[i].replace(/^\s*>\s?/, ''));
          i++;
        }
        html += '<blockquote>' + inline(escapeHtml(q.join(' '))) + '</blockquote>';
        continue;
      }
      // 表格：以 | 开头且下一行像分隔行
      if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length &&
          /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && /-/.test(lines[i + 1])) {
        flushList();
        var trows = [line];
        i++;
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
          trows.push(lines[i].trim().replace(/^\|/, '').replace(/\|$/, ''));
          i++;
        }
        html += renderTable(trows);
        continue;
      }
      var ul = line.match(/^\s*[-*+]\s+(.*)$/);
      if (ul) {
        if (listType && listType !== 'ul') flushList();
        listType = 'ul';
        listItems.push(ul[1]);
        i++;
        continue;
      }
      var ol = line.match(/^\s*\d+\.\s+(.*)$/);
      if (ol) {
        if (listType && listType !== 'ol') flushList();
        listType = 'ol';
        listItems.push(ol[1]);
        i++;
        continue;
      }

      // 段落：合并连续普通行
      flushList();
      var para = [line];
      i++;
      while (i < lines.length && !/^\s*$/.test(lines[i]) &&
             !/^(#{1,6})\s/.test(lines[i]) &&
             !/^\s*>\s?/.test(lines[i]) &&
             !/^\s*[-*+]\s+/.test(lines[i]) &&
             !/^\s*\d+\.\s+/.test(lines[i]) &&
             !/^%%CODE\d+%%$/.test(lines[i]) &&
             !/^\s*(---|\*\*\*|___)\s*$/.test(lines[i]) &&
             !/^\s*\|.*\|\s*$/.test(lines[i])) {
        para.push(lines[i]);
        i++;
      }
      html += '<p>' + inline(escapeHtml(para.join(' '))) + '</p>';
    }
    flushList();
    return html;
  }

  window.renderMarkdown = render;
})();
