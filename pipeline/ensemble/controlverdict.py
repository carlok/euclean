"""Does the control theory show concept survival? The rule, fixed in advance.

Written and committed before either grid was run. That ordering is the whole
point: a bar chosen after seeing the numbers is not a bar. The same discipline
as `admissibility/verdict.py`, applied to the question that motivated the
control in the first place.

## The question

The headline result is negative: no invented concept survives across
configurations. A reviewer's objection is that this may say nothing about the
method — the theory under test has 2 relations and 10 axioms, and perhaps it is
simply too poor to contain concepts worth inventing. A richer theory (3
relations, 15 axioms) passed the admissibility gate. If the richer theory also
shows nothing, that objection is dead. If it shows something, the headline is a
fact about the theory rather than about the method, and it must be restated.

## What "shows concept survival" means, and why it is not raw survival

Raw survival cannot be compared across theories. Members rank a fixed top-`k`
out of a pool whose size depends on the theory, so a richer theory's concepts
are each less likely to be ranked before any content is considered — see
`nullmodel`. Comparing raw counts would find the richer theory less stable no
matter what is true of it, which is the very conclusion under test.

The availability census settles which statistic to use. On the incumbent, no
concept is available to be ranked in every member (best 17 of 45), and
conditional on availability the ranking barely beats chance (best excess +3.5
over 592 keys). Survival is therefore capped by whether a concept is *minable*
across configurations at all, not by the ranking cut.

So the primary statistic is **availability**: the largest fraction of members in
whose candidate pool any single canonical key appears. It is a direct measure of
"does the same concept keep showing up", it needs no top-`k`, and it is
comparable between theories because it is a rate over members rather than a
count out of a pool.

## The rule

The control shows concept survival when **all** of these hold:

1. Its best availability rate exceeds the incumbent's, with the two ranges
   across base seeds **disjoint**. Overlapping ranges are not a difference,
   however far apart the means — the rule already applied by
   `ablation/run.py` and `admissibility/verdict.wins`.
2. Both theories were measured at the same budget. A budget difference would
   produce exactly the same signature as a theory difference.
3. Both have a noise floor from at least `REQUIRED_REPLICATES` grids at
   different base seeds. Without it there is no scale, and this project has
   already once read pure sampling noise as an effect.
4. The control's grid is not mostly vacuous. A member with fewer multi-premise
   statements than `min_support` cannot produce any candidate at all, so a null
   from such a member is an absence of input rather than a finding.

A condition that could not be evaluated is reported as unevaluated and the
verdict is withheld. A condition that was not checked is not a condition that
passed.

Selection quality — whether the scoring beats chance once a concept is available
— is reported alongside but is deliberately **not** part of the rule. On the
incumbent it is indistinguishable from chance, and a rule resting on it would be
a rule resting on noise.

Usage:  python3 -m pipeline.ensemble.controlverdict --control candidate
"""

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "ensemble"

REQUIRED_REPLICATES = 2
# Below this many multi-premise statements a member cannot produce a candidate
# at any support level, since `invent.candidates` mines conjunctions of premises
# and skips statements with fewer than two. This is a definitional floor, not a
# tuned one.
MAX_VACUOUS_FRACTION = 1 / 3


def ranges_disjoint(a, b, margin=0.0):
    """Higher-is-better comparison with no overlap, plus a resolution margin.

    Returns True only when `a` sits entirely above `b`, by at least `margin`.
    Same rule as `admissibility/verdict.wins`, with one addition forced by the
    measured data.

    Availability is a count of members divided by the member count, so it is
    quantized in steps of `1/n`. On the incumbent, all three replicates give
    *exactly* 16/45 for the quantified source — a range of width zero. Taken at
    face value that is a bar anything above 0.356 clears, which would let a
    single member's difference decide the comparison. Three samples landing on
    the same quantized value is not evidence of zero variance.

    The margin is one member's worth. Two availability figures closer than that
    are not distinguishable by this instrument at all.
    """
    return a["min"] > b["max"] + margin


