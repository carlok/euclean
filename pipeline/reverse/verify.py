"""Kernel-verify every sufficiency claim.

A claim that axioms S suffice for a statement is only worth making if a proof
exists that cites nothing outside S and the kernel accepts it. Reaching the
statement in a restricted search is suggestive; it is not the claim.

So each claim is re-derived with the rule set restricted to S, the derivation
and every lemma it leans on are emitted together, and Lean checks the batch.
Two things are then asserted, and a claim that fails either is dropped rather
than downgraded:

  * the batch compiles;
  * the transitive axiom references of the emitted proof are a subset of S.

The second matters as much as the first. A proof can compile while quietly
citing an axiom outside the subset — through a lemma that was itself derived
using one — and that would make the whole exercise a nicely formatted mistake.

This is the first output of the project where a novel-ish claim is fully
verified rather than merely reached, so the bar is exactly that and not one
step lower.

Usage:  python3 -m pipeline.reverse.verify --run main
"""

import argparse
import json
import pathlib
import time

from ..canon import relations as R
from ..chainer import run as chainer_run
from ..kernel import proof as P, theory as theory_mod
from .footprint import footprints
from .minimise import BUDGET, Restricted

ROOT = pathlib.Path(__file__).resolve().parents[2]


def rederive(base, keep, target_key, seeds, relmap):
    """Rebuild under the restricted theory and return the matching record set.

    Returns (record, all_records) so the caller can emit the target together
    with the lemmas it depends on — a batch missing a cited lemma would fail to
    compile for a reason that has nothing to do with the claim.
    """
    th = Restricted(base, keep)
    for s in seeds:
        records, _, _, _ = chainer_run.build(
            th,
            seed=s,
            generations=BUDGET["generations"],
            cfg={k: v for k, v in BUDGET.items() if k != "generations"},
            log=lambda *a: None,
        )
        for r in records:
            if repr(R.key(r["statement_ast"], relmap)) == target_key:
                return r, records, th
    return None, [], th


def cited_axioms(record, records, axiom_names):
    """Every axiom the proof rests on, transitively, in the restricted run."""
    foot, missing = footprints(records, axiom_names)
    direct = set(P.references(record["proof_ast"])) & set(axiom_names)
    return sorted(set(foot.get(record["id"], [])) | direct), missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    args = ap.parse_args()

    run_dir = ROOT / "runs" / args.run
    mini = json.loads((run_dir / "minimisation.json").read_text())
    T = theory_mod.load()
    relmap = R.canonical_map(T)

    # the claims worth verifying first are the ones that assert the most:
    # the biggest reductions off the transitive footprint
    claims = [r for r in mini["results"] if r["status"] == "ok" and r["dropped"]]
    claims.sort(key=lambda r: -(len(r["footprint"]) - len(r["sufficient"])))
    claims = claims[: args.limit]
    print(f"verifying {len(claims)} sufficiency claims")

    t0 = time.time()
    verified, rejected = [], []
    batch_index = 700
    for i, claim in enumerate(claims, 1):
        keep = set(claim["sufficient"])
        rec, records, th = rederive(T, keep, claim["canonical_key"], tuple(args.seeds), relmap)
        if rec is None:
            rejected.append({**claim, "reason": "not re-derived under the restricted theory"})
            print(f"  [{i:2d}] {claim['id']:10s} NOT re-derived")
            continue

        axioms, missing = cited_axioms(rec, records, th.axiom_names)
        outside = sorted(set(axioms) - keep)
        if outside or missing:
            rejected.append({**claim, "reason": f"cites outside the subset: {outside}"})
            print(f"  [{i:2d}] {claim['id']:10s} REJECTED, cites {outside}")
            continue

        by_gen = {}
        for r in records:
            by_gen.setdefault(r["generation"], []).append(
                (r["id"], r["statement_ast"], r["proof_ast"])
            )
        items = [by_gen[g] for g in sorted(by_gen)]
        failures = chainer_run.verify_corpus(items, log=lambda *a: None)
        batch_index += 1
        if failures:
            rejected.append({**claim, "reason": "kernel rejected the restricted batch"})
            print(f"  [{i:2d}] {claim['id']:10s} KERNEL REJECTED")
            continue

        verified.append(
            {
                "id": claim["id"],
                "statement": claim["statement"],
                "footprint": claim["footprint"],
                "suffices": sorted(keep),
                "dropped": claim["dropped"],
                "axioms_actually_cited": axioms,
                "kernel_verified": True,
            }
        )
        print(f"  [{i:2d}] {claim['id']:10s} verified: {sorted(keep)} suffices "
              f"(was {len(claim['footprint'])})")

    report = {
        "budget": BUDGET,
        "seeds": args.seeds,
        "claims_attempted": len(claims),
        "verified": len(verified),
        "rejected": len(rejected),
        "results": verified,
        "rejections": rejected,
        "what_this_establishes": (
            "For each entry: the listed axioms suffice to derive the statement, "
            "and Lean has accepted a proof citing nothing outside them. It does "
            "NOT establish that fewer would not suffice. Necessity would require "
            "counter-models, which this pipeline does not have and which this "
            "axiom set makes awkward: one of its axioms asserts that a certain "
            "element always exists, so no finite structure satisfies it and the "
            "usual small-model search is unavailable."
        ),
        "seconds": round(time.time() - t0, 1),
    }
    out = run_dir / "sufficiency.json"
    out.write_text(json.dumps(report, indent=1) + "\n")

    print(f"\n{report['verified']} verified, {report['rejected']} rejected, "
          f"{report['seconds']}s")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
