"""Measure whether a candidate theory can be used as a control at all.

The previous attempt at a control skipped this and produced a theory poorer
than the one under test — one relation and five axioms against two and ten —
which cannot test whether the subject is too poor in either direction. Three
further blockers were only discovered afterwards, each fatal on its own.

So admissibility is measured rather than argued. The probe reports five
richness axes and three blocker checks for one theory, over a seed set, and
`verdict.py` compares a candidate against the incumbent using a rule fixed in
advance.

**This never calls Lean, and that is deliberate.** What is being measured is
what the search *reaches*, not what is true, so none of the single-theory
assumptions in `kernel/verify.py` apply and no multi-theory infrastructure is
needed — `theory.load(path)` already takes a path. Nothing the probe derives is
claimed or published; if a candidate is admitted, its corpus gets kernel-checked
in the build that follows, like everything else.

Usage:
  python3 -m pipeline.admissibility.probe --spec theory/spec.json --label incumbent
"""

import argparse
import json
import pathlib
import time
from collections import Counter

from ..canon import normalize as N
from ..chainer import run as chainer_run
from ..chainer.engine import Engine
from ..cluster import methods as cluster_methods
from ..concepts import invent
from ..kernel import theory as theory_mod
from ..patterns import motifs

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "admissibility"

# One budget for every theory. Comparing theories measured at different budgets
# would compare the budgets.
BUDGET = {
    "generations": 2,
    "rounds": 5,
    "derivations_per_rule_per_round": 90,
    "time_budget": 30,
}
CONTEXT = {"atom_layout": "fixed", "assume_distinct": True, "params": 8}
SEEDS = (0, 1, 2)
SUPPORT = 8


def axiom_liveness(theory, seed=0):
    """Which axioms actually do anything.

    Three states, and the distinction matters. An axiom may become a rule; it
    may be *deliberately seeded* — a bare existential is opened once at startup
    so its witnesses join the constant pool, which is intended; or it may be
    inert, stored as a fact that no premise will ever match, contributing
    nothing and saying nothing about it.

    Only the third is a defect, and it is invisible without this check: the
    symptom of an inert axiom is a slightly smaller corpus, which is
    indistinguishable from ordinary seed variance.
    """
    eng = Engine(theory, {**CONTEXT, **{k: v for k, v in BUDGET.items() if k != "generations"}},
                 seed=seed)
    rules = {r.name for r in eng.rules}
    eng.saturate()

    contributions = Counter()
    for fact in eng.facts.values():
        origin = fact.origin
        if ":" in origin:
            contributions[origin.split(":", 1)[1]] += 1

    seeded = {
        o.split(":", 1)[1]
        for f in eng.facts.values()
        for o in [f.origin]
        if o.startswith("seed:")
    }

    rows = []
    for name in theory.axiom_names:
        rows.append(
            {
                "axiom": name,
                "is_rule": name in rules,
                "deliberately_seeded": name in seeded,
                "derivations": contributions.get(name, 0),
                "inert": name not in rules and name not in seeded,
            }
        )
    return rows


def measure_once(theory, seed):
    """One seed: build a corpus at the fixed budget and read the axes off it."""
    records, _, rejected, _ = chainer_run.build(
        theory,
        seed=seed,
        generations=BUDGET["generations"],
        cfg={**CONTEXT, **{k: v for k, v in BUDGET.items() if k != "generations"}},
        log=lambda *a: None,
    )
    if not records:
        return {
            "distinct_statements": 0,
            "existential_free": 0,
            "existential_free_share": 0.0,
            "concept_candidates": 0,
            "distinct_motifs": 0,
            "clusters": 0,
            "kept": 0,
        }

    ef = [r for r in records if "∃" not in r["normalized_statement"]]

    cands = invent.candidates(records, min_support=SUPPORT, max_conjuncts=2)

    seen_motifs = set()
    for r in records:
        for m in set(motifs.applications(r["proof_ast"])):
            if any(not a.startswith("<") for a in m[1]):
                seen_motifs.add(m)

    dep_sets = [
        set(r["axiom_dependencies"]) | set(r["proof_dependencies"]) for r in records
    ]
    labels = cluster_methods.single_linkage(dep_sets, 0.34)

    return {
        "kept": len(records),
        "distinct_statements": len({N.key(r["statement_ast"]) for r in records}),
        "existential_free": len(ef),
        "existential_free_share": round(len(ef) / len(records), 4),
        "concept_candidates": len(cands),
        "distinct_motifs": len(seen_motifs),
        "clusters": len(set(labels)),
        "rejected": dict(rejected),
    }


AXES = (
    "distinct_statements",
    "existential_free",
    "concept_candidates",
    "distinct_motifs",
    "clusters",
)


def probe(theory, label, seeds=SEEDS, log=print):
    log(f"probing {label}: {len(theory.axiom_names)} axioms, relations {theory.relations}")

    t0 = time.time()
    per_seed = []
    for s in seeds:
        m = measure_once(theory, s)
        per_seed.append(m)
        log(f"  seed {s}: kept={m['kept']:5d} distinct={m['distinct_statements']:5d} "
            f"ef={m['existential_free']:4d} cands={m['concept_candidates']:4d} "
            f"motifs={m['distinct_motifs']:4d} clusters={m['clusters']:4d}")

    axes = {}
    for axis in AXES:
        vals = [m[axis] for m in per_seed]
        axes[axis] = {
            "values": vals,
            "min": min(vals),
            "max": max(vals),
            "mean": round(sum(vals) / len(vals), 2),
        }

    liveness = axiom_liveness(theory, seed=seeds[0])
    # Two different things, and running this on the incumbent is what forced
    # the distinction. `inert` means the axiom *cannot* contribute: it is
    # neither a rule nor deliberately seeded, so no premise will ever match it
    # and it says nothing however long the search runs. That is a structural
    # defect and it is what killed the previous candidate.
    #
    # Contributing nothing *at this budget* is not that. The incumbent has
    # three such axioms — they are perfectly good rules that this short budget
    # never triggers — and a rule that failed the incumbent would be the wrong
    # rule. It is reported as diagnostic context, never as a failure.
    inert = [r["axiom"] for r in liveness if r["inert"]]
    idle = [
        r["axiom"]
        for r in liveness
        if r["derivations"] == 0 and not r["deliberately_seeded"] and not r["inert"]
    ]

    ef_share = [m["existential_free_share"] for m in per_seed]

    report = {
        "label": label,
        "seeds": list(seeds),
        "budget": BUDGET,
        "context": CONTEXT,
        "relations": theory.relations,
        "axiom_count": len(theory.axiom_names),
        "axes": axes,
        "existential_free_share": {
            "min": min(ef_share),
            "max": max(ef_share),
            "mean": round(sum(ef_share) / len(ef_share), 4),
        },
        "axiom_liveness": liveness,
        "inert_axioms": inert,
        "idle_at_this_budget": idle,
        "seconds": round(time.time() - t0, 1),
    }

    log(f"  inert axioms: {inert or 'none'}")
    log(f"  idle at this budget (not a defect): {idle or 'none'}")
    log(f"  existential-free share: {report['existential_free_share']}")
    log(f"  {report['seconds']}s")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=str(ROOT / "theory" / "spec.json"))
    ap.add_argument("--label", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    args = ap.parse_args()

    T = theory_mod.load(args.spec)
    report = probe(T, args.label, seeds=tuple(args.seeds))

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"probe-{args.label}.json"
    path.write_text(json.dumps(report, indent=1) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
