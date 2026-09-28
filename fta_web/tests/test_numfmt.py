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
    (1234, 3, "1234"),
    (12345, 3, "1.23e+4"),
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


def test_out_of_range_sig_figs_are_clamped_in_format():
    assert format_prob(0.123456, 99) == "0.123456"
    assert format_prob(0.123456, 0) == "0.1"
