# Golden outputs from FTA Editor 1.8.1 (FN-28)

CLI results for every file of `fta_web/examples/*.json` and
`fta_web/tests/b2b/*.json` (except `expected.json`), made from the 1.8.1 release
commit `c6d09f5b0d5363fc037f63d3ec7cf1c91186a798`.

## Files

- `examples__<name>.json`, `b2b__<name>.json`: one per corpus file,
  `{"file": <repo-relative path>, "commands": {<command>: {"exitCode": n, "stdout": <parsed JSON, or text>}}}`
  for the commands `quantify`, `cutsets`, `importance`, `validate` (each with `--json`) and
  `mc --json --n 2000 --seed 1 --time-limit 3600`. Refusals (for example `cutsets` on an
  event-tree file) are recorded with their exit code and output like any other result.
- `manifest.json`: the release commit, the command lines, the SHA-256 of every input file,
  the per-file larger limits (two files, see below), the exit code of every command.
- `make_goldens.py`: the generator (option `--resume` reuses goldens already written, for an interrupted run). `cli_with_budgets.py`: the driver for the two files with larger limits.

## Regenerate

Regeneration is rarely needed: the goldens describe 1.8.1 and must not follow later
behaviour. To rebuild them, check out the release commit in a separate worktree and give
the generator its path (it refuses any other commit):

    git worktree add --detach <dir> c6d09f5b0d5363fc037f63d3ec7cf1c91186a798
    cd <dir> && uv sync --frozen --extra all --extra test
    uv run --frozen python fta_web/tests/golden_1_8_1/make_goldens.py <dir>

Every command is run twice and the runs must agree; the generator fails if a result is cut
short by time or holds an absolute path.

## How a test compares

For each golden file and each command, run the same command line (a repo-relative corpus
path, the repo root as working directory, `fta_web/run.py` as the entry point) and check:

1. the exit code equals the stored `exitCode`;
2. the parsed `stdout` JSON (or the text, when the golden holds text) equals the stored
   `stdout`, after removing the key `elapsedMs` at any depth from the fresh output (the
   stored goldens already have it removed); floats within relative 1e-13, everything
   else exact, and 0 against a nonzero float fails;
3. no time truncation on either side: no `truncatedByTime` true and no `"time"` in any
   `truncatedBy`.

The command line of every file and command is in `manifest.json` (`files.<path>.commands`).
Two files, `fta_web/tests/b2b/R00_random_legacy_400.json` and `R03_random_2000.json`, need about
9 s for their cut sets, so the fixed 2 s internal budgets of `quantify` and `validate` would cut
them short by time. Their `quantify` and `validate` run through `cli_with_budgets.py`, which raises
those two budgets (to 300 s) and otherwise calls the same CLI; the manifest lists them under
`largerLimits`, and a test must use the command line the manifest gives. In `make_goldens.py`,
`entry_for` and `command_lines` build these command lines and may be imported.

Compare parsed values, not text. Files without CCF groups must give these results, floats
within relative 1e-13 (the last bits of `math.expm1` differ between interpreters and platforms).
