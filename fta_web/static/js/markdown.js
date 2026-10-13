/**
 * markdown.js -- a small Markdown renderer for the AI assistant's replies.
 *
 * WHY NOT A LIBRARY
 * -----------------
 * A model's reply is untrusted input, exactly like a node name. Every Markdown
 * library ends in an HTML string that has to be sanitised before it may touch
 * innerHTML. This module never builds HTML: parseMarkdown() returns plain
 * objects, and renderMarkdown() turns them into elements with createElement
 * and into text with createTextNode. Raw HTML in a reply is shown as the text
 * it is, and there is no code path that could make it markup.
 *
 * WHAT IT READS
 *   blocks : headings, paragraphs, fenced code, bullet and numbered lists
 *            (nested), block quotes, rules, pipe tables
 *   inline : **bold**, *italic*, ~~struck~~, `code`, [text](url), bare URLs
 *
 * WHERE IT DIFFERS FROM COMMONMARK, ON PURPOSE
 *   * A line break inside a paragraph is kept as a line break. A reply is
 *     written line by line, and the raw view shows it that way.
 *   * Emphasis never opens or closes inside a Latin word or a number, with
 *     `*` as with `_`. A reply about a fault tree is full of `root_0_0` and
 *     `0.5*0.5*0.28`; neither may lose characters to italics. Japanese is
 *     written without spaces, so only ASCII letters and digits count as a
 *     word here: `これは**重要**です` is bold.
 *   * A link is only made for http, https and mailto. Anything else stays
 *     text.
 *
 * CONTRACT
 *   parseMarkdown(text)       -> [block, ...]      (pure, no DOM)
 *   renderMarkdown(text, doc) -> DocumentFragment
 */

/** Past this size a reply is shown as plain paragraphs: no parsing cost. */
const MAX_CHARS = 200000;
/** Lists in lists, quotes in quotes, bold in italics: no deeper than this. */
const MAX_DEPTH = 8;

const FENCE = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)[^`]*$/;
const HEADING = /^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;
const RULE = /^ {0,3}([-*_])(?:\s*\1){2,}\s*$/;
const QUOTE = /^ {0,3}>\s?/;
const ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
const TABLE_RULE = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/;
const SAFE_URL = /^(?:https?:\/\/|mailto:)[^\s<>"']+$/i;
const BARE_URL = /^https?:\/\/[^\s<>"'`]+/i;
const WORD = /[A-Za-z0-9]/;
const ESCAPABLE = '\\`*_{}[]()#+-.!|~>';

/* --------------------------------------------------------------- inline ---- */

function isWord(ch) {
  return ch !== undefined && ch !== '' && WORD.test(ch);
}

function isSpace(ch) {
  return ch === undefined || ch === '' || /\s/.test(ch);
}

/**
 * The index of the delimiter that closes one opened at `from - mark.length`,
 * or -1. A closer follows a non-space and is not followed by a word character.
 */
function findCloser(text, mark, from) {
  let at = from;
  while (at < text.length) {
    const hit = text.indexOf(mark, at);
    if (hit === -1) return -1;
    if (text[hit - 1] === '\\') {
      at = hit + 1;
      continue;
    }
    // A `*` must not match part of a `**`, nor a `**` part of a `***`.
    const ch = mark[0];
    if (text[hit + mark.length] === ch || text[hit - 1] === ch) {
      at = hit + 1;
      while (text[at] === ch) at += 1;
      continue;
    }
    if (hit > from && !isSpace(text[hit - 1]) && !isWord(text[hit + mark.length])) return hit;
    at = hit + 1;
  }
  return -1;
}

/** A bare URL does not end in the full stop of its sentence. */
function trimUrl(url) {
  let end = url.length;
  while (end > 0 && '.,;:!?'.includes(url[end - 1])) end -= 1;
  if (url[end - 1] === ')' && !url.slice(0, end).includes('(')) end -= 1;
  return url.slice(0, end);
}

