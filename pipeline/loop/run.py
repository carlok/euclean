"""The rediscovery loop: T0 -> C1 -> T1, with the comparison made explicit.

The question is not whether the enriched theory proves more — a definitional
extension cannot, and it would be a bug if it appeared to. The question is
whether having the concept available changes what the search *reaches* and how
compactly the results come out.

Both outcomes are reportable. If concept invention buys nothing measurable here,
that is the finding, and the metrics table is the evidence.

Usage:  python3 -m pipeline.loop.run --generations 6 --top 8
"""

import argparse
import json
import pathlib
import statistics
import time

from ..chainer import run as chainer_run
from ..concepts import invent
from ..kernel import formula as F, theory as theory_mod, verify
from ..concepts import run as concepts_run

ROOT = pathlib.Path(__file__).resolve().parents[2]


def metrics(records):
    if not records:
        return {"kept": 0}
    sizes = [r["proof_size"] for r in records]
    stmt_sizes = [F.size(r["statement_ast"]) for r in records]
    ef = [r for r in records if "∃" not in r["normalized_statement"]]
    return {
        "kept": len(records),
        "distinct_statements": len(set(r["normalized_statement"] for r in records)),
        "existential_free": len(ef),
        "mean_proof_size": round(statistics.mean(sizes), 2),
        "median_proof_size": statistics.median(sizes),
        "mean_statement_size": round(statistics.mean(stmt_sizes), 2),
        "total_statement_size": sum(stmt_sizes),
        "max_proof_depth": max(r["proof_depth"] for r in records),
    }


def bridge_statements(concepts):
    """Concept bridges as formulas the chainer can use as rules."""
    env, relations = {}, {}
    for c in concepts:
        params = c["params"]
        arity = len(params)
        relations[c["name"]] = arity
        head = F.Atom(c["name"], [F.Var(p) for p in params])
        parts = invent.conjuncts(c["body"])

        intro = head
        for p in reversed(parts):
            intro = F.Imp(p, intro)
        env[f"{c['name']}_intro"] = F.Forall(params, intro)

        for i, p in enumerate(parts):
            env[f"{c['name']}_elim{i}"] = F.Forall(params, F.Imp(head, p))
    return env, relations


class Augmented:
    """A theory plus the concept vocabulary, for the enriched pass."""

    def __init__(self, base, extra_relations):
        self.sort = base.sort
        self.seed = base.seed
        self.env = dict(base.env)
        self.axiom_names = list(base.axiom_names)
        self.relations = {**base.relations, **extra_relations}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=6)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--min-support", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--run-id", default="loop")
    args = ap.parse_args()

    T = theory_mod.load()
    out = ROOT / "runs" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    report = {"generations": args.generations, "stages": []}

    # --- T0
    print("T0: baseline corpus")
    t0 = time.time()
    rec0, items0, rej0, _ = chainer_run.build(T, seed=args.seed, generations=args.generations)
    fail0 = chainer_run.verify_corpus(items0, log=lambda *a: None)
    assert not fail0, "baseline corpus was rejected by the kernel"
    m0 = metrics(rec0)
    m0["seconds"] = round(time.time() - t0, 1)
    report["stages"].append({"stage": "T0", "metrics": m0, "rejected": rej0})
    print("   ", m0)

    # --- C1
    print("C1: concept invention over T0")
    scored, ranked = _concepts_from(rec0, out, args.min_support, args.top)
    path = concepts_run.write_lean(ranked)
    verify.lean_env()
    _, ok, log = verify.check_file(path)
    print(f"    {len(ranked)} concepts, kernel {'accepted' if ok else 'REJECTED'}")
    if not ok:
        print("\n".join(log.splitlines()[:12]))
        return
    report["concepts"] = [
        {"name": c["name"], "params": c["params"], "scores": c["scores"]} for c in ranked
    ]

    # --- T1
    print("T1: corpus over the enriched vocabulary")
    t1 = time.time()
    extra_env, extra_rel = bridge_statements(ranked)
    T1 = Augmented(T, extra_rel)
    T1.env.update(extra_env)
    rec1, items1, rej1, _ = chainer_run.build(
        T1, seed=args.seed, generations=args.generations
    )
    fail1 = chainer_run.verify_corpus_with(items1, ["Theory.Anonymous", "Theory.Concepts"])
    m1 = metrics(rec1)
    m1["seconds"] = round(time.time() - t1, 1)
    m1["kernel_failures"] = len(fail1)
    report["stages"].append({"stage": "T1", "metrics": m1, "rejected": rej1})
    print("   ", m1)

    report["delta"] = {
        k: (m1.get(k) - m0.get(k))
        for k in m0
        if isinstance(m0.get(k), (int, float)) and isinstance(m1.get(k), (int, float))
    }
    (out / "loop.json").write_text(json.dumps(report, indent=1, default=str) + "\n")
    print("\ndelta T1 - T0:")
    for k, v in report["delta"].items():
        print(f"   {k:24s} {v:+.2f}" if isinstance(v, float) else f"   {k:24s} {v:+d}")
    print(f"\nwrote {out}/loop.json")


def _concepts_from(records, out, min_support, top):
    """Concept proposal needs cluster labels; derive them on the fly for T0."""
    from ..cluster import methods
    from ..views import build as vbuild

    T = theory_mod.load()
    views = vbuild.build(records, T)
    ids, _, matrix = vbuild.numeric_matrix(views)
    assign = methods.kmeans(matrix, 28, seed=0)
    assignments = {i: {"kmeans_numeric": a} for i, a in zip(ids, assign)}

    by_id = {r["id"]: r for r in records}
    cands = invent.candidates(records, min_support=min_support)
    scored = [
        {
            "name": f"C{i:03d}",
            "params": c["params"],
            "body": c["body"],
            "theorems": c["theorems"],
            "scores": invent.score(c, by_id, assignments),
        }
        for i, c in enumerate(cands)
    ]
    ranked = invent.rank(scored, top=top)
    for i, c in enumerate(ranked):
        c["name"] = f"C{i:02d}"
    return scored, ranked


if __name__ == "__main__":
    main()
