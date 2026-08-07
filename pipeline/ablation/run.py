"""Per-concept ablation against the frozen target set.

For each concept: run the chainer at the calibrated budget with that concept's
rules in the environment, and count how many held-out targets are reached. The
baseline is run once and shared, since it is the same for every concept.

**On verification.** These runs are not kernel-checked, and do not need to be.
Every target is a statement already kernel-verified in the source corpus, so
"reached" means the search derived something already known true; every concept
injected is kernel-verified before it gets here; and each derivation is checked
by the local proof checker as it is built. What is being measured is search
reachability, not the truth of anything new. Running Lean over every ablation
would multiply the cost of the sweep for no additional guarantee.

Usage:  python3 -m pipeline.ablation.run --run main
"""

import argparse
import json
import pathlib
import time

from ..canon import relations as R
from ..concepts import invent, roles
from ..kernel import theory as theory_mod
from ..loop.run import Augmented, bridge_statements
from . import targets as targets_mod

ROOT = pathlib.Path(__file__).resolve().parents[2]


def concept_environment(concept, theory):
    """Turn a concept into rules the chainer can fire, whichever source it came from.

    Role concepts are already lemmas and go in directly. Syntactic concepts are
    definitions and need their bridge rules, plus the concept's own symbol in the
    relation table — without which the engine cannot compute its arity and the
    rules never match anything.
    """
    if concept.get("source") == "proof-role":
        return {concept["name"]: concept["statement_ast"]}, theory

    env, rels = bridge_statements([concept])
    augmented = Augmented(theory, rels)
    augmented.env.update(theory.env)
    return env, augmented


def _condition(theory, budget, target_keys, relmap, seeds, extra_env=None):
    """Run one condition across the whole seed set. Returns per-seed hits and kept."""
    hits, kept = [], []
    for s in seeds:
        reached, n = targets_mod.reachable(
            theory, budget, seed=s, extra_env=extra_env, relmap=relmap
        )
        hits.append(len(target_keys & reached))
        kept.append(n)
    return hits, kept


def run(run_dir, theory, spec, concepts, seeds=(0, 1, 2, 3), log=print):
    """Every condition is run over the same seed set and compared by range.

    A single seed per condition is not enough here, and that is a measurement
    about this pipeline rather than a matter of taste: the baseline alone varies
    by 12 targets across seeds, which is larger than almost every effect a
    concept produces. Reported at one seed, that variance reads as concepts
    damaging the search.

    Comparison is by non-overlapping range, not by a significance test. Four
    seeds cannot support one, and a conservative "these two ranges do not
    touch" is honest about how little is being claimed.
    """
    budget = spec["budget"]
    target_keys = {t["canonical_key"] for t in spec["targets"]}
    relmap = R.canonical_map(theory)

    t0 = time.time()
    base_hits, base_kept = _condition(theory, budget, target_keys, relmap, seeds)
    base_lo, base_hi = min(base_hits), max(base_hits)
    base_mean = sum(base_hits) / len(base_hits)
    log(f"baseline over seeds {list(seeds)}: targets {base_hits} "
        f"mean {base_mean:.1f} range [{base_lo}, {base_hi}], {time.time() - t0:.0f}s")

    rows = []
    for c in concepts:
        extra, th = concept_environment(c, theory)
        try:
            hits, kept = _condition(th, budget, target_keys, relmap, seeds, extra_env=extra)
        except Exception as exc:
            log(f"  {c['name']}: run failed ({type(exc).__name__}); recorded as no data")
            rows.append({"name": c["name"], "source": c.get("source"), "error": type(exc).__name__})
            continue
        lo, hi = min(hits), max(hits)
        mean = sum(hits) / len(hits)
        separated = lo > base_hi or hi < base_lo
        rows.append(
            {
                "name": c["name"],
                "source": c.get("source", "premise-conjunction"),
                "hits_per_seed": hits,
                "mean_targets": round(mean, 2),
                "range": [lo, hi],
                "baseline_mean": round(base_mean, 2),
                "baseline_range": [base_lo, base_hi],
                "delta_mean": round(mean - base_mean, 2),
                "separated_from_baseline": separated,
                "mean_kept": round(sum(kept) / len(kept), 1),
            }
        )
        flag = "  *" if separated else ""
        log(f"  {c['name']:>4s} [{rows[-1]['source']:>18s}] mean {mean:5.1f} "
            f"range [{lo:2d},{hi:2d}] delta {mean - base_mean:+5.1f} "
            f"kept {rows[-1]['mean_kept']:6.1f}{flag}")

    return {
        "budget": budget,
        "seeds": list(seeds),
        "targets": len(target_keys),
        "baseline": {
            "hits_per_seed": base_hits,
            "mean": round(base_mean, 2),
            "range": [base_lo, base_hi],
            "mean_kept": round(sum(base_kept) / len(base_kept), 1),
        },
        "concepts": rows,
    }


def load_concepts(run_dir, theory, top=10, min_support=12, role_support=10):
    records = json.loads((run_dir / "corpus.json").read_text())
    assignments = json.loads((run_dir / "assignments.json").read_text())
    by_id = {r["id"]: r for r in records}

    syn = invent.candidates(records, min_support=min_support)
    scored = [
        {
            "name": f"S{i:02d}",
            "params": c["params"],
            "body": c["body"],
            "theorems": c["theorems"],
            "source": c.get("source", "premise-conjunction"),
            "scores": invent.score(c, by_id, assignments),
        }
        for i, c in enumerate(syn)
    ]
    ranked = invent.rank(scored, top=top)
    for i, c in enumerate(ranked):
        c["name"] = f"S{i:02d}"

    role = roles.candidates(records, theory, min_support=role_support, top=60)
    role.sort(key=lambda c: -c["support"])
    for i, c in enumerate(role[:top]):
        c["name"] = f"R{i:02d}"
    return ranked + role[:top]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3])
    args = ap.parse_args()

    spec_path = ROOT / "runs" / "targets" / "targets.json"
    spec = json.loads(spec_path.read_text())
    if not spec.get("calibrated"):
        raise SystemExit(
            "target set is not calibrated; scoring against it would be meaningless. "
            "Rebuild with pipeline.ablation.targets --build"
        )

    T = theory_mod.load()
    run_dir = ROOT / "runs" / args.run
    concepts = load_concepts(run_dir, T, top=args.top)
    print(f"{len(concepts)} concepts under ablation at budget {spec['budget']}")

    report = run(run_dir, T, spec, concepts, seeds=tuple(args.seeds))

    deltas = [r["delta_mean"] for r in report["concepts"] if "delta_mean" in r]
    signal = [r for r in report["concepts"] if r.get("separated_from_baseline")]
    report["spread"] = {
        "min_delta_mean": min(deltas) if deltas else None,
        "max_delta_mean": max(deltas) if deltas else None,
        "separated": len(signal),
        "of": len(deltas),
    }
    out = ROOT / "runs" / args.run / "ablation.json"
    out.write_text(json.dumps(report, indent=1) + "\n")

    s = report["spread"]
    b = report["baseline"]["range"]
    print(f"\nmean delta range [{s['min_delta_mean']}, {s['max_delta_mean']}]; "
          f"{s['separated']}/{s['of']} concepts have a range disjoint from the "
          f"baseline's {b}")
    if s["separated"] == 0:
        print(
            "NO CONCEPT SEPARATES FROM THE BASELINE. Under this budget the criterion "
            "cannot distinguish any concept from seed noise, and must be reported that "
            "way rather than tabulated as a set of effects."
        )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