export function parseInline(text, depth = 0) {
  const out = [];
  // Delimiters known to have no closer in the rest of the text. Whether one
  // closes does not depend on where it was opened, so one failed search
  // settles every later one: a line of 30,000 stray `*` stays linear.
  const dead = new Set();
  let plain = '';
  const flush = () => {
    if (plain) out.push({ type: 'text', text: plain });
    plain = '';
  };
  let i = 0;
  while (i < text.length) {
    const ch = text[i];

    if (ch === '\\' && i + 1 < text.length && ESCAPABLE.includes(text[i + 1])) {
      plain += text[i + 1];
      i += 2;
      continue;
    }

    if (ch === '\n') {
      flush();
      out.push({ type: 'br' });
      i += 1;
      continue;
    }

    if (ch === '`') {
      let run = 1;
      while (text[i + run] === '`') run += 1;
      const mark = '`'.repeat(run);
      let close = dead.has(mark) ? -1 : text.indexOf(mark, i + run);
      while (close !== -1 && text[close + run] === '`') {
        // a longer run is not this closer: skip past it
        let skip = close;
        while (text[skip] === '`') skip += 1;
        close = text.indexOf(mark, skip);
      }
      if (close !== -1) {
        flush();
        out.push({ type: 'code', text: text.slice(i + run, close).replace(/\n/g, ' ').trim() });
        i = close + run;
        continue;
      }
      dead.add(mark);
      plain += mark;
      i += run;
      continue;
    }

    if (depth < MAX_DEPTH && (ch === '*' || ch === '_' || ch === '~')) {
      let run = 1;
      while (text[i + run] === ch) run += 1;
      // ***both*** is bold and italic; a longer run is not emphasis at all.
      const mark = ch.repeat(Math.min(run, 3));
      const single = mark.length === 1;
      const usable = run <= 3 && (ch === '~' ? mark.length === 2 : true);
      const opens = !isWord(text[i - 1]) && !isSpace(text[i + mark.length]);
      if (usable && opens && !dead.has(mark)) {
        const close = findCloser(text, mark, i + mark.length);
        if (close !== -1) {
          flush();
          const inner = parseInline(text.slice(i + mark.length, close), depth + 1);
          if (mark.length === 3) {
            out.push({ type: 'strong', children: [{ type: 'em', children: inner }] });
          } else {
            out.push({ type: ch === '~' ? 'del' : single ? 'em' : 'strong', children: inner });
          }
          i = close + mark.length;
          continue;
        }
        dead.add(mark);
      }
      plain += mark;
      i += mark.length;
      continue;
    }

    if (ch === '[' && depth < MAX_DEPTH && !dead.has('](')) {
      const mid = text.indexOf('](', i + 1);
      if (mid === -1) dead.add('](');
      const end = mid === -1 ? -1 : text.indexOf(')', mid + 2);
      const label = mid === -1 ? '' : text.slice(i + 1, mid);
      if (end !== -1 && label && !label.includes('\n') && !label.includes('[')) {
        const href = text.slice(mid + 2, end).trim().split(/\s+/)[0] || '';
        flush();
        if (SAFE_URL.test(href)) {
          out.push({ type: 'link', href, children: parseInline(label, depth + 1) });
        } else {
          // Not a link we will make: keep every character the model wrote.
          out.push({ type: 'text', text: text.slice(i, end + 1) });
        }
        i = end + 1;
        continue;
      }
    }

    if ((ch === 'h' || ch === 'H') && !isWord(text[i - 1])) {
      const hit = BARE_URL.exec(text.slice(i, i + 2048));
      if (hit) {
        const href = trimUrl(hit[0]);
        if (SAFE_URL.test(href)) {
          flush();
          out.push({ type: 'link', href, children: [{ type: 'text', text: href }] });
          i += href.length;
          continue;
        }
      }
    }

    plain += ch;
    i += 1;
  }
  flush();
  return out;
}

/* --------------------------------------------------------------- blocks ---- */

function indentOf(line) {
  let n = 0;
  for (const ch of line) {
    if (ch === ' ') n += 1;
    else if (ch === '\t') n += 4;
    else break;
  }
  return n;
}

/** Remove up to `n` columns of leading white space. */
function dedent(line, n) {
  let cut = 0;
  let cols = 0;
  while (cut < line.length && cols < n) {
    if (line[cut] === ' ') cols += 1;
    else if (line[cut] === '\t') cols += 4;
    else break;
    cut += 1;
  }
  return line.slice(cut);
}

function splitRow(line) {
  let row = line.trim();
  if (row.startsWith('|')) row = row.slice(1);
  if (row.endsWith('|') && !row.endsWith('\\|')) row = row.slice(0, -1);
  const cells = [];
  let cell = '';
  let inCode = false;
  for (let i = 0; i < row.length; i += 1) {
    const ch = row[i];
    if (ch === '\\' && row[i + 1] === '|') {
      cell += '|';
      i += 1;
    } else if (ch === '`') {
      inCode = !inCode;
      cell += ch;
    } else if (ch === '|' && !inCode) {
      cells.push(cell.trim());
      cell = '';
    } else {
      cell += ch;
    }
  }
  cells.push(cell.trim());
  return cells;
}

