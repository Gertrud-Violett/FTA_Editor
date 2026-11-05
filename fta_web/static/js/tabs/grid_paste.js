/**
 * tabs/grid_paste.js -- the pure part of pasting into the Grid tab (F3, FN-47, FN-50).
 *
 * Three functions and no side effects: no DOM, no network, no storage, no number reading.
 * The Grid tab hands in the readers of its columns (the existing field parsers), so the
 * same text means the same number as in the field where it is typed (FN-46); this
 * module only decides which clipboard cell goes to which (row, column) and which cells
 * are refused before anything is sent.
 *
 *   parseClipboard(text) -> string[][]      Excel's tab-separated text with its quoting
 *   planPaste({...})     -> {requestRows, refused, clipRowCount}
 *   endSentence(text, language) -> text closed with a full stop (for joining a message into a sentence)
 *
 * A refusal made here is {clipRow, column, code, text?, n?}. The Grid tab writes the
 * wording from `code` when it draws the summary (so it follows the language).
 */

/** A paste holds at most this many clipboard rows (the server refuses more as well). */
export const MAX_PASTE_ROWS = 2000;

const isBlank = (text) => String(text).trim() === '';

/**
 * Clipboard text as rows of cells. Cells end at a tab; rows end at CRLF, LF or CR, and
 * exactly one final terminator is dropped (a trailing newline makes no empty row). A cell
 * that starts with a double quote is quoted: "" is a quote, tabs and line breaks inside
 * belong to the cell, the closing quote ends it, and an unterminated quote runs to the end.
 * A quote inside an unquoted cell is literal.
 */
export function parseClipboard(text) {
  const src = text === null || text === undefined ? '' : String(text);
  const rows = [];
  let row = [];
  let cell = '';
  let fresh = true; // nothing of the current row consumed yet
  let i = 0;
  const end = src.length;
  while (i < end) {
    const ch = src[i];
    fresh = false;
    if (ch === '"' && cell === '') {
      // a quoted cell: read to the closing quote
      i += 1;
      let closed = false;
      while (i < end) {
        if (src[i] === '"') {
          if (src[i + 1] === '"') {
            cell += '"';
            i += 2;
            continue;
          }
          i += 1;
          closed = true;
          break;
        }
        cell += src[i];
        i += 1;
      }
      if (!closed) break;
      // after the closing quote: anything up to the next tab or line break is literal
      while (i < end && src[i] !== '\t' && src[i] !== '\r' && src[i] !== '\n') {
        cell += src[i];
        i += 1;
      }
      continue;
    }
    if (ch === '\t') {
      row.push(cell);
      cell = '';
      i += 1;
      continue;
    }
    if (ch === '\r' || ch === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
      fresh = true;
      i += ch === '\r' && src[i + 1] === '\n' ? 2 : 1;
      continue;
    }
    cell += ch;
    i += 1;
  }
  if (!fresh) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

/**
 * Map the clipboard cells onto the grid and decide what is sent.
 *
 *   rows       parseClipboard() output
 *   anchorRow  index in `order` of the selected cell's row
 *   anchorCol  index in `columns` of the selected cell's column
 *   order      node ids in the order displayed (sorted and filtered)
 *   columns    the visible column keys, in table order
 *   rowFor     (nodeId) -> the row as shown, passed to the readers
 *   read       {columnKey: (text, row) -> {ok: true, value, ignore?} | {ok: false, code?}}
 *   numeric    column keys whose cell must not hold a tab or a line break
 *
 * Per clipboard row, in this order: a row of empty cells is skipped (and still uses its
 * displayed row); with no displayed row left it is refused (EXTRA_ROW); cells beyond the
 * last visible column are dropped and reported once (EXTRA_CELLS); an empty cell is left
 * out; every other cell is read by its column's reader, and one unreadable cell refuses
 * the whole row (one refusal per such cell, nothing of the row is sent).
 */
export function planPaste({ rows, anchorRow, anchorCol, order, columns, rowFor, read, numeric = [] }) {
  const requestRows = [];
  const refused = [];
  const numericColumns = new Set(numeric);
  rows.forEach((cells, index) => {
    const clipRow = index + 1;
    if (cells.every(isBlank)) return;
    const nodeId = order[anchorRow + index];
    if (nodeId === undefined) {
      refused.push({ clipRow, column: '', code: 'EXTRA_ROW' });
      return;
    }
    const room = Math.max(0, columns.length - anchorCol);
    const extra = cells.slice(room).filter((text) => !isBlank(text)).length;
    if (extra) refused.push({ clipRow, column: '', code: 'EXTRA_CELLS', n: extra });
    const row = rowFor(nodeId);
    const out = {};
    let bad = false;
    cells.slice(0, room).forEach((text, offset) => {
      if (isBlank(text)) return;
      const column = columns[anchorCol + offset];
      if (numericColumns.has(column) && /[\t\r\n]/.test(text)) {
        refused.push({ clipRow, column, code: 'CONTROL_CHAR', text });
        bad = true;
        return;
      }
      const reader = read[column];
      const result = reader ? reader(text, row) : { ok: true, value: text };
      if (!result.ok) {
        refused.push({ clipRow, column, code: result.code || 'INVALID_CELL', text });
        bad = true;
        return;
      }
      if (result.ignore) return;
      out[column] = result.value;
    });
    if (!bad && Object.keys(out).length) requestRows.push({ clipRow, nodeId, cells: out });
  });
  return { requestRows, refused, clipRowCount: rows.length };
}

/** A sentence ends with one of these (optionally followed by closing quotes or brackets). */
const SENTENCE_END = /[.!?。！？…‥][)\]}"'”’」』）】]*$/;

/**
 * `text` as the end of a sentence that is followed by another one: trimmed, and closed with
 * a full stop (`.` for English, `。` for Japanese) unless it already ends with one of . ! ? 。 ！ ？ …
 * An empty text stays empty. Used where a message from elsewhere (the server, the browser) is
 * joined into a catalog sentence, so that "{error} Nothing was applied." reads right either way.
 */
export function endSentence(text, language) {
  const out = String(text === null || text === undefined ? '' : text).trim();
  if (!out || SENTENCE_END.test(out)) return out;
  return out + (language === 'ja' ? '。' : '.');
}
