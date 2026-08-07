"""How few axioms suffice to reach a statement.

Greedy: start from the transitive footprint, drop one axiom at a time, and keep
the drop if the statement is still reached with the rule set restricted to the
remainder. Reuses `ablation.targets.reachable` against a theory whose `env` has
been cut down, so the search machinery needs no changes at all.

**Sufficiency and necessity are not symmetric here, and the asymmetry is the
whole reason this module is careful.** That a subset suffices is checkable: the
search derives the statement from it, and `reverse.verify` then has Lean confirm
a proof citing nothing outside it. That no smaller subset works is *not*
checkable by this pipeline. Failing to reach a statement inside a bounded search
establishes nothing — the same semi-decision that makes conjecture yield
unreadable — and establishing it properly would need counter-models, which this
project has no machinery for and which the axiom set makes awkward anyway, since
segment construction forces every model to be infinite.

So the output is *a sufficient subset, verified* and *no smaller subset was
reached, not established*. The word "minimal" is not used unqualified anywhere
in this module or its report, and that is deliberate.

Usage:  python3 -m pipeline.reverse.minimise --run main --top 50
"""

import argparse
import json
import pathlib
import time

from ..ablation import targets as targets_mod
from ..canon import relations as R
from ..kernel import theory as theory_mod

ROOT = pathlib.Path(__file__).resolve().parents[2]

BUDGET = {"generations": 2, "rounds": 5, "derivations_per_rule_per_round": 90}
SEEDS = (0, 1, 2)


class Restricted:
    """The theory with its axiom set cut down to `keep`."""

    def __init__(self, base, keep):
        self.sort = base.sort
        self.seed = base.seed
        self.relations = dict(base.relations)
        self.axiom_names = [n for n in base.axiom_names if n in keep]
        self.env = {n: s for n, s in base.env.items() if n in keep}


def reaches(base, keep, target_key, seeds=SEEDS, relmap=None):
    """Is the target derived from this axiom subset, under any seed?

    Any seed, not every seed: the question is whether the subset *can* produce
    it, and a subset that works under one trajectory is sufficient. Requiring
    all seeds would make the answer a fact about sampling.
    """
    th = Restricted(base, keep)
    if not th.env:
        return False
    for s in seeds:
        try:
            reached, _ = targets_mod.reachable(th, BUDGET, seed=s, relmap=relmap)
        except Exception:
            continue
        if target_key in reached:
            return True
    return False


def minimise_one(base, footprint, target_key, seeds=SEEDS, relmap=None, log=None):
    """Greedily drop axioms that are not needed to reach the target."""
    keep = set(footprint)
    if not reaches(base, keep, target_key, seeds, relmap):
        # the full footprint does not reproduce it at this budget; nothing can
        # be concluded about subsets of it
        return {"status": "not-reproduced", "sufficient": None, "tested": 0}

    tested = 0
    # largest-first: dropping a heavily used axiom early prunes more
    for axiom in sorted(footprint):
        candidate = keep - {axiom}
        if not candidate:
            continue
        tested += 1
        if reaches(base, candidate, target_key, seeds, relmap):
            keep = candidate
            if log:
                log(f"      dropped {axiom} -> {sorted(keep)}")
    return {
        "status": "ok",
        "sufficient": sorted(keep),
        "dropped": sorted(set(footprint) - keep),
        "tested": tested,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    args = ap.parse_args()

    run_dir = ROOT / "runs" / args.run
    records = json.loads((run_dir / "corpus.json").read_text())
    foot = json.loads((run_dir / "footprints.json").read_text())["footprints"]
    by_id = {r["id"]: r for r in records}
    T = theory_mod.load()
    relmap = R.canonical_map(T)

    # rank by the ensemble-aggregated importance where available, since a
    # single run's ordering is one sample
    agg_path = ROOT / "runs" / "ensemble" / "importance.json"
    order = []
    if agg_path.exists():
        agg = json.loads(agg_path.read_text())
        keys = {repr(R.key(r["statement_ast"], relmap)): r["id"] for r in records}
        for item in agg:
            rid = keys.get(item["canonical_key"])
            if rid and rid not in order:
                order.append(rid)
    if not order:
        imp = json.loads((run_dir / "importance.json").read_text())
        order = [i["id"] for i in imp if i["id"] in by_id]

    targets = [t for t in order if len(foot.get(t, [])) > 1][: args.top]
    print(f"minimising {len(targets)} targets at budget {BUDGET}, seeds {args.seeds}")

    t0 = time.time()
    rows = []
    for i, rid in enumerate(targets, 1):
        rec = by_id[rid]
        key = repr(R.key(rec["statement_ast"], relmap))
        res = minimise_one(T, foot[rid], key, tuple(args.seeds), relmap)
        rows.append(
            {
                "id": rid,
                "statement": rec["normalized_statement"],
                "canonical_key": key,
                "footprint": foot[rid],
                **res,
            }
        )
        suff = res["sufficient"]
        print(f"  [{i:3d}/{len(targets)}] {rid:10s} footprint {len(foot[rid])} -> "
              f"{len(suff) if suff else '-'}  {res['status']}")

    ok = [r for r in rows if r["status"] == "ok"]
    reductions = [len(r["footprint"]) - len(r["sufficient"]) for r in ok]
    report = {
        "budget": BUDGET,
        "seeds": args.seeds,
        "targets": len(targets),
        "reproduced": len(ok),
        "not_reproduced": len(rows) - len(ok),
        "mean_footprint": round(sum(len(r["footprint"]) for r in ok) / len(ok), 2) if ok else 0,
        "mean_sufficient": round(sum(len(r["sufficient"]) for r in ok) / len(ok), 2) if ok else 0,
        "max_reduction": max(reductions) if reductions else 0,
        "caveat": (
            "Sufficiency is checkable and is verified separately by "
            "reverse.verify. Necessity is not: failing to reach a statement "
            "inside a bounded search establishes nothing, and this pipeline has "
            "no counter-model machinery. Do not read these as minimal sets."
        ),
        "results": rows,
        "seconds": round(time.time() - t0, 1),
    }
    out = run_dir / "minimisation.json"
    out.write_text(json.dumps(report, indent=1) + "\n")

    print(f"\n{report['reproduced']}/{report['targets']} reproduced from their footprint")
    print(f"  mean footprint {report['mean_footprint']} -> sufficient {report['mean_sufficient']}")
    print(f"  largest reduction: {report['max_reduction']} axioms")
    print(f"  {report['seconds']}s")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