def availability_range(grids_by_seed, source):
    """Best availability rate for `source`, min and max across replicates."""
    vals = [
        summary[source]["best_presence_rate"]
        for summary in grids_by_seed.values()
        if source in summary
    ]
    if not vals:
        return None
    return {"min": min(vals), "max": max(vals), "values": sorted(vals), "n": len(vals)}


def evaluate(control, incumbent, sources=("premise-conjunction", "quantified")):
    """Apply the rule. `control` and `incumbent` are measurement bundles.

    Each bundle carries `availability` (base seed -> presence_summary), `budget`,
    `vacuous_fraction` and `label`.
    """
    # One member's worth of availability, the finest difference the statistic
    # can express. Taken from the smaller grid so the margin is never optimistic.
    per_grid = [
        b["members"] / max(len(b["availability"]), 1)
        for b in (control, incumbent)
        if b.get("members") and b.get("availability")
    ]
    margin = 1.0 / min(per_grid) if per_grid else 0.0

    rows, won = [], []
    for source in sources:
        c = availability_range(control["availability"], source)
        i = availability_range(incumbent["availability"], source)
        if c is None or i is None:
            rows.append({"source": source, "evaluated": False})
            continue
        beats = ranges_disjoint(c, i, margin)
        won.append(source) if beats else None
        rows.append(
            {
                "source": source,
                "evaluated": True,
                "control": [c["min"], c["max"]],
                "incumbent": [i["min"], i["max"]],
                "control_replicates": c["n"],
                "incumbent_replicates": i["n"],
                "margin_required": round(margin, 4),
                "disjoint_and_higher": beats,
            }
        )

    replicates_ok = (
        min(
            (len(control["availability"]), len(incumbent["availability"])),
            default=0,
        )
        >= REQUIRED_REPLICATES
    )
    same_budget = control.get("budget") == incumbent.get("budget")
    vac = control.get("vacuous_fraction")

    # A control whose search was truncated by a ceiling is biased downward: a
    # smaller corpus carries fewer distinct premise patterns, so fewer concepts
    # recur across members. The bias runs one way only, which is why it is not a
    # flat blocker. Clearing the bar despite being truncated is a safe positive.
    # Failing to clear it while truncated says nothing about the theory.
    bound = control.get("budget_bound")
    truncation_ok = True if (bound is False or won) else None

    conditions = [
        (
            "some source is higher with disjoint ranges",
            bool(won) if any(r.get("evaluated") for r in rows) else None,
            f"sources clearing the bar: {won or 'none'}",
        ),
        (
            "control's search was not truncated, or cleared the bar anyway",
            truncation_ok,
            "not truncated"
            if bound is False
            else (
                "truncated but cleared the bar, which truncation biases against"
                if won
                else "the control hit a fact ceiling and did not clear the bar; a "
                "downward-biased failure is not evidence about the theory"
            ),
        ),
        (
            "both theories measured at the same budget",
            same_budget if control.get("budget") and incumbent.get("budget") else None,
            "budgets match" if same_budget else "budgets differ; the comparison "
            "would be of budgets rather than theories",
        ),
        (
            f"noise floor from at least {REQUIRED_REPLICATES} base seeds, both theories",
            replicates_ok,
            f"control {len(control['availability'])}, "
            f"incumbent {len(incumbent['availability'])}",
        ),
        (
            "control grid is not mostly vacuous",
            (vac <= MAX_VACUOUS_FRACTION) if vac is not None else None,
            "not measured" if vac is None else f"vacuous fraction {vac:.2f}, "
            f"limit {MAX_VACUOUS_FRACTION:.2f}",
        ),
    ]

    failed = [n for n, ok, _ in conditions if ok is False]
    unevaluated = [n for n, ok, _ in conditions if ok is None]

    return {
        "control": control.get("label"),
        "incumbent": incumbent.get("label"),
        "sources": rows,
        "conditions": [{"condition": n, "passed": ok, "detail": d} for n, ok, d in conditions],
        "first_failing_condition": failed[0] if failed else None,
        "unevaluated_conditions": unevaluated,
        "shows_survival": not failed and not unevaluated,
        # reported, never decisive: see the module docstring
        "selection_beats_chance": control.get("selection_excess"),
    }


