// Compare the GUI snapshots s_core records (headline, Details and diagram labels
// after every step: what the user saw) between two runs, e.g. the dev server and
// the packaged exe:
//   node compare_snaps.js out/dev/core_dev.json out/exe/core_exe.json
// Exit code 1 on any difference.
'use strict';
const fs = require('fs');
const [a, b] = process.argv.slice(2).map((f) => JSON.parse(fs.readFileSync(f, 'utf8')));
let diffs = 0;
let compared = 0;
const n = Math.max(a.snaps.length, b.snaps.length);
for (let i = 0; i < n; i += 1) {
  const x = a.snaps[i];
  const y = b.snaps[i];
  if (!x || !y) { console.log('DIFF snapshot count', i); diffs += 1; continue; }
  const flat = (s) => JSON.stringify({ label: s.label, sf: s.sf, headline: s.headline, details: s.details, diagram: s.diagram });
  compared += 1 + Object.keys(x.diagram || {}).length;
  if (flat(x) !== flat(y)) {
    diffs += 1;
    console.log('DIFF', x.label, '\n  A', flat(x).slice(0, 400), '\n  B', flat(y).slice(0, 400));
  }
}
console.log(`snapshots ${n}, values compared ~${compared}, diffs ${diffs}`);
process.exit(diffs ? 1 : 0);
