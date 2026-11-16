"""F2 BRIEF criteria 11 and 12 (FN-23, FN-24): importance and Monte Carlo.

Criterion 11: FV, Birnbaum, RAW and RRW are computed on the expanded structure;
the CCF event has its own row; the member rows are the independent parts; no row
is a combined component. R1h values for ``ccf:g1`` (SPEC 7.4): Birnbaum
0.99999919 and RAW 9919.6588 and RRW 124.45669 (rounded to the digits shown),
FV 0.991965076374 compared at relative 1e-9 (DESIGN section 19: the SPEC prints
a value that is 9e-13 off the exact one).

Criterion 12: one draw per group per trial; the per-trial CCF q divided by the
member Q_t is beta within relative 1e-12 and the independent parts are equal
(through the sampler hook ``uncertainty.run(..., ccf_trial_hook=...)``); R11
(n = 200,000, one fixed seed, ``time_limit=3600``) has its mean within 3
standard errors of 1.2696e-4; the Monte Carlo result carries the note "β and α
are not sampled".
"""
import math

import pytest

import _ccf_models as M

R1_MCUB = 1.00809919e-4
R11_MEAN = 1.2696e-4
#: The ONE seed of the R11 test (fixed in T0 before any run; never changed to pass).
R11_SEED = 20261026
HOOK_SEED = 7
#: The ONE seed of the beta = 0 test (fixed in T0 before any run; never changed to pass).
BETA0_SEED = 20261028
SAMPLING_NOTE = "β and α are not sampled in Monte Carlo."


def analysis_of(groups):
    return {"ccfGroups": groups}


def importance_rows(tree, groups):
    from fta_web import cutsets, importance

    result = cutsets.compute(tree, analysis_of(groups), {"timeBudgetS": 120})
    return result, importance.compute(result)


# ---------------------------------------------------------------- criterion 11


def test_r1h_importance_of_the_ccf_event():
    result, rows = importance_rows(M.r1_tree(), [M.group()])
    by_id = {r["id"]: r for r in rows}
    row = by_id["ccf:g1"]
    assert row["fv"] == M.rel(0.991965076374, 1e-9)
    assert row["birnbaum"] == M.rel(0.99999919, 1e-9)
    assert abs(row["raw"] - 9919.6588) <= 0.5e-4  # half a unit of the last digit shown
    assert abs(row["rrw"] - 124.45669) <= 0.5e-5
    assert row["name"] == "CCF: Feed pumps"
    assert row["q"] == M.rel(1e-4, 1e-12)
    assert row["ccf"]["groupId"] == "g1" and row["ccf"]["role"] == "event"


def test_the_member_rows_are_the_independent_parts_and_there_is_no_combined_row():
    _, rows = importance_rows(M.r1_tree(), [M.group()])
    by_id = {r["id"]: r for r in rows}
    assert set(by_id) == {"A", "B", "ccf:g1"}  # nothing like "A + CCF"
    assert len(rows) == 3
    for member, name in (("A", "Pump A"), ("B", "Pump B")):
        row = by_id[member]
        assert row["name"] == name + " (independent part)"
        assert row["q"] == M.rel(9e-4, 1e-12)
        assert row["ccf"]["role"] == "independent" and row["ccf"]["groupId"] == "g1"
    assert not any(r["name"] in ("Pump A", "Pump B") for r in rows)


def test_importance_through_the_api_carries_the_ccf_event_and_the_block(api):
    api.open_doc(M.document(M.r1_tree(), [M.group()]))
    status, body = api.post("/api/analysis/importance", {})
    assert status == 200, body
    row = [r for r in body["events"] if r["id"] == "ccf:g1"][0]
    assert row["birnbaum"] == M.rel(0.99999919, 1e-9)
    assert row["fv"] == M.rel(0.991965076374, 1e-9)
    assert row["name"] == "CCF: Feed pumps" and row["ccf"]["groupId"] == "g1"
    assert body["topValue"] == M.rel(R1_MCUB, 1e-9)
    assert [g["id"] for g in body["ccf"]["applied"]] == ["g1"]
    assert body["events"][0]["id"] == "ccf:g1"  # sorted by FV, the CCF event first


def test_importance_of_a_document_without_groups_has_no_ccf_key(api):
    api.open_doc(M.document(M.r1_tree(), None))
    status, body = api.post("/api/analysis/importance", {})
    assert status == 200, body
    assert "ccf" not in body
    assert all("ccf" not in r for r in body["events"])


