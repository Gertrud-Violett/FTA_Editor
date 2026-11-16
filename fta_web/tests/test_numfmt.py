"""Tests for fta_web/numfmt.py -- the shared probability formatter."""
import pytest

from fta_web.numfmt import clamp_sig_figs, format_prob


@pytest.mark.parametrize("value, sf, expected", [
    (1e-7, 3, "1.00e-7"),
    (1.234e-7, 3, "1.23e-7"),
    (0.5, 3, "0.500"),
    (0.123456, 3, "0.123"),
    (0.0123456, 3, "0.0123"),
    (0.001, 3, "0.00100"),
    (0.00099996, 3, "0.00100"),  # rounds up into fixed form
    (0.000999, 3, "9.99e-4"),
    (1, 3, "1.00"),
    # More integer digits than sig figs: rounded, written plain (as numfmt.js).
    (1234, 3, "1230"),
    (1234, 2, "1200"),
    (12.3456, 1, "10"),
    (9238.778557185406, 3, "9240"),
    (100.99999999999899, 2, "100"),
    # Exponent form without the redundant "+" (as numfmt.js): 1.23e4.
    (12345, 3, "1.23e4"),
    (25000, 1, "3e4"),
    (1e4, 3, "1.00e4"),
    # The form follows the *rounded* magnitude (USER_GUIDE, "Significant figures").
    (9999.7, 3, "1.00e4"),
    (999.96, 3, "1000"),
    # Exact binary ties round half up, as JavaScript's toPrecision does.
    (0.25, 1, "0.3"),
    (1.25, 2, "1.3"),
    (3.25, 2, "3.3"),
    (0.5625, 3, "0.563"),
    (12345, 4, "1.235e4"),
    (-0.25, 1, "-0.3"),
    # Not a tie in binary: 0.35 is 0.34999999999999997779... -> 0.3.
    (0.35, 1, "0.3"),
    (0.5, 1, "0.5"),
    (1e-7, 1, "1e-7"),
    (1e-7, 6, "1.00000e-7"),
    (-2e-5, 2, "-2.0e-5"),
    (0, 3, "0"),
    (0.0, 3, "0"),
])
def test_format_prob(value, sf, expected):
    assert format_prob(value, sf) == expected


@pytest.mark.parametrize("value", [None, float("nan"), "abc", True, [1]])
def test_missing_values_are_a_dash(value):
    assert format_prob(value) == "—"


def test_numeric_strings_are_accepted():
    assert format_prob("1e-7") == "1.00e-7"


def test_default_is_three_significant_figures():
    assert format_prob(1e-7) == "1.00e-7"


@pytest.mark.parametrize("value, expected", [
    (None, 3), ("x", 3), (0, 1), (-4, 1), (1, 1), (4, 4), ("5", 5), (6, 6), (9, 6), (2.7, 2), (True, 3),
])
def test_clamp_sig_figs(value, expected):
    assert clamp_sig_figs(value) == expected


def test_matches_numfmt_js_exactly():
    """Back-to-back with the browser's formatter (static/js/numfmt.js, run by
    node): identical text for every value and every sig-fig setting,
    including the plain/exponent boundary, which both decide from the
    *rounded* magnitude (0.00099996 at 3 s.f. is "0.00100", 9999.7 is
    "1.00e4"; USER_GUIDE "Significant figures"). 1.7.0's numfmt.js decided
    from the raw value, so the GUI and the DOCX/CLI disagreed there."""
    import json
    import math
    import random
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    rng = random.Random(5)
    values = [1e-7, 0.5, 0.00099996, 1234.0, 12345.0, 9999.7, 999.96, 0.25, 1.25, 0.5625,
              -2e-5, 9238.778557185406, 585.0746, 25000.0, 0.30000000000000004, 2.5e-12]
    values += [10 ** rng.uniform(-13, 5) for _ in range(400)]
    values += [round(rng.uniform(0, 1), rng.randint(1, 4)) for _ in range(200)]  # ties
    values += [float(n) for n in range(1, 200)] + [n + 0.5 for n in range(20)]
    sfs = [1, 2, 3, 4, 5, 6]
    module = (Path(__file__).resolve().parents[1] / "static" / "js" / "numfmt.js").as_uri()
    script = (
        "import(%s).then(m => {const vs = JSON.parse(process.argv[1]);"
        "const out = {}; vs.forEach((v, i) => { for (const sf of [1, 2, 3, 4, 5, 6])"
        " out[i + '@' + sf] = m.formatProb(v, sf); });"
        "process.stdout.write(JSON.stringify(out));});" % json.dumps(module))
    proc = subprocess.run([node, "--input-type=module", "-e", script, json.dumps(values)],
                          capture_output=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    js = json.loads(proc.stdout.decode("utf-8"))
    py = {"%d@%d" % (i, sf): format_prob(v, sf) for i, v in enumerate(values) for sf in sfs}

    bad = []
    for key, text in py.items():
        i, sf = (int(x) for x in key.split("@"))
        if text != js[key]:
            bad.append((values[i], sf, text, js[key]))
    assert not bad, bad[:10]
    assert all(math.isfinite(v) for v in values)


def test_out_of_range_sig_figs_are_clamped_in_format():
    assert format_prob(0.123456, 99) == "0.123456"
    assert format_prob(0.123456, 0) == "0.1"
