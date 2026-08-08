"""Run the configuration grid against whatever theory is currently in place.

Each member is built, kernel-verified, and analyzed the same way the single
sprint-1 run was, then stored under `runs/ens/<id>/`. Members run sequentially
because they all write batch modules into the same Lean package; the kernel
check is a few seconds each, so this costs little and avoids a whole class of
collision bug.

Usage:  python3 -m pipeline.ensemble.run --generations 3
"""

import argparse
import json
import pathlib
import time

from ..canon import relations as R
from ..chainer import run as chainer_run
from ..cluster import run as cluster_run
from ..concepts import invent, quantified, roles
from ..canon import normalize as N
from ..kernel import emit, theory as theory_mod
from ..report import importance as importance_mod
from ..views import build as views_build
from . import config as cfg_mod

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENS = ROOT / "runs" / "ens"


def slim_record(r):
    """Everything the stability analysis needs, without the proof terms.

    Full corpora across the grid run to hundreds of megabytes and the proof term
    is only needed to re-verify, which already happened before this is written.
    """
    return {k: v for k, v in r.items() if k != "proof_ast"}


def run_one(entry, theory, generations, min_support, top, log=print):
    out = ENS / entry["id"]
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    records, items, rejected, traces = chainer_run.build(
        theory,
        seed=entry["chainer_seed"],
        generations=generations,
        cfg=entry["config"],
        promote_max=cfg_mod.PROMOTE_MAX,
        log=lambda *a: None,
    )
    failures = chainer_run.verify_corpus(items, log=lambda *a: None)
    if failures:
        log(f"  {entry['id']}: KERNEL REJECTED {len(failures)} batch(es)")
        return None
    for r in records:
        r["verification"] = True

    (out / "corpus.json").write_text(json.dumps([slim_record(r) for r in records]) + "\n")

    views = views_build.build(records, theory)
    ids, keys, matrix = views_build.numeric_matrix(views)
    (out / "views.json").write_text(json.dumps(views_build.serializable(views)) + "\n")
    (out / "vectors.json").write_text(
        json.dumps({"ids": ids, "keys": keys, "matrix": matrix}) + "\n"
    )

    report, assignments = cluster_run.run(
        out,
        k=min(28, max(2, len(records) // 20)),
        only=cfg_mod.CLUSTER_METHODS,
    )
    (out / "clusters.json").write_text(json.dumps(report, indent=1) + "\n")
    (out / "assignments.json").write_text(json.dumps(assignments) + "\n")

    by_id = {r["id"]: r for r in records}
    cands = invent.candidates(records, min_support=min_support, max_conjuncts=2)
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

    # a name that means the same thing in every member of the grid
    relmap = R.canonical_map(theory)
    for c in ranked:
        c["canonical_key"] = repr(R.key(c["body"], relmap))
        c.setdefault("source", "premise-conjunction")

    # The second candidate source. Both are carried in the same artifact so the
    # stability analysis can compare their survival rates directly, which is the
    # question this sprint exists to answer.
    role = roles.candidates(records, theory, min_support=max(4, min_support // 2), top=40)
    role.sort(key=lambda c: -c["support"])
    role_ranked = role[:top]
    for i, c in enumerate(role_ranked):
        c["name"] = f"R{i:02d}"
        c["canonical_key"] = repr(R.key(c["statement_ast"], relmap))
        c["scores"] = {
            "arity": len(c["params"]),
            "theorems_covered": len(c["theorems"]),
            "support": c["support"],
        }
        c.pop("proof_ast", None)
        c.pop("statement_ast", None)

    # The third candidate source. Sprint 3 compared where candidates come from
    # and found no difference; this compares what they can say, which is the
    # last untested explanation for the null.
    quant = quantified.candidates(records, min_support=max(4, min_support // 2))
    quant.sort(key=lambda c: -c["support"])
    quant_ranked = quant[:top]
    for i, c in enumerate(quant_ranked):
        c["name"] = f"Q{i:02d}"
        c["canonical_key"] = repr(R.key(c["body"], relmap))
        c["scores"] = {
            "arity": len(c["params"]),
            "theorems_covered": len(c["theorems"]),
            "support": c["support"],
        }

    (out / "concepts.json").write_text(
        json.dumps(
            {
                "ranked": ranked + role_ranked + quant_ranked,
                "all_candidates": len(scored) + len(role) + len(quant),
            },
            indent=1,
            default=str,
        )
        + "\n"
    )

    ranking = importance_mod.score(records, views, assignments)
    for item in ranking:
        stmt = by_id[item["id"]]["statement_ast"]
        item["canonical_key"] = repr(R.key(stmt, relmap))
        # Counting by canonical key while displaying a raw statement made the
        # published table unreadable: the same relation appeared with three
        # arguments in one row and four in another, because each row showed
        # whichever member's identifier permutation happened to come first.
        item["canonical_statement"] = emit.formula(
            N.canonical(R.apply(stmt, relmap)), top=True
        )
    (out / "importance.json").write_text(json.dumps(ranking) + "\n")

    disjunctive = sum(1 for r in records if "∨" in r["normalized_statement"])
    case_analysis = sum(1 for r in records if r["generation_method"] == "case-analysis")
    summary = {
        "id": entry["id"],
        "config": entry["config"],
        "chainer_seed": entry["chainer_seed"],
        # The theory seed is a relabelling of the same theory, so it tests
        # permutation invariance. The base seed shifts the chainer seeds and is
        # what makes a run a genuine replicate — without it, every "repeat"
        # reuses chainer seeds 0..14 and no survival figure has an error bar.
        "base_seed": entry.get("base_seed", 0),
        "theory_seed": theory.seed,
        "relation_canonical_map": relmap,
        "kept": len(records),
        "distinct_statements": len(set(r["normalized_statement"] for r in records)),
        "existential_free": sum(1 for r in records if "∃" not in r["normalized_statement"]),
        "disjunctive": disjunctive,
        "case_analysis_derived": case_analysis,
        "concept_candidates": len(scored),
        "role_candidates": len(role),
        "quantified_candidates": len(quant),
        "rejected": rejected,
        "seconds": round(time.time() - t0, 1),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    log(
        f"  {entry['id']:26s} kept={summary['kept']:5d} ef={summary['existential_free']:4d} "
        f"disj={disjunctive:3d} ca={case_analysis:4d} cands={len(scored):4d} "
        f"{summary['seconds']:5.1f}s"
    )
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=3)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--min-support", type=int, default=8)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--tag", default="", help="suffix distinguishing this theory's members")
    ap.add_argument(
        "--base-seed",
        type=int,
        default=0,
        help="shifts every chainer seed; a different value is a replicate of the "
        "whole grid, which is what a noise floor needs",
    )
    args = ap.parse_args()

    T = theory_mod.load()
    entries = cfg_mod.grid(repeats=args.repeats, base_seed=args.base_seed)
    if args.limit:
        entries = entries[: args.limit]

    # A replicate must not overwrite the grid it is a replicate of. Base seed 0
    # keeps the original ids byte-identical so the stored grid stays readable.
    suffix = args.tag
    if args.base_seed:
        suffix = f"{suffix}-b{args.base_seed}" if suffix else f"b{args.base_seed}"
    for e in entries:
        e["base_seed"] = args.base_seed
        if suffix:
            e["id"] = f"{e['id']}-{suffix}"

    print(f"theory seed {T.seed}: {len(entries)} configurations, {args.generations} generations")
    summaries = []
    for entry in entries:
        s = run_one(entry, T, args.generations, args.min_support, args.top)
        if s:
            summaries.append(s)

    index = ENS / f"index{('-' + suffix) if suffix else ''}.json"
    index.write_text(json.dumps(summaries, indent=1) + "\n")
    print(f"{len(summaries)}/{len(entries)} members completed; wrote {index}")


if __name__ == "__main__":
    main()