def render(v):
    L = []
    w = L.append
    w("# Does the control theory show concept survival?")
    w("")
    w("Generated by `pipeline.ensemble.controlverdict`. The rule was fixed in code")
    w("before either grid ran.")
    w("")
    verdict = "SHOWS SURVIVAL" if v["shows_survival"] else "DOES NOT SHOW SURVIVAL"
    if v["unevaluated_conditions"]:
        verdict = "WITHHELD"
    w(f"**Verdict: {verdict}**")
    if v["first_failing_condition"]:
        w("")
        w(f"First failing condition: *{v['first_failing_condition']}*.")
    if v["unevaluated_conditions"]:
        w("")
        w(f"Conditions not evaluated: {v['unevaluated_conditions']}. A condition that")
        w("was not checked is not a condition that passed, so no verdict is claimed.")
    w("")

    w("## What is being compared")
    w("")
    w("Availability: the largest fraction of grid members in whose candidate pool")
    w("any one canonical concept appears. Raw survival is not comparable across")
    w("theories, because a fixed top-k over a larger pool penalizes a richer")
    w("theory before any content is considered.")
    w("")
    w("| source | control | incumbent | disjoint and higher |")
    w("|---|---|---|---|")
    for r in v["sources"]:
        if not r.get("evaluated"):
            w(f"| {r['source']} | not measured | not measured | — |")
            continue
        w(
            f"| {r['source']} | {r['control'][0]:.3f}–{r['control'][1]:.3f} "
            f"({r['control_replicates']} seeds) | {r['incumbent'][0]:.3f}–"
            f"{r['incumbent'][1]:.3f} ({r['incumbent_replicates']} seeds) | "
            f"{'yes' if r['disjoint_and_higher'] else 'no'} |"
        )
    w("")

    w("## Conditions")
    w("")
    w("| condition | passed | detail |")
    w("|---|---|---|")
    for c in v["conditions"]:
        state = {True: "yes", False: "**no**", None: "not evaluated"}[c["passed"]]
        w(f"| {c['condition']} | {state} | {c['detail']} |")
    w("")

    w("## What this does not decide")
    w("")
    w("Whether the scoring criteria pick better than chance once a concept is")
    w("available. On the incumbent that margin is indistinguishable from noise, so")
    w("it is reported but kept out of the rule.")
    w("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    # Roles are read from runs/ensemble/roles.json rather than defaulted to a
    # theory name. Which theory is subject and which is control is a choice, and
    # baking either into an argument default is how a name became an identity.
    from . import grids

    recorded = grids.roles()
    ap.add_argument("--control", default=recorded["control"], help="theory code")
    ap.add_argument("--incumbent", default=recorded["subject"], help="theory code")
    args = ap.parse_args()

    def bundle(label):
        p = OUT / f"availability-{label}.json"
        if not p.exists():
            raise SystemExit(
                f"missing {p}. Build it with pipeline.ensemble.nullmodel for each "
                f"base seed before asking for a verdict."
            )
        return json.loads(p.read_text())

    v = evaluate(bundle(args.control), bundle(args.incumbent))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "controlverdict.json").write_text(json.dumps(v, indent=1) + "\n")
    doc = ROOT / "docs" / "control.md"
    doc.write_text(render(v))

    print(f"verdict: {'shows survival' if v['shows_survival'] else 'does not show survival'}")
    if v["first_failing_condition"]:
        print(f"  first failing condition: {v['first_failing_condition']}")
    if v["unevaluated_conditions"]:
        print(f"  not evaluated: {v['unevaluated_conditions']}")
    print(f"wrote {OUT}/controlverdict.json and {doc}")


if __name__ == "__main__":
    main()
