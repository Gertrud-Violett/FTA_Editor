"""The AI panel's MD switch: replies as formatted Markdown, or as raw text.

``static/js/markdown.js`` is run in node where node is installed. Its parser
is pure, so no DOM is needed to check what it reads; the renderer is checked
against a ten-line stand-in for ``document`` that records what it is asked to
build. The rest reads the sources: a model's reply is untrusted input, and the
rule that it never reaches ``innerHTML`` is a property of the text of the file.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "fta_web" / "static" / "js"
MARKDOWN = STATIC / "markdown.js"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

# Flattens the parser's objects into a string a test can read at a glance.
_FLAT = """
const flat = (nodes) => nodes.map((n) =>
  n.type === 'text' ? n.text
  : n.type === 'br' ? '\\n'
  : n.type === 'code' ? '`' + n.text + '`'
  : '<' + n.type + (n.href ? ' ' + n.href : '') + '>' + flat(n.children) + '</' + n.type + '>').join('');
const shape = (blocks) => blocks.map((b) =>
  b.type === 'list' ? { type: b.ordered ? 'ol' : 'ul', start: b.start, items: b.items.map(shape) }
  : b.type === 'quote' ? { type: 'quote', blocks: shape(b.blocks) }
  : b.type === 'table' ? { type: 'table', head: b.head.map(flat), align: b.align, rows: b.rows.map((r) => r.map(flat)) }
  : b.type === 'code' ? { type: 'code', lang: b.lang, text: b.text }
  : b.type === 'rule' ? { type: 'rule' }
  : b.type === 'heading' ? { type: 'h' + b.level, text: flat(b.inline) }
  : { type: 'p', text: flat(b.inline) });
