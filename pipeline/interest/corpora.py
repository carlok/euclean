"""Build and kernel-check the audit's corpora.

One corpus per (theory, identifier permutation, base seed), each built exactly
as the reference run is built, `python -m pipeline.chainer.run --seed S
--generations 10`, but from an explicit spec file and checked in a private Lean
package (`interest.lean`), so that `theory/`, `generated/` and `metadata/` are
never written.

The analysis chain that euclean's importance score needs is then run the way
`ensemble/run.py` runs it, with `report.importance.score` called directly:
`report.importance.main` would also rewrite `runs/ensemble/importance.json`.

The run id is built from the theory code the pre-registration assigns, never
from the spec's own `theory` field: the stored permutation-0 control spec
predates the code migration and still carries a role label there.

Usage:
  python -m pipeline.interest.corpora --theory CODE --perm P --seed S
"""

import argparse
import hashlib
import json
import time

from ..chainer import run as chainer_run
from ..cluster import run as cluster_run
from ..kernel import theory as theory_mod
from ..kernel.theory import ROOT
from ..report import importance as importance_mod
from ..views import build as views_build
from .lean import Package

GENERATIONS = 10
CLUSTER_K = 28  # cluster.run's default, which the reference run used


def run_id(code, perm, seed):
    return f"interest-{code}-p{perm}-s{seed}"


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clock_watching(engine_cls, hits):
    """The engine, observed: after each saturation, was the clock past its deadline?

    The engine's own trace records a time-budget stop only when one lands at the
    start of a round; a stop inside a round, or in the last round, leaves no
    mark. Watching the deadline directly closes that gap. Nothing the engine
    does changes.
    """

    class ClockWatched(engine_cls):
        def saturate(self, rounds=None):
            trace = super().saturate(rounds)
            hits.append(bool(self._past_deadline()))
            return trace

    return ClockWatched


def build_one(code, perm, seed, generations=GENERATIONS, log=print, out_id=None):
    """`out_id` writes the corpus to another run directory: used only for the
    duplicate build that measures reproducibility, never for an analysed corpus."""
    from . import plan

    spec_path = ROOT / plan.SPECS[(code, perm)]
    spec = json.loads(spec_path.read_text())
    T = theory_mod.Theory(spec)
    rid = out_id or run_id(code, perm, seed)
    out = ROOT / "runs" / rid
    out.mkdir(parents=True, exist_ok=True)
    log(f"{rid}: {T}")

    stamps = []

    def stamp(msg):
        stamps.append({"t": round(time.time() - t0, 1), "msg": msg})
        log(f"  [{stamps[-1]['t']:7.1f}s] {msg}")

    clock_hits = []
    engine_cls = chainer_run.Engine
    chainer_run.Engine = _clock_watching(engine_cls, clock_hits)
    t0 = time.time()
    try:
        records, items_by_gen, rejected, traces = chainer_run.build(
            T, seed=seed, generations=generations, log=stamp
        )
    finally:
        chainer_run.Engine = engine_cls
    t_gen = time.time() - t0
    stamp(f"generated {len(records)} candidates")

    t1 = time.time()
    pkg = Package(out / "interest" / "lean", spec).create()
    failures, modules = pkg.verify_corpus(items_by_gen, log=log)
    t_ver = time.time() - t1
    if failures:
        stem, lg = failures[0]
        raise SystemExit(f"KERNEL REJECTED {len(failures)} batch(es), first {stem}:\n{lg[:1500]}")
    for r in records:
        r["verification"] = True
    stamp(f"kernel-checked {len(modules)} batches")

    (out / "corpus.json").write_text(json.dumps(records) + "\n")

    t2 = time.time()
    views = views_build.build(records, T)
    ids, keys, matrix = views_build.numeric_matrix(views)
    (out / "views.json").write_text(json.dumps(views_build.serializable(views)) + "\n")
    (out / "vectors.json").write_text(json.dumps({"ids": ids, "keys": keys, "matrix": matrix}) + "\n")
    report, assignments = cluster_run.run(out, k=CLUSTER_K)
    (out / "clusters.json").write_text(json.dumps(report, indent=1) + "\n")
    (out / "assignments.json").write_text(json.dumps(assignments) + "\n")
    views_loaded = json.loads((out / "views.json").read_text())
    ranked = importance_mod.score(records, views_loaded, assignments)
    (out / "importance.json").write_text(json.dumps(ranked, indent=1) + "\n")
    t_an = time.time() - t2
    stamp("analysis chain written")

    summary = {
        "run": rid,
        "theory": code,
        "spec_theory_field": spec.get("theory"),
        "perm": perm,
        "spec_path": str(spec_path.relative_to(ROOT)),
        "spec_sha256": file_sha256(spec_path),
        "spec_hash": T.spec_hash,
        "theory_seed": T.seed,
        "chainer_seed": seed,
        "generations": generations,
        "kept": len(records),
        "rejected": rejected,
        "traces": traces,
        "time_budget_stops": sum(
            1 for tr in traces for rd in tr["rounds"] if rd.get("stopped") == "time-budget"
        ),
        "trace_clock_stop_generations": sorted(
            {tr["generation"] for tr in traces for rd in tr["rounds"] if rd.get("stopped") == "time-budget"}
        ),
        "clock_past_deadline_generations": [g for g, hit in enumerate(clock_hits) if hit],
        "lean": pkg.version(),
        "lean_modules": modules,
        "seconds_generate": round(t_gen, 2),
        "seconds_verify": round(t_ver, 2),
        "seconds_analysis": round(t_an, 2),
        "stamps": stamps,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    log(f"wrote {out}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theory", required=True, help="theory code, as in runs/ensemble/roles.json")
    ap.add_argument("--perm", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--generations", type=int, default=GENERATIONS)
    ap.add_argument("--out-id", default=None,
                    help="write to runs/<OUT_ID> instead; only for the reproducibility duplicate")
    args = ap.parse_args()
    build_one(args.theory, args.perm, args.seed, args.generations, out_id=args.out_id)


if __name__ == "__main__":
    main()
