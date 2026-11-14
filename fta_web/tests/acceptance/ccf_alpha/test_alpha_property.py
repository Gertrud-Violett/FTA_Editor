"""F2A BRIEF criterion 3 (FN-41, FN-42): the consistency property of the alpha model.

For every member, the independent part and the CCF events that contain it add up to its
total probability::

    sum over k = 1..m of C(m-1, k-1) * Q_k  ==  Q_t        (relative 1e-12)

(a member is in C(m-1, k-1) of the C(m, k) subsets of size k). Checked for m = 2, 3, 4 and for
both testing schemes over at least 1,000 random alpha sets each, seeded (plain pytest, no
hypothesis: PLAN Q6). Q_t is drawn log-uniform in [1e-9, 1e-1]. Half of the sets sum to 1 (up
to rounding), a quarter sum to 1.0005 or 0.9995 (the normalised case of FN-43) and a few have
zero entries.

The Q_k are read from the public ``ccf.event_probabilities`` (independent part = Q_1, the q of
each subset event of size k = Q_k) and are also compared with the formulas written in
``_alpha_models.oracle_q`` (S1 Eq. 5.6 and 5.7).
"""
import math
import random

import pytest

import _alpha_models as M

SETS_PER_CASE = 1000
SEED = 20261028


def random_alpha(rng, m):
    """m non-negative numbers adding up to 1, or to 1.0005 / 0.9995 (the normalised case)."""
    raw = [rng.random() ** rng.choice((1, 2, 3)) for _ in range(m)]
    if rng.random() < 0.1:
        raw[rng.randrange(m)] = 0.0
    if sum(raw) == 0.0:
        raw[0] = 1.0
    total = sum(raw)
    alpha = [x / total for x in raw]
    pick = rng.random()
    if pick > 0.75:
        factor = 1.0005 if pick < 0.875 else 0.9995
        if max(alpha) * factor > 1.0:       # FN-43: every alpha_k is a number in [0, 1]
            factor = 0.9995
        alpha = [x * factor for x in alpha]
    assert all(0.0 <= x <= 1.0 for x in alpha), alpha
    return alpha


def random_qt(rng):
    return 10 ** rng.uniform(-9, -1)


@pytest.mark.parametrize("testing", ["staggered", "nonStaggered"])
@pytest.mark.parametrize("m", [2, 3, 4])
def test_sum_of_the_binomial_weighted_probabilities_is_q_t(m, testing):
    from fta_web import ccf

    rng = random.Random(SEED + 10 * m + (0 if testing == "staggered" else 1))
    checked = 0
    for _ in range(SETS_PER_CASE):
        alpha = random_alpha(rng, m)
        qt = random_qt(rng)
        result = ccf.event_probabilities("alpha", {"alpha": alpha, "testing": testing}, [qt] * m)

        q1 = result.independent[0]
        assert len(result.independent) == m and all(q == q1 for q in result.independent)
        by_size = {}
        for idxs, q in result.events:
            by_size.setdefault(len(idxs), []).append(q)
        assert sorted(by_size) == list(range(2, m + 1))
        total = q1
        for k in range(2, m + 1):
            events = by_size[k]
            assert len(events) == math.comb(m, k)
            assert all(q == events[0] for q in events), (k, events)
            total += math.comb(m - 1, k - 1) * events[0]
        assert total == pytest.approx(qt, rel=1e-12, abs=0.0), (alpha, qt, testing)

        # and the individual Q_k are those of Eq. 5.6 / 5.7 (alpha divided by the sum)
        expected = M.oracle_q(m, alpha, testing, qt)
        assert q1 == pytest.approx(expected[0], rel=1e-12, abs=0.0)
        for k in range(2, m + 1):
            assert by_size[k][0] == pytest.approx(expected[k - 1], rel=1e-12, abs=0.0)
        checked += 1
    assert checked >= 1000      # PLAN Q6 / BRIEF criterion 3: at least 1,000 sets for this (m, scheme)


@pytest.mark.parametrize("testing", ["staggered", "nonStaggered"])
def test_every_member_of_the_compiled_tree_adds_up_to_q_t(testing):
    """The same property on the compiled structure: in an OR tree each member contributes its
    independent part and the events that contain it; the q values add up to Q_t."""
    rng = random.Random(SEED + 99)
    for m in (2, 3, 4):
        for _ in range(25):
            alpha = random_alpha(rng, m)
            qt = 10 ** rng.uniform(-6, -2)
            members = M.IDS[:m]
            tree = M.or_tree(members, q=qt)
            qs = M.event_q(tree, [M.agroup(members=members, alpha=alpha, testing=testing)])
            for position, member in enumerate(members):
                mine = qs[member] + sum(
                    q for idx in M.subsets(m) if position in idx
                    for q in [qs[M.subset_id("g1", members, idx)]])
                assert mine == pytest.approx(qt, rel=1e-12, abs=0.0), (m, member, alpha, testing)


@pytest.mark.parametrize("testing", ["staggered", "nonStaggered"])
def test_monte_carlo_keeps_alpha_fixed_and_splits_each_sampled_q_t(testing):
    """DESIGN 3.4 / BRIEF interfaces: alpha is not sampled (FN-24). Each trial draws one Q_t per
    member, and the per-trial CCF event q and independent part are Q_k = c_k * Q_t with the
    constants of Eq. 5.6 / 5.7 (``_alpha_models.oracle_q``), relative 1e-12, through the
    sampler hook ``uncertainty.run(..., ccf_trial_hook=...)`` of F2."""
    from fta_web import uncertainty

    quant = {"model": "fixed", "unc": {"dist": "lognormal", "median": 1e-3, "ef": 3}}
    members = ["A", "B", "D"]
    tree = M.top([M.gate("G1", "AND", [M.pump(i, quant=quant) for i in members],
                         name="Pumps fail")])
    group = M.agroup(members=members, alpha=M.ALPHA3, testing=testing)
    calls = []
    result = uncertainty.run(tree, M.analysis_of([group]), time_limit=3600, n=1200, seed=7,
                             ccf_trial_hook=calls.append)
    assert result["completed"] == 1200
    assert [len(c["qt"]) for c in calls] == [500, 500, 200]      # one group step per chunk
    constants = M.oracle_q(3, M.ALPHA3, testing, qt=1.0)          # c_k = Q_k / Q_t
    ids = {M.subset_id("g1", members, idx): idx for idx in M.subsets(3)}
    seen = set()
    for call in calls:
        assert call["groupId"] == "g1" and call["model"] == "alpha" and call["beta"] is None
        assert set(call["ccf"]) == set(ids) and set(call["independent"]) == set(members)
        for i, qt in enumerate(call["qt"]):
            seen.add(qt)
            for member in members:
                assert call["independent"][member][i] == pytest.approx(
                    constants[0] * qt, rel=1e-12, abs=0.0)
            for event_id, idx in ids.items():
                assert call["ccf"][event_id][i] == pytest.approx(
                    constants[len(idx) - 1] * qt, rel=1e-12, abs=0.0)
            # Q_t is recovered for a member: its independent part and the events that contain it
            mine = call["independent"]["A"][i] + sum(
                q[i] for event_id, q in call["ccf"].items() if 0 in ids[event_id])
            assert mine == pytest.approx(qt, rel=1e-12, abs=0.0)
    assert len(seen) > 1000   # Q_t is drawn afresh in every trial; alpha is the same in all
