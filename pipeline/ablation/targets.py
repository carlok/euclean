"""Build and freeze the held-out target set.

The criterion this supports is "does having this concept let the search reach
things it otherwise could not". Raw theorem yield cannot answer that: this
generator emits large volumes of weak existential statements, so yield rises
when the search gets *worse*. A set of targets committed to in advance cannot be
gamed that way.

Two design choices are worth defending.

**Targets are selected on intrinsic properties, never on whether the baseline
reached them.** Selecting by baseline outcome would fix the baseline rate by
construction and make the calibration meaningless. Instead targets are chosen
for being existential-free, structurally important, and first reached late, and
the *budget* is then tuned until the baseline lands in the calibration band.
Tuning the budget leaves the target set independent of it.

**Calibration is a gate, not a diagnostic.** If the baseline reaches every
target or none, no concept can move the number, and every ablation result will
be a column of zeros that looks like a finding. That has to be caught when the
set is built.

Usage:  python3 -m pipeline.ablation.targets --build
"""

import argparse
import json
import pathlib

from ..canon import relations as R
from ..chainer import run as chainer_run
from ..kernel import emit, theory as theory_mod

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "targets"

BAND = (0.20, 0.60)

# The seed context targets are defined against. Ablation runs must use the same
# one, or the targets are not reachable in principle and the measurement is of
# the context rather than the concept.
CONTEXT = {"atom_layout": "fixed", "assume_distinct": True, "params": 8}

BUDGETS = [
    {"generations": 1, "rounds": 3, "derivations_per_rule_per_round": 40},
    {"generations": 1, "rounds": 4, "derivations_per_rule_per_round": 60},
    {"generations": 2, "rounds": 4, "derivations_per_rule_per_round": 60},
    {"generations": 2, "rounds": 5, "derivations_per_rule_per_round": 90},
    {"generations": 3, "rounds": 5, "derivations_per_rule_per_round": 120},
]


def select(records, views, importance, count=80):
    """Existential-free and structurally important, stratified by difficulty.

    An earlier version took the latest generations first, on the reasoning that
    late-reached statements are the hard ones. They are — too hard. Every target
    then needed the full promotion chain of a ten-generation run, no short budget
    came within reach of any of them, and calibration failed at 0-6%.

    A target set has to straddle the budget it will be measured at: some targets
    the baseline reaches, some it does not, so a concept has room to move the
    number in either direction. Sampling evenly across generations gives that
    spread without ever consulting what the baseline actually reached.
    """
    rank = {item["id"]: i for i, item in enumerate(importance)}
    pool = [r for r in records if "∃" not in r["normalized_statement"] and r["id"] in rank]

    by_gen = {}
    for r in pool:
        by_gen.setdefault(r["generation"], []).append(r)
    for g in by_gen:
        by_gen[g].sort(key=lambda r: rank[r["id"]])

    out, gens = [], sorted(by_gen)
    i = 0
    while len(out) < count and gens:
        g = gens[i % len(gens)]
        if by_gen[g]:
            out.append(by_gen[g].pop(0))
        else:
            gens.remove(g)
            continue
        i += 1
    return out


def reachable(theory, budget, seed=0, extra_env=None, relmap=None):
    """Canonical keys of everything a run at this budget proves."""
    cfg = {**CONTEXT, **{k: v for k, v in budget.items() if k != "generations"}}
    records, _, _, _ = chainer_run.build(
        theory,
        seed=seed,
        generations=budget["generations"],
        cfg=cfg,
        extra_env=extra_env,
        log=lambda *a: None,
    )
    relmap = relmap or R.canonical_map(theory)
    return {repr(R.key(r["statement_ast"], relmap)) for r in records}, len(records)


def calibrate(theory, target_keys, seed=0, log=print):
    """Find a budget where the baseline reaches a workable share of targets."""
    relmap = R.canonical_map(theory)
    trace = []
    for budget in BUDGETS:
        reached, kept = reachable(theory, budget, seed=seed, relmap=relmap)
        hits = len(target_keys & reached)
        rate = hits / max(len(target_keys), 1)
        trace.append({"budget": budget, "kept": kept, "hits": hits, "rate": round(rate, 3)})
        log(f"  budget {budget} -> {hits}/{len(target_keys)} targets ({rate:.0%}), {kept} kept")
        if BAND[0] <= rate <= BAND[1]:
            return budget, reached, trace
    return None, set(), trace


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--count", type=int, default=80)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()

    run_dir = ROOT / "runs" / args.run
    records = json.loads((run_dir / "corpus.json").read_text())
    views = json.loads((run_dir / "views.json").read_text())
    importance = json.loads((run_dir / "importance.json").read_text())
    T = theory_mod.load()
    relmap = R.canonical_map(T)

    chosen = select(records, views, importance, args.count)
    keys = {repr(R.key(r["statement_ast"], relmap)) for r in chosen}
    print(f"selected {len(chosen)} candidate targets ({len(keys)} distinct canonical keys)")

    budget, reached, trace = calibrate(T, keys, seed=args.seed)
    if budget is None:
        print(
            f"CALIBRATION FAILED: no budget puts the baseline inside "
            f"{BAND[0]:.0%}-{BAND[1]:.0%}. The target set measures nothing as it "
            f"stands and must not be used for scoring."
        )
    else:
        print(f"calibrated: {budget}, baseline reaches {len(keys & reached)}/{len(keys)}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "targets.json").write_text(
        json.dumps(
            {
                "source_run": args.run,
                "seed": args.seed,
                "context": CONTEXT,
                "band": BAND,
                "calibrated": budget is not None,
                "budget": budget,
                "calibration_trace": trace,
                "baseline_reached": sorted(keys & reached),
                "targets": [
                    {
                        "id": r["id"],
                        "canonical_key": repr(R.key(r["statement_ast"], relmap)),
                        "statement": emit.formula(r["statement_ast"], top=True),
                        "generation": r["generation"],
                        "proof_size": r["proof_size"],
                    }
                    for r in chosen
                ],
            },
            indent=1,
        )
        + "\n"
    )
    print(f"wrote {OUT}/targets.json")
    if budget is None:
        # A broken measurement and a genuine null result must not look alike to
        # a shell chain. The artifact is still written, so the failure can be
        # inspected, but the exit status says the run is unusable.
        raise SystemExit(2)


if __name__ == "__main__":
    main()