"""


def _node(body: str, payload):
    """Run ``body`` as a module with markdown.js imported and ``input`` set."""
    script = (
        "import { parseInline, parseMarkdown, renderMarkdown } from %s;\n" % json.dumps(MARKDOWN.as_uri())
        + _FLAT
        + "const input = %s;\n" % json.dumps(payload)
        + body
    )
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True,
                         text=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(out)


def _inline(texts):
    return _node("console.log(JSON.stringify(input.map((t) => flat(parseInline(t)))));", texts)


def _blocks(text):
    return _node("console.log(JSON.stringify(shape(parseMarkdown(input))));", text)


# ---- inline ---------------------------------------------------------------------------

@needs_node
def test_emphasis_code_and_strike():
    assert _inline([
        "**bold** and *it* and _it2_ and ~~gone~~",
        "***both***",
        "**a *b* c**",
        "`c*o*de` and ``a ` b``",
    ]) == [
        "<strong>bold</strong> and <em>it</em> and <em>it2</em> and <del>gone</del>",
        "<strong><em>both</em></strong>",
        "<strong>a <em>b</em> c</strong>",
        "`c*o*de` and `a ` b`",
    ]


@needs_node
def test_ids_and_formulas_keep_every_character():
    """A reply about a fault tree is full of these; none may turn into italics."""
    texts = [
        "P = 0.5*0.5*0.28 and root_0_0 with snake_case_name",
        "2 * 3 * 4",
        "a ** b ** c",
        "**unclosed and *also unclosed",
        "node_a and node_b",
        "1e-7 ~ 1e-6",
    ]
    assert _inline(texts) == texts


@needs_node
def test_japanese_emphasis_needs_no_spaces():
    assert _inline(["これは**重要**な指摘です", "値は*0.0684*です"]) == [
        "これは<strong>重要</strong>な指摘です",
        "値は<em>0.0684</em>です",
    ]


@needs_node
def test_backslash_escapes_a_delimiter():
    assert _inline(["\\*not em\\* and \\`not code\\`"]) == ["*not em* and `not code`"]


@needs_node
def test_links_are_made_for_http_https_and_mailto_only():
    assert _inline([
        "[ok](https://a.example/c) and [mail](mailto:a@b.example)",
        "see https://e.example/y(1). End",
        "[x](javascript:alert(1)) [y](data:text/html,x) [z](vbscript:x) [f](file:///c:/x)",
        "[x]( JaVaScRiPt:alert(1) )",
    ]) == [
        "<link https://a.example/c>ok</link> and <link mailto:a@b.example>mail</link>",
        "see <link https://e.example/y(1)>https://e.example/y(1)</link>. End",
        "[x](javascript:alert(1)) [y](data:text/html,x) [z](vbscript:x) [f](file:///c:/x)",
        "[x]( JaVaScRiPt:alert(1) )",
    ]


@needs_node
def test_html_in_a_reply_is_text():
    texts = ["<img src=x onerror=alert(1)> <script>alert(1)</script> <b>bold</b>"]
    assert _inline(texts) == texts


# ---- blocks ---------------------------------------------------------------------------

@needs_node
def test_blocks_of_a_typical_reply():
    text = "\n".join([
        "# Title",
        "Intro line",
        "second line:",
        "- one",
        "- two",
        "  - nested **b**",
        "",
        "  still in two",
        "- three",
        "3. a",
        "4. b",
        "",
        "> quote",
        "> - q1",
        "",
        "| Cut set | P |",
        "|:--|--:|",
        "| A `x|y` | 0.1 |",
        "| B |",
        "",
        "```json",
        '{"a": "<b>"}',
        "```",
        "---",
        "In 1986. A year",
        "3. not a list",
    ])
    assert _blocks(text) == [
        {"type": "h1", "text": "Title"},
        {"type": "p", "text": "Intro line\nsecond line:"},
        {"type": "ul", "start": None, "items": [
            [{"type": "p", "text": "one"}],
            [{"type": "p", "text": "two"},
             {"type": "ul", "start": None, "items": [[{"type": "p", "text": "nested <strong>b</strong>"}]]},
             {"type": "p", "text": "still in two"}],
            [{"type": "p", "text": "three"}],
        ]},
        {"type": "ol", "start": 3, "items": [[{"type": "p", "text": "a"}], [{"type": "p", "text": "b"}]]},
        {"type": "quote", "blocks": [
            {"type": "p", "text": "quote"},
            {"type": "ul", "start": None, "items": [[{"type": "p", "text": "q1"}]]},
        ]},
        {"type": "table", "head": ["Cut set", "P"], "align": ["left", "right"],
         "rows": [["A `x|y`", "0.1"], ["B", ""]]},
        {"type": "code", "lang": "json", "text": '{"a": "<b>"}'},
        {"type": "rule"},
        {"type": "p", "text": "In 1986. A year\n3. not a list"},
    ]


@needs_node
def test_an_unclosed_fence_and_crlf_lose_nothing():
    assert _blocks("before\r\n~~~\r\n**kept as typed**\r\nlast") == [
        {"type": "p", "text": "before"},
        {"type": "code", "lang": "", "text": "**kept as typed**\nlast"},
    ]


@needs_node
def test_empty_and_non_string_input():
    assert _node("console.log(JSON.stringify(input.map((t) => shape(parseMarkdown(t)))));",
                 ["", "   \n\n", None, 12]) == [[], [], [], [{"type": "p", "text": "12"}]]


@needs_node
def test_hostile_input_is_parsed_in_linear_time():
    """30,000 stray delimiters once took 8 s; the page must not hang on a reply."""
    took = _node(
        "const text = '*a '.repeat(30000) + '\\n' + '['.repeat(20000) + '\\n' + '`'.repeat(999) + ' x'"
        " + '\\n' + '_b '.repeat(30000) + '\\n' + '> '.repeat(5000) + 'deep' + '\\n' + '~~c '.repeat(20000);\n"
        "const t0 = Date.now(); parseMarkdown(text); console.log(Date.now() - t0);", None)
    assert took < 2000, "parseMarkdown took %d ms on hostile input" % took


# ---- renderer -------------------------------------------------------------------------

_FAKE_DOM = """
const made = [];
const node = (tag) => ({ tag, attrs: {}, style: {}, children: [], className: '',
  set textContent(v) { this.children = [{ text: String(v) }]; },
  setAttribute(k, v) { this.attrs[k] = String(v); },
  appendChild(c) { this.children.push(c); return c; } });
