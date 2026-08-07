"""Which axioms a theorem actually rests on, transitively.

`axiom_dependencies` on a record lists only what its own proof term cites
directly. That number is nearly useless on its own: the median is one or two,
and the fifty most structurally important theorems average 0.8, because most of
a proof's weight sits in the promoted lemmas it calls rather than in axioms it
names. A theorem citing one axiom and five lemmas rests on everything those
lemmas needed.

The transitive closure is the reverse-mathematics quantity — the set of axioms
the whole proof tree bottoms out in — and it is free, since the corpus already
carries an exact DAG. No search, no kernel.

Usage:  python3 -m pipeline.reverse.footprint --run main
"""

import argparse
import json
import pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]


def footprints(records, axiom_names):
    """id -> the set of axioms its whole proof tree rests on.

    Records are processed in dependency order and memoized. A lemma cited but
    absent from the corpus would silently contribute nothing, so those are
    counted and returned rather than ignored: a closure that under-reports makes
    every footprint look smaller and every result look better than it is.
    """
    by_id = {r["id"]: r for r in records}
    axioms = set(axiom_names)
    memo = {}
    missing = Counter()

    def resolve(rid, stack):
        if rid in memo:
            return memo[rid]
        if rid in stack:
            # the corpus DAG is acyclic by construction (generation g may only
            # cite g-1 and earlier); treat a cycle as a bug, not as empty
            raise ValueError(f"dependency cycle through {rid}")
        rec = by_id.get(rid)
        if rec is None:
            missing[rid] += 1
            return set()

        stack.add(rid)
        out = set(a for a in rec["axiom_dependencies"] if a in axioms)
        for dep in rec["proof_dependencies"]:
            if dep in axioms:
                out.add(dep)
            else:
                out |= resolve(dep, stack)
        stack.discard(rid)

        memo[rid] = out
        return out

    result = {}
    for r in sorted(records, key=lambda r: r["generation"]):
        result[r["id"]] = sorted(resolve(r["id"], set()))
    return result, dict(missing)


def summarize(records, foot):
    direct = Counter(len(r["axiom_dependencies"]) for r in records)
    trans = Counter(len(foot[r["id"]]) for r in records)
    grew = sum(1 for r in records if len(foot[r["id"]]) > len(r["axiom_dependencies"]))
    return {
        "theorems": len(records),
        "direct_distribution": {str(k): v for k, v in sorted(direct.items())},
        "transitive_distribution": {str(k): v for k, v in sorted(trans.items())},
        "mean_direct": round(
            sum(len(r["axiom_dependencies"]) for r in records) / len(records), 2
        ),
        "mean_transitive": round(sum(len(foot[r["id"]]) for r in records) / len(records), 2),
        "theorems_whose_footprint_grew": grew,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    args = ap.parse_args()

    from ..kernel import theory as theory_mod

    run_dir = ROOT / "runs" / args.run
    records = json.loads((run_dir / "corpus.json").read_text())
    T = theory_mod.load()

    foot, missing = footprints(records, T.axiom_names)
    stats = summarize(records, foot)

    out = run_dir / "footprints.json"
    out.write_text(
        json.dumps(
            {
                "summary": stats,
                "missing_dependencies": missing,
                "footprints": foot,
            },
            indent=1,
        )
        + "\n"
    )

    print(f"{stats['theorems']} theorems")
    print(f"  axioms cited directly:    mean {stats['mean_direct']}")
    print(f"  axioms rested on overall: mean {stats['mean_transitive']}")
    print(f"  footprint grew for {stats['theorems_whose_footprint_grew']} of them")
    print(f"  transitive size distribution: {stats['transitive_distribution']}")
    if missing:
        print(f"  WARNING: {len(missing)} cited dependencies absent from the corpus")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