function isTableStart(lines, i) {
  if (i + 1 >= lines.length) return false;
  if (!lines[i].includes('|') || !lines[i + 1].includes('|')) return false;
  if (!TABLE_RULE.test(lines[i + 1])) return false;
  return splitRow(lines[i]).length === splitRow(lines[i + 1]).length;
}

function itemMatch(line) {
  const m = ITEM.exec(line);
  if (!m) return null;
  const ordered = /\d/.test(m[2][0]);
  return {
    indent: indentOf(m[1]),
    ordered,
    start: ordered ? parseInt(m[2], 10) : null,
    // where the item's own text starts: what a continuation line is cut to
    content: indentOf(m[1]) + m[2].length + 1,
    text: m[3],
  };
}

/** Does this line start a block that may cut a paragraph short? */
function startsBlock(lines, i) {
  const line = lines[i];
  if (FENCE.test(line) || HEADING.test(line) || RULE.test(line) || QUOTE.test(line)) return true;
  if (isTableStart(lines, i)) return true;
  const item = itemMatch(line);
  // "1986. A year" must not turn a sentence into a list: only 1. may interrupt.
  return Boolean(item && (!item.ordered || item.start === 1));
}

function parseBlocks(lines, depth) {
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (depth >= MAX_DEPTH) {
      blocks.push({ type: 'paragraph', inline: [{ type: 'text', text: lines.slice(i).join('\n') }] });
      break;
    }

    const fence = FENCE.exec(line);
    if (fence) {
      const mark = fence[1];
      const body = [];
      i += 1;
      while (i < lines.length) {
        const close = /^ {0,3}(`{3,}|~{3,})\s*$/.exec(lines[i]);
        if (close && close[1][0] === mark[0] && close[1].length >= mark.length) break;
        body.push(lines[i]);
        i += 1;
      }
      i += 1; // the closing fence, or the end of the reply
      blocks.push({ type: 'code', lang: fence[2] || '', text: body.join('\n') });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, inline: parseInline(heading[2]) });
      i += 1;
      continue;
    }

    if (RULE.test(line)) {
      blocks.push({ type: 'rule' });
      i += 1;
      continue;
    }

    if (QUOTE.test(line)) {
      const inner = [];
      while (i < lines.length && QUOTE.test(lines[i])) {
        inner.push(lines[i].replace(QUOTE, ''));
        i += 1;
      }
      blocks.push({ type: 'quote', blocks: parseBlocks(inner, depth + 1) });
      continue;
    }

    if (isTableStart(lines, i)) {
      const head = splitRow(lines[i]);
      const align = splitRow(lines[i + 1]).map((cell) => {
        const left = cell.startsWith(':');
        const right = cell.endsWith(':');
        return left && right ? 'center' : right ? 'right' : left ? 'left' : '';
      });
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        const cells = splitRow(lines[i]).slice(0, head.length);
        while (cells.length < head.length) cells.push('');
        rows.push(cells.map((cell) => parseInline(cell)));
        i += 1;
      }
      blocks.push({ type: 'table', head: head.map((cell) => parseInline(cell)), align, rows });
      continue;
    }

    const first = itemMatch(line);
    if (first) {
      const list = { type: 'list', ordered: first.ordered, start: first.start, items: [] };
      while (i < lines.length) {
        const item = itemMatch(lines[i]);
        if (!item || item.ordered !== list.ordered || item.indent > first.indent + 1 || item.indent < first.indent) {
          break;
        }
        const own = [item.text];
        i += 1;
        while (i < lines.length) {
          const next = lines[i];
          if (!next.trim()) {
            // A blank line stays in the item only if indented text follows it.
            let ahead = i + 1;
            while (ahead < lines.length && !lines[ahead].trim()) ahead += 1;
            if (ahead < lines.length && indentOf(lines[ahead]) > first.indent + 1) {
              own.push('');
              i += 1;
              continue;
            }
            break;
          }
          if (indentOf(next) <= first.indent + 1) break;
          own.push(dedent(next, item.content));
          i += 1;
        }
        list.items.push(parseBlocks(own, depth + 1));
        // blank lines between two items of one list
        let ahead = i;
        while (ahead < lines.length && !lines[ahead].trim()) ahead += 1;
        const more = ahead < lines.length ? itemMatch(lines[ahead]) : null;
        if (more && more.ordered === list.ordered && more.indent >= first.indent && more.indent <= first.indent + 1) {
          i = ahead;
        } else {
          break;
        }
      }
      blocks.push(list);
      continue;
    }

    const para = [line.trim()];
    i += 1;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) {
      para.push(lines[i].trim());
      i += 1;
    }
    blocks.push({ type: 'paragraph', inline: parseInline(para.join('\n')) });
  }
  return blocks;
}

export function parseMarkdown(text) {
  const source = String(text === null || text === undefined ? '' : text).replace(/\r\n?/g, '\n');
  if (source.length > MAX_CHARS) {
    return source
      .split(/\n{2,}/)
      .filter((part) => part.trim())
      .map((part) => ({ type: 'paragraph', inline: [{ type: 'text', text: part }] }));
  }
  return parseBlocks(source.split('\n'), 0);
}

/* --------------------------------------------------------------- render ---- */

function inlineInto(parent, nodes, doc) {
  for (const node of nodes) {
    if (node.type === 'text') {
      parent.appendChild(doc.createTextNode(node.text));
    } else if (node.type === 'br') {
      parent.appendChild(doc.createElement('br'));
    } else if (node.type === 'code') {
      const code = doc.createElement('code');
      code.textContent = node.text;
      parent.appendChild(code);
    } else if (node.type === 'link') {
      const a = doc.createElement('a');
      // parseInline only lets http, https and mailto through; checked again
      // here so that no other caller of this function can make a script URL.
      if (SAFE_URL.test(node.href)) a.setAttribute('href', node.href);
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
      inlineInto(a, node.children, doc);
      parent.appendChild(a);
    } else {
      const tag = node.type === 'strong' ? 'strong' : node.type === 'del' ? 'del' : 'em';
      const span = doc.createElement(tag);
      inlineInto(span, node.children, doc);
      parent.appendChild(span);
    }
  }
}

function blocksInto(parent, blocks, doc) {
  for (const block of blocks) {
    if (block.type === 'paragraph') {
      const p = doc.createElement('p');
      inlineInto(p, block.inline, doc);
      parent.appendChild(p);
    } else if (block.type === 'heading') {
      const h = doc.createElement('h' + block.level);
      inlineInto(h, block.inline, doc);
      parent.appendChild(h);
    } else if (block.type === 'code') {
      const pre = doc.createElement('pre');
      const code = doc.createElement('code');
      code.textContent = block.text;
      pre.appendChild(code);
      parent.appendChild(pre);
    } else if (block.type === 'rule') {
      parent.appendChild(doc.createElement('hr'));
    } else if (block.type === 'quote') {
      const quote = doc.createElement('blockquote');
      blocksInto(quote, block.blocks, doc);
      parent.appendChild(quote);
    } else if (block.type === 'list') {
      const list = doc.createElement(block.ordered ? 'ol' : 'ul');
      if (block.ordered && Number.isFinite(block.start) && block.start !== 1) {
        list.setAttribute('start', String(block.start));
      }
      for (const item of block.items) {
        const li = doc.createElement('li');
        // An item that is one line reads as a line, not as a paragraph.
        if (item.length && item[0].type === 'paragraph') {
          inlineInto(li, item[0].inline, doc);
          blocksInto(li, item.slice(1), doc);
        } else {
          blocksInto(li, item, doc);
        }
        list.appendChild(li);
      }
      parent.appendChild(list);
    } else if (block.type === 'table') {
      const wrap = doc.createElement('div');
      wrap.className = 'md-table';
      const table = doc.createElement('table');
      const cellInto = (row, tag, inline, column) => {
        const cell = doc.createElement(tag);
        if (block.align[column]) cell.style.textAlign = block.align[column];
        inlineInto(cell, inline, doc);
        row.appendChild(cell);
      };
      const thead = doc.createElement('thead');
      const headRow = doc.createElement('tr');
      block.head.forEach((inline, column) => cellInto(headRow, 'th', inline, column));
      thead.appendChild(headRow);
      table.appendChild(thead);
      const tbody = doc.createElement('tbody');
      for (const cells of block.rows) {
        const tr = doc.createElement('tr');
        cells.forEach((inline, column) => cellInto(tr, 'td', inline, column));
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      wrap.appendChild(table);
      parent.appendChild(wrap);
    }
  }
}

export function renderMarkdown(text, doc = document) {
  const fragment = doc.createDocumentFragment();
  blocksInto(fragment, parseMarkdown(text), doc);
  return fragment;
}

export default renderMarkdown;