const doc = {
  createElement: (tag) => { made.push(tag); return node(tag); },
  createTextNode: (text) => ({ text: String(text) }),
  createDocumentFragment: () => node('#fragment'),
};
const walk = (n, out) => { if (n.tag) { out.push(n); n.children.forEach((c) => walk(c, out)); } return out; };
"""


@needs_node
def test_the_renderer_builds_only_known_elements_and_safe_links():
    text = "\n".join([
        "# H", "p **b** *i* ~~d~~ `c` [l](https://a.example/) [bad](javascript:alert(1))",
        "<img src=x onerror=alert(1)><script>alert(1)</script>",
        "- a", "1. b", "> q", "| t |", "|---|", "| <svg onload=alert(1)> |", "```", "<iframe>", "```", "---",
    ])
    result = _node(
        _FAKE_DOM
        + "const all = walk(renderMarkdown(input, doc), []);\n"
        "console.log(JSON.stringify({ tags: [...new Set(made)].sort(),\n"
        "  links: all.filter((n) => n.tag === 'a').map((n) => n.attrs),\n"
        "  attrs: [...new Set(all.flatMap((n) => Object.keys(n.attrs)))].sort() }));", text)
    allowed = {"a", "blockquote", "br", "code", "del", "div", "em", "h1", "h2", "h3", "h4", "h5", "h6",
               "hr", "li", "ol", "p", "pre", "strong", "table", "tbody", "td", "th", "thead", "tr", "ul"}
    assert set(result["tags"]) <= allowed
    assert not {"img", "script", "svg", "iframe"} & set(result["tags"])
    assert result["links"] == [
        {"href": "https://a.example/", "target": "_blank", "rel": "noopener noreferrer"}]
    assert set(result["attrs"]) <= {"href", "target", "rel", "start"}


# ---- sources --------------------------------------------------------------------------

def test_markdown_js_never_builds_html():
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", MARKDOWN.read_text(encoding="utf-8"), flags=re.S)
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "DOMParser",
                 "createContextualFragment", "eval(", "Function("):
        assert sink not in code, "markdown.js uses %s" % sink


def test_only_the_models_replies_are_drawn_as_markdown():
    chat = (STATIC / "chat.js").read_text(encoding="utf-8")
    assert "import { renderMarkdown } from './markdown.js';" in chat
    # The two places a model's reply enters the log, and nothing else.
    assert chat.count("{ reply: true }") == 2
    assert "addMessage('user', text);" in chat
    # A rendering failure falls back to the raw text, and raw mode is textContent.
    fill = re.search(r"  function fillReply\(.*?\n  \}\n", chat, re.S).group(0)
    assert "renderMarkdown(text, document)" in fill and "catch" in fill
    assert fill.rstrip().endswith("body.textContent = text;\n  }".rstrip())
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", chat, flags=re.S)
    assert "innerHTML" not in code


def test_the_switch_is_a_remembered_toggle_button():
    chat = (STATIC / "chat.js").read_text(encoding="utf-8")
    assert "const MARKDOWN_PREF = 'fta.aiMarkdown';" in chat
    assert "getItem(MARKDOWN_PREF) !== '0'" in chat, "the switch is on unless it was switched off"
    assert "markdownBtn.setAttribute('aria-pressed', markdownOn ? 'true' : 'false');" in chat
    main = (STATIC / "main.js").read_text(encoding="utf-8")
    for key in ("ai.chat.markdown", "ai.chat.markdownLabel", "ai.chat.markdownOnTitle",
                "ai.chat.markdownOffTitle"):
        assert main.count("'%s':" % key) == 2, "%s must be in the English and the Japanese table" % key


def test_a_replys_lists_get_their_markers_back():
    """`.panel__body ul, ol` strips every list in a panel, the chat's included."""
    css = (REPO / "fta_web" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert ".panel__body .chat-msg__body--md ul { list-style: disc; }" in css
    assert ".panel__body .chat-msg__body--md ol { list-style: decimal; }" in css
    assert ".chat-msg__body--md { white-space: normal; }" in css
