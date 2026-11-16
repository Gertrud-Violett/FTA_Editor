# Common-cause failure (CCF) groups, beta factor and alpha factor

**Applies to**: the web app (not the frozen desktop app) | **Models**: beta factor; alpha factor (groups of 2 to 4 members)

> Check CCF results with a qualified engineer before use.
> (ja: CCF の結果は、使用前に有資格の技術者が確認してください。)

This page states what the editor computes for a CCF group, with the source
and page of every formula, the assumptions behind it, what it does not do, and
worked examples you can repeat by hand. The same note and the assumptions are
shown in the **CCF groups** tab, in the CCF section of the DOCX report and in
the `ccf.note` field of the command-line JSON.

- [What a CCF group is](#what-a-ccf-group-is)
- [Sources](#sources)
- [The beta-factor model](#the-beta-factor-model)
- [How the editor applies it](#how-the-editor-applies-it)
- [Where the numbers show](#where-the-numbers-show)
- [Applied and not applied](#applied-and-not-applied)
- [The file format](#the-file-format)
- [Command line, report and API](#command-line-report-and-api)
- [Assumptions and limits](#assumptions-and-limits)
- [The alpha-factor model](#the-alpha-factor-model)
- [Alpha groups in the editor](#alpha-groups-in-the-editor)
- [Alpha lint codes](#alpha-lint-codes)
- [Alpha groups in the file, report, command line and API](#alpha-groups-in-the-file-report-command-line-and-api)
- [Source errors not to copy](#source-errors-not-to-copy)
- [Overlapping CCF events](#overlapping-ccf-events)
- [Worked examples](#worked-examples)
- [Alpha-factor reference cases](#alpha-factor-reference-cases)

## What a CCF group is

Redundant components are often modelled as independent basic events. They are
not: one cause (a shared design flaw, the same maintenance error, the same
environment) can fail all of them together. A **CCF group** lists basic
events that are identical redundant components and tells the editor how
likely it is that a failure of one of them is a failure of all of them. In
the beta-factor model that likelihood is one number, **β**: the fraction of a
component's total failure probability that is common to the whole group. In the
alpha-factor model (groups of 2 to 4 members) it is a list **α1 … αm**: α_k is
the fraction of the failure events in which exactly k of the m members fail,
and a testing scheme says how the data behind the α values were collected
([below](#the-alpha-factor-model)).

A group has a name, the model (`beta` or `alpha`), β (beta) or the α values and
the testing scheme (alpha), a list of member events and a free text source (for
example the data handbook and page β or α came from). Each basic event can be in
one group only.

## Sources

| Id | Document |
|---|---|
| S1 | NUREG/CR-5485 (1998), Mosleh, Rasmuson, Marshall, *Guidelines on Modeling Common-Cause Failures in Probabilistic Risk Assessment* |
| S2 | NUREG/CR-4780 Vol. 2 (1989), *Procedures for Treating Common Cause Failures in Safety and Reliability Studies* |
| S3 | NASA/SP-2011-3421, 2nd ed., *Probabilistic Risk Assessment Procedures Guide* |

Pages are the printed page numbers of those documents. The sources are cited
as sources of the formulas only; this page and the editor make no claim that
an analysis made with them follows any standard or has been approved by anyone.

## The beta-factor model

Let `Q_t` be the **total failure probability** of one member at mission time
(its probability, as the Quantification tab or the node's probability field
gives it), and `m` the number of members. The model splits `Q_t` into a part
that fails one member alone and a part that fails all members at once:

| Formula | Meaning | Source |
|---|---|---|
| `Q_1 = (1 − β)·Q_t` | independent part of each member | S2 Table C-1 p. C-5 and Eq. C.10-C.13 p. C-6; S1 Eq. 5.11-5.13 p. 42 |
| `Q_m = β·Q_t` | one event that fails all `m` members | S2 Table C-1 p. C-5 and Eq. C.10-C.13 p. C-6; S1 Eq. 5.11-5.13 p. 42; S3 Eq. 7-3 p. 7-5 (two-component group) |
| AND of two members: `Q_1² + Q_m` | top event of a two-train system, rare-event form | S1 Table 5-2 p. 49 (Case 1) |
| OR of two members: `2·Q_1 + Q_m` | same, for a system that fails if either member fails | S1 Table 5-2 p. 49 (Case 2) |
| Splitting `Q_t` versus splitting λ | agree only to first order in λT | S3 p. D-20 |

The editor applies the split to `Q_t`, not to λ. For a rate model
`Q_t = 1 − e^(−λT)`, and splitting λ instead gives the same result only to
first order in λT (S3 p. D-20).

The code that does this is `ccf.event_probabilities` in `fta_web/ccf.py`; its
docstring cites the same sources and pages as the table above. It is the only
place where the probabilities of a group are computed: the expansion of the
tree and the Monte Carlo trials both call it.

## How the editor applies it

**Members must be identical.** The model assumes identical components. A
group is applied only when its members have the same quantification model,
the same model parameters, the same `Q_t` and the same uncertainty. "The
same" means equal within a relative tolerance of **1e-6**; a rate entered as
per year on one member and per hour on another is the same stored number and
gives no finding. The CCF event uses the first member's `Q_t`; each independent
part is `(1 − β)` times that member's own `Q_t` (equal within 1e-6). In Monte
Carlo all of them follow the one shared draw.

**Expansion.** Before any analysis the editor replaces each member `X` of an
applied group by

```
X  →  OR( X (independent part), CCF event )
```

- the **independent part** keeps the member's id and its place in the tree and
  has probability `(1 − β)·Q_t`;
- the **CCF event** has the id `ccf:<groupId>` and probability `β·Q_t`. It is
  created once per group, so every reference to a member (a link, a transfer,
  the same id under two gates) reaches the same CCF event.

An alpha group has one CCF event for every subset of two or more members
instead of one for the whole group; see [the alpha-factor
model](#the-alpha-factor-model).

The expansion is done when the tree is compiled for the analysis (in
`fta_web/logic.py`, outside the hash-pinned core). Cut sets, importance and
Monte Carlo all work on the expanded structure. The tree you edit, the node
probabilities and the saved file are not changed by it: a member still shows
and stores `Q_t`.

A document without groups gives the same results as 1.8.1: checked against the
1.8.1 release on every bundled example and every b2b file, with the run time
`elapsedMs` left out of the comparison, floating-point numbers agreeing within a
relative 1e-13 (the last bits of a float, for example from `math.expm1`, can
differ between Python versions and platforms) and everything else exactly. A
document whose groups are all not applied gives the numbers of the tree without
them, plus the `ccf` block.

**Headline.** While at least one group is applied, the top-event value is the
**min-cut upper bound (MCUB)** of the expanded structure, because a shared
CCF event cannot be seen by the tree walk (the tree walk multiplies the
probabilities of independent branches; for the two-train example it is about
100 times too low). The headline reads "MCUB, includes CCF (n groups)".

With `P(C) = Π q` for a cut set `C`, the rare-event value is `Σ P(C)` and the
MCUB is `1 − Π (1 − P(C))` over the minimal cut sets (`fta_web/cutsets.py`).
The MCUB is the headline; the rare-event value is the form of the source
formulas (R1, R2).

If the cut sets cannot be completed (they ran out of time, failed, or hit the
summary's own cap of 2,000 sets), the editor shows **no headline value**: the
method is `incomplete`, the headline reads "incomplete, CCF not included", and
the tree-walk value is shown only under the label "tree walk, without CCF; cut
sets cut short (time | error | summary cap)". A plain number without CCF is
never shown as the headline.

Cut sets that the document's own limits (order, count, cutoff) drop are a
different matter: they are reported as truncation as before, and the MCUB is
that of the sets kept.

**Cut-set labels.** A CCF event is listed as `CCF: <group name>` with its
probability `β·Q_t`; a member's variable is listed as
`<member name> (independent part)` with `(1 − β)·Q_t`. In the first example
below the cut sets are `{ccf:g1}` and `{A, B}`. An event of an alpha group is
listed as `CCF: <group name> (<member names joined by " + ">)`, for example
`CCF: Relief valves (V1 + V2)`.

**Importance.** FV, Birnbaum, RAW and RRW are computed on the expanded
structure with the definitions of the Importance tab. The CCF event has its
own row; member rows are the independent parts. There is no row for "the
component" as a whole (independent part plus CCF), because RAW and RRW of such
a row would be a different quantity.

With `Q = 1 − Π (1 − P_j)` over the minimal cut sets (the MCUB) and `Q(q_i = x)`
the same value with event `i` set to probability `x`, the definitions
(`fta_web/importance.py`) are: Birnbaum `= Q(q_i = 1) − Q(q_i = 0)`;
Fussell-Vesely `= (Q − Q(q_i = 0)) / Q`; RAW `= Q(q_i = 1) / Q`; RRW
`= Q / Q(q_i = 0)`. The Fussell-Vesely value is therefore not the share of the
cut sets that hold the event.

**Monte Carlo.** For each applied group the trial draws **one** value of the
members' shared uncertain parameter per trial, which gives that trial's
`Q_t`; the independent parts and the CCF event follow as `(1 − β)·Q_t` and
`β·Q_t`. So the members move together, as identical components do, and the CCF
event gets no uncertainty of its own. **β is fixed: β and α are not sampled in
Monte Carlo.**

## Where the numbers show

| Where | What |
|---|---|
| Headline (top box) | "MCUB, includes CCF (n groups)", or "incomplete, CCF not included" with the labelled tree-walk value; "n CCF groups not applied" when a group is left out |
| Tree | a `CCF: <group name>` badge on each member; a group that is not applied reads `CCF: <group name> (off)`. Gates above a member (and a leaf with links to one) show the gate's MCUB, `n/a (CCF)` when the cut sets are incomplete, or a dash while the value loads; never the tree-walk value |
| Diagram | the same badge on each member's box (fault-tree mode only), the independent part beside the member's `Q_t` as `(indep. <value>)`, and the gate's MCUB with the label `(MCUB)` |
| Details | for a member: `Q_t (total)`, `Independent part` and `CCF event`, in a CCF block under the **Calculated probability** line; for a gate above a member, its MCUB marked "(MCUB, includes CCF)" |
| CCF groups tab | the groups, their status, the editor, the assumptions and the note |
| Cut Sets, Importance | `CCF: <group name>` and `<name> (independent part)`; for an alpha group `CCF: <group name> (<names>)` per member subset; clicking a CCF cut-set row highlights every member of that event in tree and diagram |
| Uncertainty tab, report | the line "β and α are not sampled in Monte Carlo" |
| Validation tab | an issue for every error or warning of a group, with a jump to the group |
| Excel and DOCX | gate values as in the diagram (MCUB or `n/a (CCF)`), a CCF section in the report, rows `CCF groups applied` and `CCF groups not applied` in the Analysis sheet |

The Details panel and the diagram keep showing `Q_t` for a member. The CCF
groups tab is available in Advanced mode only; the badges, the Details block,
the headline and the Validation issues show in both modes.

## Applied and not applied

A group is **applied** when it has no error. An **error** makes the group
*not applied*: it stays in the file, shows its reason in the tab, in the
headline note ("n CCF groups not applied"), in the Validation tab (with a jump
to the group), in the report (`Not applied: <reason>. Results exclude this
group.`) and in the CLI, and the numbers are those of the tree without it. A
**warning** leaves the group applied. A **status** makes the group not applied
without a Validation issue. Nothing is dropped or corrected silently.

The 12 codes that apply to every group (texts in English and Japanese name the
group and the member); the alpha-factor model adds four more, listed in
[Alpha lint codes](#alpha-lint-codes):

| Code | Condition | Severity |
|---|---|---|
| `CCF_MEMBER_NOT_BASIC` | a member is a gate or has children, a house event, a conditioning event, a transfer, or an id not in the tree | error |
| `CCF_TOO_FEW_MEMBERS` | fewer than 2 distinct members | error |
| `CCF_MEMBER_IN_TWO_GROUPS` | an event belongs to two groups (both groups are not applied) | error |
| `CCF_MEMBERS_DIFFER` | members differ in quantification model, in a model parameter or `Q_t` by more than relative 1e-6, or in uncertainty (distribution, median or mean, error factor) | error |
| `CCF_NO_PROBABILITY` | a member has no probability (a model parameter is missing) | error |
| `CCF_Q_ONE` | a member's `Q_t` is 1 (splitting a certain failure would lower it) | error |
| `CCF_BAD_PARAMETER` | β loaded from a file is not a finite number in [0, 1]; also a model other than `beta` or `alpha`, a missing or repeated group id, a tree node whose id starts with `ccf:` (that prefix is reserved), or (kind `event_id`) a CCF event id that would be made twice, see [Event ids](#event-ids-and-the-expansion) | error |
| `CCF_MEMBER_RENAMED` | a member id was renamed when the file was opened (duplicate-id repair), so it is not clear which event is meant | error |
| `CCF_ETA_MODE` | the document is in ETA mode | status |
| `CCF_HIGH_Q` | a member's `Q_t` is above 0.01 | warning |
| `CCF_ZERO_Q` | the members' `Q_t` is 0, so the group has no effect | warning |
| `CCF_ORDERED_GATE` | a member sits below a PAND or XOR gate | warning |

Members under INHIBIT or k-out-of-n gates, and a member that is reached twice
(links, transfers), give no finding.

**ETA mode.** Groups are not used in event trees. In ETA mode every group has
the status `Not applied: ETA mode`, the tab is greyed, and the groups stay in
the file and can still be edited. `CCF_ETA_MODE` is a status, not a Validation
issue.

**The tree follows the groups.** Deleting a member node (single or batch
delete, an AI update, an FMEA re-import that replaces nodes, or undoing the
node's creation) removes it from its group in the same undo step, and undo
restores both. Making a member a gate keeps it in the group, and the group is
then flagged `CCF_MEMBER_NOT_BASIC`.

## The file format

Groups are saved under `analysis.ccfGroups`, and a file with at least one
group also gets the top-level key `"fileFormatVersion": 2`:

```json
{
  "fileFormatVersion": 2,
  "analysis": {
    "ccfGroups": [
      {"id": "g1", "name": "Feed pumps", "model": "beta", "beta": 0.1,
       "alpha": null, "testing": null,
       "members": ["n12", "n13"], "source": "free text, e.g. data handbook and page"}
    ]
  }
}
```

An alpha group uses the same eight keys; see [the file keys of an alpha
group](#alpha-groups-in-the-file-report-command-line-and-api).

- A file without groups is saved exactly as in 1.8.1 (no `ccfGroups`, no
  `fileFormatVersion`). The last group removed takes the key with it.
- A group with invalid values (β or an α that is not a number in [0, 1], a
  missing member, an unknown model) is kept as it is in the file and flagged; it
  is never corrected or dropped.
- A file whose `fileFormatVersion` is greater than 2 opens with the warning
  "This file was saved by a newer FTA Editor; saving may lose data".
- **Older programs lose the groups.** FTA Editor 1.8.x opens such a file,
  warns "reset to their defaults: ccfGroups" and saves it without the groups.
  The frozen desktop app does not keep the `analysis` block at all: saving
  there drops every analysis setting, groups included. Do not save a file that
  has CCF groups with either of them.

## Command line, report and API

**CLI.** For a file with groups, `quantify`, `cutsets`, `importance` and `mc`
with `--json` give the same numbers as the API and add a `ccf` block
`{applied, notApplied: [{id, name, code, reason}], note}`; the text output
prints one line `CCF group not applied: <name> (<id>): <reason>` per group not
applied and the engineer note. A file without groups gets no `ccf` block. For an
alpha group, an item of `applied` also holds `alpha`, `testing`, `alphaSum` and
`alphaNormalised`.

Exit codes of these four commands, in fault-tree mode: **0** when every group
is applied, the headline is complete and nothing else fails; **1** when a group
is not applied, the headline is `incomplete`, or anything else fails as before
(a validation error, a failed analysis). In ETA mode, `quantify` adds the `ccf` block with
every group in `notApplied` (code `CCF_ETA_MODE`) and exits 0; `cutsets`,
`importance` and `mc` keep their existing ETA refusal and exit code. Groups
never change the exit code in ETA mode. The other exit codes (2 usage, 3
unreadable input) are unchanged.

**Report.** When the document has groups, the DOCX report has a CCF section
after the Assumptions (it is always written; it is not one of the sections you
can untick, so a report cannot hide a group that was not applied). It lists:

- per group, the name, model, parameters, testing scheme, source, members and
  status;
- the formulas with their sources and pages;
- the assumptions below, the overlapping-events note and the engineer note;
- for each group not applied, `Not applied: <reason>. Results exclude this group.`

The headline line of the report says "includes CCF (n groups)" or "incomplete,
CCF not included", and CCF events appear in the cut-set and importance tables.

**API.** See [API_REFERENCE.md](API_REFERENCE.md#ccf-groups-api-19) for
`/api/ccf/groups` and the added result fields, and the
[User Guide](USER_GUIDE.md#ccf-groups-beta-factor-and-alpha-factor) for the screens.

## Assumptions and limits

The CCF groups tab shows the first six of these, and a seventh while the document
has an alpha group; the report lists the first six under Assumptions and puts the
alpha sentence once under Formulas.

1. The model and its formula: `Q_1 = (1 − β)·Q_t` for each member and
   `Q_m = β·Q_t` for one event failing all `m` members (S2 Table C-1 p. C-5
   and Eq. C.10-C.13 p. C-6; S1 Eq. 5.11-5.13 p. 42). The formulas of the
   alpha-factor model are the seventh assumption, below.
2. A member's probability is its total failure probability `Q_t` at mission
   time.
3. Beta factor: the CCF event fails all members together.
4. The split is applied to `Q_t`; splitting λ instead agrees only to first
   order in λT (S3 p. D-20).
5. The headline is the min-cut upper bound; the formulas in the sources use
   the rare-event approximation.
6. β and α are not sampled in Monte Carlo.
7. Only while the document has an alpha group: *Alpha-factor model: Q_k is the
   probability of each CCF event that fails exactly k of the group's members;
   staggered Q_k = α_k / C(m-1, k-1) · Q_t (NUREG/CR-5485 Eq. 5.6 p. 40);
   non-staggered Q_k = k / C(m-1, k-1) · (α_k / α_t) · Q_t with
   α_t = Σ k·α_k (Eq. 5.7-5.9 p. 41; NUREG/CR-4780 Vol. 2 Eq. C.23-C.24
   pp. C-10/C-11).*

Further limits:

- **Check results with a qualified engineer.** The editor does not judge
  whether β is right for your components, whether the members are really
  identical, or whether a beta-factor group is the right model for your
  system. For an alpha group the same holds for the α values and the testing
  scheme. Those are engineering decisions; check CCF results with a qualified
  engineer before use.
- **Small probabilities.** The models are meant for small `Q_t`. S1 p. A-5 says
  that if the common-cause basic events (CCBEs) Q_k^(m) are treated as
  independent instead of mutually exclusive, Eq. A.8, the sum
  `Q_t = Σ C(m−1, k−1)·Q_k`, "is still valid under the rare event
  approximation". After the expansion a member's own failure probability is
  `1 − (1 − (1 − β)·Q_t)(1 − β·Q_t) = Q_t − β(1 − β)·Q_t²`, not `Q_t`. The
  relative difference is `β(1 − β)·Q_t`, at most `0.25·Q_t`: at most 0.25 % for
  `Q_t ≤ 0.01`, but up to 2.5 % at `Q_t = 0.1`. `CCF_HIGH_Q` warns above
  `Q_t = 0.01`. That threshold on `Q_t` is a rule of this editor; S1 p. 44 gives
  10^-2 for the independent event unavailability, as one condition for the
  global-term simplification of the beta factor model. Check the result when
  the warning shows. An alpha group gets the same warning with its own text
  (the alpha-factor model assumes small probabilities); no page is cited for it.
- **Identical members only.** One β (or one α list) and one `Q_t` per group. Members that
  differ are not averaged: the group is not applied (`CCF_MEMBERS_DIFFER`).
- **Order logic is not kept.** The cut sets read a PAND gate as AND and an XOR
  gate as OR, so a CCF event below such a gate ignores the order or exclusion
  logic (`CCF_ORDERED_GATE`).
- **Gate values and truncation.** The value of a gate above a member is the MCUB
  of that gate's cut sets as the expansion kept them. A leaf with AND or OR
  links counts as a gate here, including a member that has links: its links
  make it "A and B" or "A or B". It shows the MCUB of its expanded cut sets, or
  `n/a (CCF)`, never the tree-walk value. A member without links keeps its
  `Q_t`.

  When the document's own limits (maximum order, maximum count, cutoff) drop
  cut sets, a gate's value is the MCUB of the sets that remain, which can be
  below the value without the limits. The Cut Sets tab and the API report the
  truncation as before.
- **One group per event.** An event in two groups makes both groups not
  applied.
- **Group size.** Any number of members from 2 upward is accepted by the beta
  model; one CCF event fails all of them. Partial failures of some members are
  not modelled by it. The alpha-factor model takes 2 to 4 members (more or fewer:
  `CCF_ALPHA_SIZE`) and models the partial failures.
- **Monte Carlo** samples the shared uncertain parameter of each group but not
  β or α.
- **No statement about standards.** The editor reports a calculation, with its
  sources. It does not state or imply that the result meets any standard.

## The alpha-factor model

The alpha-factor model is for a group of **2 to 4** identical members. It
describes partial common-cause failures: some members of the group fail together
and the others do not. The data are the fractions **α_k** (k = 1 … m): the
fraction of the failure events of the group in which exactly k of the m members
fail. They are dimensionless numbers from 0 to 1 that add up to 1. The result
is a probability `Q_k` for **each** set of k members that fail together;
`Q_1` is the independent part of every member.

A member of the group is in `C(m−1, k−1)` of the `C(m, k)` sets of k members.
The model is built so that these add up to the member's total failure
probability `Q_t`:

`Σ_k C(m−1, k−1)·Q_k = Q_t` (k = 1 … m), for both testing schemes.

The test suite checks this identity within relative 1e-12 over 1,000 seeded
random α sets for each of m = 2, 3, 4 and each scheme.

### Formulas and sources

Let `α'_k = α_k / Σα` (the α values after the division described under
[Normalisation](#normalisation)); with a sum of exactly 1, `α'_k = α_k`.

| Testing scheme | Formula | Source |
|---|---|---|
| Staggered | `Q_k = α'_k / C(m−1, k−1) · Q_t` | S1 Eq. 5.6 p. 40 |
| Non-staggered | `Q_k = k / C(m−1, k−1) · (α'_k / α_t) · Q_t`, with `α_t = Σ k·α'_k` | S1 Eq. 5.7-5.9 p. 41; S2 Eq. C.23-C.24 pp. C-10/C-11 |

The formulas are derived from S1 Eq. 5.6 and 5.7, not copied from the places
listed under [Source errors not to copy](#source-errors-not-to-copy). The
non-staggered formula was also compared with S3 Eq. 7-12 to 7-14 p. 7-14, which
agree. About S2: it is cited as given above and only partly checked.
Eq. C.21, C.22 and C.24 are consistent with the formula in the available text;
the body of C.23 could not be read.

The consistency identity above gives, for the staggered scheme, `Σ α'_k = 1`
(each term is `α'_k·Q_t`), and for the non-staggered scheme
`Σ k·α'_k / α_t = 1`. The code that evaluates the formulas is `_alpha_model` in
`fta_web/ccf.py`; its docstring cites the same equations and pages. Like the
beta model it is reached only through `ccf.event_probabilities`, so the
expansion and the Monte Carlo trials use the same numbers.

**m = 2 and the beta model.** For m = 2 the staggered formula (k = 1, 2, with
`C(1,0) = C(1,1) = 1`) gives `Q_1 = α_1·Q_t` and `Q_2 = α_2·Q_t`. With
`α = (1 − β, β)` these are `(1 − β)·Q_t` and `β·Q_t`, the beta-factor model. This
is derived here from Eq. 5.6; S1 p. E-2 prints the relation for three components
(staggered `α_1 = 1 − β`, `α_2 = β(1 − γ)`, `α_3 = βγ`), not the m = 2 result.
The test suite compares the cut-set probabilities of the alpha group and of the
beta group within relative 1e-12 for β = 0, 0.05, 0.1 and 1. The non-staggered
scheme does not reduce to the beta model: for m = 2 and `α = (1 − β, β)` it gives
`Q_2 = 2β / (1 + β)·Q_t`.

### The testing scheme

The two formulas differ because of how the data behind the α values were
collected. S1 p. 40 ties the choice to "the way systems in the database are
tested". S3 p. 7-9 (see also S3 p. 7-14) gives the definition: **non-staggered**
testing means the components are tested simultaneously; **staggered** testing
means they are tested one at a time at fixed time intervals.

S3 p. 7-15 remarks that the assumptions apply to parameter estimation as part of
the data collection, and that "During modeling activities, the typical CCF model
to be used will be that of non-staggered testing." That is a remark of the
source about modelling practice. **The editor has no default scheme**: it does
not choose non-staggered, or any scheme, for you. You choose one for every alpha
group, from the source of your α values. The choice matters: with
`α = (0.955, 0.034, 0.011)` and `Q_t = 1e-3` the CCF part of one member, which
is in two of the three pairs and in the triple (`2·Q_2 + Q_3`), is 4.5e-5
staggered and 9.564e-5 non-staggered, a factor of about 2.13. The CCF part of the
failure of 2 of the 3 members (`3·Q_2 + Q_3`, the quantity of R7 and R9) is
6.2e-5 staggered and 1.27841e-4 non-staggered, a factor of about 2.06.

A group whose scheme is not chosen is **not applied**, with the status
`Not applied: testing scheme missing`.

### Event ids and the expansion

For every subset of two or more members the editor makes one CCF event with
`q = Q_k` (k is the size of the subset). Its id is

`ccf:<groupId>:<m1>+<m2>…`

with the member ids joined by `+` in the order of the group's member list. The
events are ordered by size, then by position in the group: for three members
`n20`, `n21`, `n22` in group `g2` they are `ccf:g2:n20+n21`, `ccf:g2:n20+n22`,
`ccf:g2:n21+n22` and `ccf:g2:n20+n21+n22`. A group of 2, 3 or 4 members has 1,
4 or 11 events (2^m − m − 1). An event whose `Q_k` is 0 (an `α_k` of 0) is still
created. It has probability 0, so the default cut-set cutoff (1e-15) drops it
from the cut sets, as it does for a beta factor of 0; with the cutoff set to 0
the cut set stays in the list with probability 0. The numbers in this document
were computed with the default limits (maximum order 6, maximum count 5000,
cutoff 1e-15); no cut set with a non-zero probability in them is below that
cutoff. At the default cutoff very small events can fall below it: when every
cut set of a top event is below 1e-15 (for the AND of two members with
`α = (0.9, 0.1)`, a `Q_t` under about 1e-14), the cut-set list is empty, the
headline is 0.0 and the truncation shows `cutoff`; no "incomplete" note is
raised for that.

Each member `X` of an applied group is replaced by

```
X  →  OR( X (independent part, Q_1), every CCF event that contains X )
```

so for a group `{A, B, C}`, `A` becomes
`OR(A, ccf:g:A+B, ccf:g:A+C, ccf:g:A+B+C)`. All events of the group are created
once, when the first member is referenced; a link, a transfer or the same id
under two gates reaches the same events. The independent part keeps the
member's id and place and has `q = Q_1` (its `Q_t` is the member's). The headline
is the min-cut upper bound, as for a beta group, and each CCF event has its own
row in the cut sets and in the importance table.

**A member's own probability.** The members of an alpha group are identical
(`CCF_MEMBERS_DIFFER` otherwise, at a relative tolerance of 1e-6), and every `Q_k`,
`Q_1` included, uses the first member's `Q_t`. After the expansion the editor treats
the independent part and the CCF events as independent events, so a member's own
failure probability is not `Q_t` but, for a group of 3,
`1 − (1 − Q_1)(1 − Q_2)²(1 − Q_3)`. The terms add up to `Q_t` as a sum (the
identity above); the combination differs from `Q_t` by a second-order amount, about
−4.4e-5 relative for R7 and −9.0e-5 for R9 at `Q_t = 1e-3`. The same independence
is behind the note on [overlapping CCF events](#overlapping-ccf-events).

**A new refusal: ids that would clash.** The ids are made with `+` and `:`, so
group or member ids that contain these characters could make the same event id
twice and the structure would silently merge two different events (an example:
members `a`, `b+c`, `a+b` and `c` give `a+b+c` twice; an alpha group `g` on `a`
and `b` and a beta group with the id `g:a+b` both give `ccf:g:a+b`). The editor
checks the event ids of all groups and does not apply a group that holds an id
that occurs more than once, in its own group or in another (both groups of a
clash): `CCF_BAD_PARAMETER`, kind `event_id`. Ordinary ids, without `+` or `:`,
never clash. Rename the ids that contain these characters.

### Normalisation

Published α sets are rounded, so their sum is often a little off 1. The editor
(`CCF_ALPHA_SUM`, `CCF_ALPHA_NORMALISED`):

- accepts an α list whose sum is within **1e-3** of 1 and divides every α_k by the
  sum before use; if the difference is **more than 1e-9** the group stays
  applied and carries the warning `CCF_ALPHA_NORMALISED` with the original sum;
- divides inside 1e-9 too (the values then change by at most 1e-9 relative, e.g.
  5e-10 for a sum of 1 + 5e-10) but raises no warning;
- refuses a sum **more than 1e-3** from 1: `CCF_ALPHA_SUM`, the group is not
  applied. A slack of 1e-15 at both edges (1e-3 and 1e-9) absorbs floating-point
  noise in the sum (the noise of a sum of up to four values is a few times
  1e-16), so that `(0.899, 0.1)`, whose decimal deviation is exactly 0.001, is
  inside the 1e-3 band, and a difference that exceeds 1e-9 only by that noise
  raises no warning;
- does not apply a list with an α_k that is not a finite number from 0 to 1, or
  whose length is not the number of members.

For the non-staggered scheme the division changes nothing (the formula depends on
`α_k / α_t`, and both scale together); only the warning and the note appear. For
the staggered scheme the division changes the values.

### Monte Carlo

α is fixed: it is not sampled, as β is not. The trial draws one `Q_t` per
group per trial from the members' shared uncertainty, and every `Q_k` of the trial
is computed from it with the same formula (each is a constant times `Q_t`, because
α is fixed). The note "β and α are not sampled in Monte Carlo" stays.

## Alpha groups in the editor

In the **CCF groups** tab (Advanced mode) the model selector of the group editor
offers **Beta factor** and **Alpha factor**. For an alpha group the editor shows:

- **α1 … αm**, one field per member, labelled "αk (dimensionless, 0 to 1)". They
  read the same typed texts as the other number fields (`0.05`, `5e-2`, `5%` as
  0.05, a simple fraction). A value outside 0 to 1, or text, gives a message under
  the field and sends nothing.
- A **Testing scheme** selector: "Staggered testing" and "Non-staggered testing".
  **Nothing is preselected** and the editor chooses nothing for you; the first
  entry reads "Choose a testing scheme".
- A live line, **Sum of α**. Within 1e-9 of 1 it shows the sum; within 1e-3 it
  adds that each α is divided by the sum and lists the values used (the
  normalisation note); further off it shows that the sum must be 1.
- **Save α values**. Edits to the α fields are sent with this button (or Enter in
  a field), as one request and one undo step for the whole list.
- A status line: `Applied` or `Not applied: <reason>`, with a `Warning:` line for
  each warning (for example the normalisation note, with the original sum).

You can create a group without choosing a scheme; it then reads
`Not applied: testing scheme missing` in the table, in the editor and in the
Validation tab, until you choose one. Choosing a scheme, saving α values, and
adding or removing members are each one undo step; Undo and Redo restore the
editor with the group.

Members and α are separate. Adding or removing a member **never changes the
stored α list**. If the number of α values then differs from the number of
members the group is not applied (`CCF_ALPHA_SUM`, kind `length`), the editor
shows the fields for the new member count (a missing α_k is empty) with a
hint, and you save the list again. A group with more than 4 members (or fewer
than 2) shows that the alpha-factor model needs 2 to 4 members and has no α
fields.

Changing the model of an existing group sends nothing by itself. The new
model's parameters are sent together with the change when you commit them
(**Save α values**, or the β field), as one request and one undo step; the old
model's values are set to `null`, and Undo restores them.

## Alpha lint codes

The alpha-factor model adds four codes to the 12 of
[Applied and not applied](#applied-and-not-applied). They are tested in the
order given, after the checks on the members (too few, not a basic event,
renamed, in two groups) and before the checks for a missing probability,
differing members and `Q_t` of 1. Texts are in English and Japanese; a group
with no error is applied.

| Code | Condition | Severity |
|---|---|---|
| `CCF_ALPHA_SIZE` | the group has fewer than 2 or more than 4 members (for fewer than 2, `CCF_TOO_FEW_MEMBERS` also fires and is listed first). The sum is not tested then | error |
| `CCF_ALPHA_SUM` | kind `length`: the number of α values is not the number of members; kind `range`: an α_k is not a finite number from 0 to 1 (the message names its position); kind `sum`: the α values do not add up to 1 within 1e-3 | error |
| `CCF_ALPHA_NORMALISED` | the sum is more than 1e-9 and at most 1e-3 from 1; each α is divided by the sum and the text shows the original sum | warning |
| `CCF_NO_TESTING` | kind `missing`: the testing scheme is `null`, absent or empty (`Not applied: testing scheme missing`); kind `unknown`: any other value than `staggered` and `nonStaggered` (for example `non-staggered` in a file) | error |

A warning leaves the group applied. `CCF_HIGH_Q` also has a text for alpha
groups.

## Alpha groups in the file, report, command line and API

**File.** An alpha group is saved with the same eight keys as a beta group
(`fileFormatVersion` stays 2):

```json
{"id": "g2", "name": "Relief valves", "model": "alpha", "beta": null,
 "alpha": [0.955, 0.034, 0.011], "testing": "staggered",
 "members": ["n20", "n21", "n22"], "source": "free text"}
```

- `model` is `"alpha"`; `beta` is `null`. `alpha` is the list α1 … αm, where the
  position is the number of failing members. `testing` is `"staggered"`,
  `"nonStaggered"` (no hyphen) or `null` when no scheme is chosen.
- A beta group keeps `alpha` and `testing` as `null`. A value of the other
  model's key that a file holds is kept verbatim and ignored.
- A file with an invalid alpha group (a wrong length, an α outside 0 to 1, an
  unknown scheme) is kept as it is and flagged; it is never corrected.

**Report.** The CCF section shows, for an alpha group, the model `Alpha factor`,
the parameters `α = (0.955, 0.034, 0.011)` (with `; sum 1.0005, each α divided
by the sum` when normalised) and a **Testing scheme** column (`Staggered
testing`, `Non-staggered testing` or `not chosen`; a dash for a beta group). The
formulas block gets the alpha sentence with the two alpha formulas, their source and
page (once, when the document has an alpha group; it is not repeated under the
assumptions). After the
overlapping-events note of the report there is one line for each applied alpha
group of 3 or 4 members, see [Overlapping CCF events](#overlapping-ccf-events).
A group not applied reads `Not applied: <reason>. Results exclude this group.`.

**Command line.** With `--json`, the `ccf.applied` items of an alpha group
carry `alpha`, `testing`, `alphaSum` (the original sum) and `alphaNormalised`.
A group without a scheme is in `notApplied` with the code `CCF_NO_TESTING` and
the reason `testing scheme missing`, and the exit code is 1 as for any group not
applied. A normalised group is applied and does not change the exit code.

**API.** `POST` and `PATCH /api/ccf/groups` take `model`, `alpha` and `testing`;
see [API_REFERENCE.md](API_REFERENCE.md#ccf-groups-api-19).

## Source errors not to copy

The alpha formulas are derived from S1 Eq. 5.6 and 5.7. These places are wrong
in the sources and are **not copied**:

- S1 p. 41 Eq. 5.10 prints `Q3 = 3α3·Q_t`; it should be `α3·Q_t` (the m = 3
  case of Eq. 5.6).
- S1 Tables 5-4 and 5-5 have the `m = 4` rows swapped. The `m = 4` results here
  come from Eq. 5.6 and the Case formulas of S1 Table 5-2 p. 49, never from those
  tables.
- S1 Table 5-5 "2 of 5" has a stray `/4`.
- S3 (NASA/SP-2011-3421) Eq. 7-16 p. 7-15 repeats the Eq. 5.10 error and prints
  `3α3·Q_t`; S3 Eq. 7-15 is right. It is not copied either.

## Overlapping CCF events

With alpha-factor groups of 3 or 4 members, this editor treats the CCF events
of a group as independent basic events, so minimal cut sets with two CCF events
that share a member (for example `{C_AB, C_AC}`) are kept. NUREG/CR-5485 treats
such events as mutually exclusive and disallows those cut sets (pp. 47-48;
Table E-2 p. E-4). The kept cut sets raise the rare-event sum and the min-cut
upper bound by a second-order amount. For a system that fails only when all
three members fail (the AND of three; S1 calls it "1 of 3", meaning one
of the three is enough to keep it working), the amount is `3·Q_2²`; at
`Q_t = 1e-3` that is 7.8e-5 relative for `α = (0.955, 0.034, 0.011)` with
staggered testing and 9.9e-5 non-staggered, and 6.0e-4 and 7.2e-4 for
`α = (0.9, 0.09, 0.01)`. The relative amount can be larger when `α_m` is very
small compared with `α_2`.

Events with no member in common, such as `{C_AB, C_CD}`, are kept both by
NUREG/CR-5485 (Table 5-2 p. 49) and by this editor. A beta-factor group has one
CCF event, so none of this arises for it.

## Worked examples

These are **formulas evaluated at `Q_t = 1e-3` and β = 0.1**, not numeric
examples printed in the sources: we found no numeric worked example of a two-
or three-train top event in S1, S2 or S3. The numbers are the tests' expected values
(`fta_web/tests/acceptance/ccf/`).

Common: `Q_1 = (1 − 0.1) × 1e-3 = 9.0e-4`, `Q_m = 0.1 × 1e-3 = 1.0e-4`.

**R1: AND of two members** (tree: top OR [ gate AND [A, B], C ], C with
probability 0 so that the top is the AND gate). Label: published formula,
S1 Table 5-2 p. 49 (Case 1); S3 Eq. 7-3 p. 7-5.

- Cut sets: `{ccf:g1}` with `1.0e-4`, and `{A, B}` with
  `9.0e-4 × 9.0e-4 = 8.1e-7`.
- Rare-event sum: `Q_1² + Q_m = 8.1e-7 + 1.0e-4 =` **1.0081e-4**.
- The tree walk of the same tree gives `1e-6` (`Q_t²`): about 100 times too
  low, which is why the headline is the MCUB.

**R1h: the same, as MCUB** (hand calculation). `1 − (1 − 1.0e-4)(1 − 8.1e-7) =`
**1.00809919e-4**. Importance of `ccf:g1`: Birnbaum `= 1 − 8.1e-7 = 0.99999919`,
RAW `= 1 / 1.00809919e-4 = 9919.6588`, RRW `= 1.00809919e-4 / 8.1e-7 = 124.45669`,
FV `= 0.9919650763731` (the tests compare at relative 1e-9).

**R2: OR of two members** (tree: top OR [ A, B ]). Label: published formula,
S1 Table 5-2 p. 49 (Case 2). Cut sets `{A}`, `{B}` (each `9.0e-4`) and
`{ccf:g1}` (`1.0e-4`). Rare-event sum: `2·Q_1 + Q_m = 1.8e-3 + 1.0e-4 =`
**1.9e-3**.

**R2h: the same, as MCUB** (hand calculation).
`1 − (1 − 9.0e-4)²(1 − 1.0e-4) =` **1.899010081e-3**.

**R3: β = 0** (the R1 tree; hand calculation). `Q_1 = 1e-3`, `Q_m = 0`: MCUB
**1e-6**, equal to the tree without the group; the cut sets are equal once the
zero-probability CCF set is dropped.

**R4: β = 1** (the R1 tree; hand calculation). `Q_1 = 0`, `Q_m = 1e-3`: the top
event is **1e-3** (the members fail only together).

**R11: Monte Carlo** (hand calculation). AND of two members, β = 0.1, members
lognormal with median 1e-3 and error factor 3. With one shared draw `Q_t` per
trial, the rare-event (first-order) form is
`E[top] ≈ β·E[Q_t] + (1 − β)²·E[Q_t²]`. With `σ = ln 3 / 1.645 = 0.66785`:
`E[Q_t] = 1.2498e-3`, `E[Q_t²] = 2.4401e-6`, so `E[top] ≈ 1.2696e-4`. The cut
sets are chosen once, before the trials, from the point values: the most
probable ones until they cover at least 99.99 % of the rare-event sum, at most
2,000 of them. Here {ccf:g1} alone covers 99.20 %, so both cut sets are kept:
the CCF event, and the two independent parts together as one set. Each trial
computes the MCUB of these two cut sets with its own draw of `Q_t`; its exact
mean is 1.269594e-4: it differs by
`−β(1 − β)²·E[Q_t³]`, 4.7e-6 relative, far below the test's 3 standard errors.
The test runs 200,000 trials with a fixed seed and requires the mean to be
within 3 standard errors of 1.2696e-4.

## Alpha-factor reference cases

These are **formulas evaluated at `Q_t = 1e-3`**, as the worked examples above.
Each case has a label that says where its formula comes from: *published formula*
(the formula is printed in the cited table or equation; the number is our
evaluation of it) or *hand calculation* (ours). "Exact" values are checked at
relative 1e-12 (rare-event sums) or 1e-9 (min-cut upper bound), "rounded" values
to half a unit of the last digit shown. The tests are in
`fta_web/tests/acceptance/ccf_alpha/`. The α set of R7 to R10h,
`(0.955, 0.034, 0.011)`, is the set of S3 p. 7-16.

**R5: staggered, m = 2, α = (0.9, 0.1).** Label: published formula, S1 Table 5-4
p. 53. `Q_1 = 0.9 × 1e-3 = 9e-4`, `Q_2 = 0.1 × 1e-3 =` **1e-4**, the same as R1
(β = 0.1). For the AND of the two members the rare-event sum is **1.0081e-4** and
the MCUB 1.00809919e-4, the R1 values (exact).

**R6: non-staggered, m = 2, α = (0.95, 0.05).** Label: published formula, S1
Table 5-5 p. 54. `α_t = 1·0.95 + 2·0.05 = 1.05`;
`Q_2 = 2 / C(1,1) · (0.05 / 1.05) × 1e-3 =` **9.5238095e-5** (rounded).

**R6h: the same, AND of the two members** (hand calculation).
`Q_1 = (0.95 / 1.05) × 1e-3 =` **9.0476190e-4**; rare-event sum
`Q_1² + Q_2 =` **9.6056689e-5**; MCUB `1 − (1 − Q_2)(1 − Q_1²) =`
**9.6056611e-5** (rounded).

**R7: staggered, m = 3, α = (0.955, 0.034, 0.011).** Label: published formula, S1
Table 5-4 p. 53. `Q_1 = 9.55e-4`; `Q_2 = (0.034 / C(2,1)) × 1e-3 = 1.7e-5` for each
of the three pairs; `Q_3 = 0.011 × 1e-3 = 1.1e-5`. The CCF part of the failure
of 2 of the 3 members (the three pairs and the triple), `3·Q_2 + Q_3 =`
**6.2e-5** (exact). (The CCF part of one member, which is in two pairs, is
`2·Q_2 + Q_3 = 4.5e-5`.)

**R8: the same, 2-of-3** (the top event occurs when at least two of the three
members fail; a 2-out-of-3 failure gate). Label:
published formula, S1 Table 5-2 p. 49 (Case 4); cut sets S1 Table E-2 p. E-4.
There are **7 cut sets**: the three pairs of independent parts and the four CCF
events. Rare-event sum `3·Q_1² + 3·Q_2 + Q_3 =` **6.4736075e-5** (exact).

**R8h: the same, as MCUB** (hand calculation): **6.47344749e-5** (rounded).

**R9: non-staggered, m = 3, same α.** Label: published formula, S1 Table 5-5
p. 54. `α_t = 0.955 + 2·0.034 + 3·0.011 = 1.056`;
`Q_1 = (0.955 / 1.056) × 1e-3 = 9.0435606e-4`;
`Q_2 = (2 / C(2,1))·(0.034 / 1.056) × 1e-3 = 3.2196970e-5`;
`Q_3 = (3 / C(2,2))·(0.011 / 1.056) × 1e-3 = 3.1250000e-5`. The CCF part of the
failure of 2 of the 3 members, `3·Q_2 + Q_3 =` **1.27841e-4** (rounded), is about
2.06 times that of R7.

**R9h: the same, 2-of-3** (hand calculation). Rare-event sum
`3·Q_1² + 3·Q_2 + Q_3 =` **1.302945e-4**; MCUB **1.302880e-4** (rounded).

**R10: staggered, m = 3, same α, 1-of-3** (S1's label for a system that fails only
when all three members fail; the top event occurs when all three fail). Label:
published formula, S1 Table 5-2 p. 49 (Case 3).
`Q_1³ + 3·Q_1·Q_2 + Q_3 =` **1.10495760e-5** (rounded). This formula leaves out
the cut sets with two CCF events of the group, which the editor keeps (next case).

**R10h: the same, as the editor computes it** (hand calculation). The editor
keeps the three cut sets `{C_AB, C_AC}`, `{C_AB, C_BC}` and `{C_AC, C_BC}`, each
with probability `Q_2²`, so the rare-event sum is `R10 + 3·Q_2² =`
**1.10504430e-5** (rounded). `R10h − R10 = 3·Q_2² = 8.67e-10`; the test checks
this at relative 1e-9. See [Overlapping CCF events](#overlapping-ccf-events).

**Four members (S1 Table 5-2 Cases 8 and 9, p. 49).** Staggered,
`α = (0.95, 0.03, 0.01, 0.01)`: `Q_1 = 9.5e-4`, `Q_2 = 0.03 / 3 × 1e-3 = 1e-5`,
`Q_3 = 0.01 / 3 × 1e-3 = 3.3333333e-6`, `Q_4 = 1e-5`.

- *Case 9, "4 of 4 must operate"* (the system fails when any one of the four
  members fails: the OR of the four members; 15 cut sets):
  `4·Q_1 + 6·Q_2 + 4·Q_3 + Q_4 =` **3.8833333e-3**.
- *Case 8, "3 of 4 must operate"* (the system fails when at least two of the four
  members fail: a 2-of-4 failure gate; 17 cut sets):
  `6·Q_1² + 6·Q_2 + 4·Q_3 + Q_4 =` **8.8748333e-5**. Its CCF term
  `6·Q_2 + 4·Q_3 + Q_4` is 8.3333333e-5.

These are the cases where S1 Tables 5-4 and 5-5 are wrong (the swapped `m = 4`
row would give a CCF term of 2.33e-5 for Case 8). The numbers come from Eq. 5.6
and the Case formulas, not from those tables.

Where the sums above are not printed in a source, they are our evaluation of the
formula. No numeric worked example of a two- or three-train top event was found
in S1, S2 or S3.

**Published tables, shown beside the tool values.** Two published tables of
NUREG/CR-5485 are rounded coarsely, so the tool values are shown beside them and
no exact match is claimed.

- *Table 3-1 p. 13, factor g.* g is the probability of the global CCF event
  that fails the system (the sum of the CCF events that fail it), divided by the
  failure probability Q_t of one component
  (S1 p. 12 Eq. 3.1: g = Q(CCF) / P(A), for identical members). It is a ratio to
  Q_t, so Q_t cancels. The labels "2 of 4" and "3 of 4" are S1's success labels:
  a "2 of 4" system fails at 3 failures (the 3-of-4 failure gate) and a "3 of 4"
  system fails at 2 failures (the 2-of-4 failure gate). The α set is
  `(0.95, 0.0213, 0.0101, 0.0186)` of S1 Table 5-11 p. 75. That this set is the
  one behind Table 3-1 is an inference from the numbers: S1 p. 48 says Table 3-1
  uses the formulae of Section 5 and the generic estimates of Section 5.5.4.
  Tool values, staggered: 2 of 4 0.032067 (printed 0.04), 3 of 4 0.074667
  (0.08); non-staggered: 2 of 4 0.104620 (0.11), 3 of 4 0.182266 (0.19). These
  four printed values are the tool values rounded up to two decimals. That is an
  observation, not a rule of the source: in the non-staggered m = 2 row of the
  same table the printed 0.10 is higher than the tool value 0.089780 rounded up
  (0.09).
- *Table 6-10 p. 105 (Section 6.4), term 4·V3.* The tool value is 6.65E-5 against
  the printed 6.6E-5. The printed α3 and q_v have only three digits.

The tests are in `fta_web/tests/test_ccf_alpha_published.py`.