# ---------------------------------------------------------------- criterion 12


def run_mc(tree, groups, **kwargs):
    from fta_web import uncertainty

    return uncertainty.run(tree, analysis_of(groups), time_limit=3600, **kwargs)


def test_the_sampler_hook_shows_beta_times_the_shared_draw_and_equal_independent_parts():
    calls = []
    result = run_mc(M.r11_tree(), [M.group()], n=1200, seed=HOOK_SEED, ccf_trial_hook=calls.append)
    assert result["completed"] == 1200
    assert [len(c["qt"]) for c in calls] == [500, 500, 200]  # once per group per chunk
    qts = []
    for call in calls:
        assert call["groupId"] == "g1"
        assert call["beta"] == M.rel(0.1, 1e-12)
        assert set(call["independent"]) == {"A", "B"}
        count = len(call["qt"])
        assert len(call["ccf"]) == count
        assert len(call["independent"]["A"]) == len(call["independent"]["B"]) == count
        for i in range(count):
            qt = call["qt"][i]
            assert call["ccf"][i] / qt == M.rel(0.1, 1e-12)
            assert call["independent"]["A"][i] == M.rel(call["independent"]["B"][i], 1e-12)
            assert call["independent"]["A"][i] == M.rel(0.9 * qt, 1e-12)
        qts.extend(call["qt"])
    assert len(qts) == 1200
    assert len(set(qts)) > 1000  # Q_t is drawn afresh every trial (lognormal, EF 3)
    assert all(0.0 < q < 1.0 for q in qts)
    median = sorted(qts)[len(qts) // 2]
    assert median == M.rel(1e-3, 0.15)  # the members' median
    # Tie the hook to the result: the hook must show what the sampler really used. Rebuild each
    # trial's top event from the hook columns. R11 is the AND of A and B with the group, so the
    # cut sets are {ccf:g1} and {A, B} and the min-cut upper bound is
    # 1 - (1 - ccf)(1 - indA * indB). Their mean and std must be the result's.
    tops = []
    for call in calls:
        for ccf_q, ind_a, ind_b in zip(call["ccf"], call["independent"]["A"],
                                       call["independent"]["B"]):
            tops.append(1.0 - (1.0 - ccf_q) * (1.0 - ind_a * ind_b))
    assert len(tops) == result["completed"] == 1200
    rebuilt_mean = math.fsum(tops) / len(tops)
    # The product's std is the sample standard deviation (divisor completed - 1, uncertainty.py);
    # SPEC 7.4 names no other, so the same divisor is used here.
    rebuilt_std = math.sqrt(math.fsum((v - rebuilt_mean) ** 2 for v in tops) / (len(tops) - 1))
    assert rebuilt_mean == M.rel(result["mean"], 1e-9)
    assert rebuilt_std == M.rel(result["std"], 1e-9)
    assert result["std"] > 0


def test_the_hook_is_not_called_without_an_applied_group():
    calls = []
    run_mc(M.r11_tree(), [], n=600, seed=HOOK_SEED, ccf_trial_hook=calls.append)
    run_mc(M.r11_tree(), [M.group(beta="abc")], n=600, seed=HOOK_SEED, ccf_trial_hook=calls.append)
    assert calls == []


def test_the_result_names_the_sampled_group_and_says_beta_and_alpha_are_not_sampled():
    result = run_mc(M.r11_tree(), [M.group()], n=600, seed=HOOK_SEED)
    assert result["ccfSampling"] == {"groups": [{"id": "g1", "sampled": True}],
                                     "note": SAMPLING_NOTE}
    assert [g["id"] for g in result["ccf"]["applied"]] == ["g1"]
    assert result["method"] == "cutsets"  # the CCF event is a repeated event
    assert set(result["uncertainEvents"]) == {"A", "B"}  # the member ids stand for the group
    assert not any(i.startswith("ccf:") for i in result["certainEvents"])
    assert "MC_EVENT_NOT_SAMPLED" not in [w["code"] for w in result["warnings"]]
    assert "ccf:g1" in {r["id"] for r in result["repeatedEvents"]}


def test_no_applied_group_means_no_sampling_note():
    result = run_mc(M.r11_tree(), [M.group(beta="abc")], n=300, seed=HOOK_SEED)
    assert "ccfSampling" not in result
    assert [g["code"] for g in result["ccf"]["notApplied"]] == ["CCF_BAD_PARAMETER"]
    plain = run_mc(M.r11_tree(), [], n=300, seed=HOOK_SEED)
    assert "ccfSampling" not in plain and "ccf" not in plain


def test_a_group_without_uncertainty_is_a_constant_and_the_ccf_event_is_not_frozen_out():
    tree = M.gate("root", "AND", [M.pump("A"), M.pump("B")], name="Top event", type_="Root")
    result = run_mc(tree, [M.group()], n=500, seed=HOOK_SEED)
    assert result["method"] == "cutsets"
    assert result["pointEstimate"] == M.rel(R1_MCUB, 1e-9)
    assert result["mean"] == M.rel(R1_MCUB, 1e-9)  # the CCF set is in every sample
    assert result["std"] == pytest.approx(0.0, abs=1e-15)
    assert "MC_NO_UNCERTAINTY" in [w["code"] for w in result["warnings"]]


def test_the_uncertainty_endpoint_returns_the_note_and_the_ccf_block(api):
    api.open_doc(M.document(M.r11_tree(), [M.group()]))
    status, body = api.post("/api/analysis/uncertainty", {"n": 800, "seed": HOOK_SEED})
    assert status == 200, body
    assert body["ccfSampling"]["note"] == SAMPLING_NOTE
    assert body["ccfSampling"]["groups"] == [{"id": "g1", "sampled": True}]
    assert [g["id"] for g in body["ccf"]["applied"]] == ["g1"]


def test_the_same_seed_gives_the_same_run_with_a_group():
    a = run_mc(M.r11_tree(), [M.group()], n=700, seed=HOOK_SEED)
    b = run_mc(M.r11_tree(), [M.group()], n=700, seed=HOOK_SEED)
    assert [g["id"] for g in a["ccf"]["applied"]] == ["g1"]
    assert a["mean"] == b["mean"] and a["std"] == b["std"]


def test_with_beta_zero_the_members_share_one_draw_so_the_mean_is_e_q_squared():
    """Shared against independent member sampling, told apart without doubt.

    Group g1 with beta = 0 on R11 (AND of A and B, both lognormal median 1e-3, EF 3, so
    sigma = ln 3 / 1.645 = 0.66785). The CCF event has q = 0, so the top is 1 - (1 - 0)(1 -
    Q_A * Q_B) = Q_A * Q_B, and the group shares ONE draw Q per trial between its members:
    top = Q^2, mean E[Q^2] = m^2 exp(2 sigma^2) = 2.4401e-6. Independent member draws would
    give E[Q]^2 = (m exp(sigma^2 / 2))^2 = 1.5621e-6, 56 % lower. At n = 20,000 the standard
    error is about 3.8e-8, so the two means are 23 standard errors apart. An analyst's
    cross-check (not a SPEC oracle); one fixed seed, never changed to make it pass.
    """
    shared = 2.4401e-6  # E[Q^2]
    independent = 1.5621e-6  # E[Q]^2
    result = run_mc(M.r11_tree(), [M.group(beta=0.0)], n=20000, seed=BETA0_SEED)
    assert [g["id"] for g in result["ccf"]["applied"]] == ["g1"]  # beta 0 is a valid beta
    assert result["completed"] == 20000 and result["truncatedByTime"] is False
    standard_error = result["std"] / math.sqrt(result["completed"])
    assert standard_error > 0
    assert abs(result["mean"] - shared) <= 3 * standard_error, (result["mean"], standard_error)
    assert abs(result["mean"] - independent) > 3 * standard_error, (
        result["mean"], standard_error)


def test_r11_the_mean_of_the_top_event_is_within_three_standard_errors():
    """AND of two members, beta 0.1, lognormal median 1e-3, EF 3:
    E[top] = beta E[Q_t] + (1 - beta)^2 E[Q_t^2] = 1.2696e-4 (SPEC 7.4, R11).

    One fixed seed, 200,000 trials, a time limit that cannot cut the run.
    The test passes or fails for 3 standard errors of the run's own scatter; the
    seed is never changed to make it pass.
    """
    result = run_mc(M.r11_tree(), [M.group()], n=200000, seed=R11_SEED)
    assert result["completed"] == 200000 and result["truncatedByTime"] is False
    standard_error = result["std"] / math.sqrt(result["completed"])
    assert standard_error > 0
    assert abs(result["mean"] - R11_MEAN) <= 3 * standard_error, (
        result["mean"], standard_error)
