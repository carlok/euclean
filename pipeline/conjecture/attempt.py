"""Attempt each conjecture, keep the failures.

A conjecture is attempted by running the chainer at a small budget and checking
whether the conjecture's canonical key appears among what it proves. That is a
*semi-decision*: reaching it establishes truth, and not reaching it establishes
nothing beyond "not within this budget". Results are labelled accordingly and
nothing here is ever recorded as refuted — this pipeline has no counter-model
machinery and cannot refute anything.

Failures are kept with their source, because the interesting number is not how
many conjectures were proved but which proposer produced provable ones.

Usage:  python3 -m pipeline.conjecture.attempt --run main
"""

import argparse
import json
import pathlib
import time
from collections import Counter, defaultdict

from ..ablation import targets as targets_mod
from ..backward import search as backward
from ..canon import relations as R
from ..kernel import emit, theory as theory_mod
from . import propose as propose_mod

ROOT = pathlib.Path(__file__).resolve().parents[2]

ATTEMPT_BUDGET = {"generations": 2, "rounds": 5, "derivations_per_rule_per_round": 90}


def attempt(theory, conjectures, seeds=(0, 1, 2), budget=None, log=print):
    """Prove what can be proved within budget; label the rest unresolved."""
    budget = budget or ATTEMPT_BUDGET
    relmap = R.canonical_map(theory)
    wanted = {}
    for c in conjectures:
        wanted.setdefault(repr(R.key(c["statement_ast"], relmap)), []).append(c)

    reached = set()
    t0 = time.time()
    for s in seeds:
        got, kept = targets_mod.reachable(theory, budget, seed=s, relmap=relmap)
        reached |= got
        log(f"  attempt seed {s}: {kept} statements, {len(set(wanted) & reached)} conjectures hit")
    forward_only = set(wanted) & reached

    # The backward prover is used *in addition to* forward saturation, not
    # instead of it. On known-true statements each recovers 18% alone, and the
    # two sets are disjoint: together they reach 35%. Neither clears the bar
    # that was set for a replacement; used together the improvement is real and
    # close to free, since the backward pass costs under a second.
    env = dict(theory.env)
    for key, group in wanted.items():
        if key in reached:
            continue
        stmt = group[0]["statement_ast"]
        pf = backward.prove_closed(stmt, env, seconds=2.0)
        if pf is None:
            continue
        try:
            from ..kernel import formula as _F, proof as _P

            if _F.same(_P.infer(pf, env), stmt):
                reached.add(key)
        except Exception:
            continue
    backward_added = (set(wanted) & reached) - forward_only
    log(f"  forward reached {len(forward_only)}, backward added {len(backward_added)}")
    log(f"  {time.time() - t0:.0f}s over {len(seeds)} seeds")

    results = []
    for key, group in wanted.items():
        proved = key in reached
        for c in group:
            if c.get("structural_check"):
                outcome = "consistent" if c.get("structurally_identical") else "INCONSISTENT"
            else:
                # never "refuted": not reaching it inside a bounded search is not
                # evidence of falsity, and calling it that would be a lie
                outcome = "proved" if proved else "unresolved"
            results.append(
                {
                    **{k: v for k, v in c.items() if k != "statement_ast"},
                    "statement": emit.formula(c["statement_ast"], top=True),
                    "canonical_key": key,
                    "outcome": outcome,
                }
            )
    return results


def summarize(results):
    by_source = defaultdict(Counter)
    for r in results:
        by_source[r["source"]][r["outcome"]] += 1

    control = [r for r in results if r["source"] == "symmetry-control"]
    control_ok = sum(1 for r in control if r["outcome"] == "consistent")
    pos = [r for r in results if r["source"] == "positive-control"]
    pos_ok = sum(1 for r in pos if r["outcome"] == "proved")
    recall = pos_ok / len(pos) if pos else None

    return {
        "attempt_recall": {
            "known_statements_tried": len(pos),
            "recovered": pos_ok,
            "recall": round(recall, 3) if recall is not None else None,
            "note": (
                "Ceiling on any yield below. A source cannot score above what the "
                "bounded attempt can recover from statements already known true, so "
                "a low yield against a low recall is not evidence the conjectures "
                "are false."
            ),
        },
        "total": len(results),
        "by_source": {
            s: {
                "proved": c.get("proved", 0),
                "unresolved": c.get("unresolved", 0),
                "yield": round(c.get("proved", 0) / max(sum(c.values()), 1), 3),
            }
            for s, c in sorted(by_source.items())
        },
        "symmetry_control": {
            "checked": len(control),
            "consistent": control_ok,
            # structural: a permutation the view calls a symmetry must
            # canonicalize back to the statement it came from
            "view_consistent": control_ok == len(control) if control else None,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--per-source", type=int, default=40)
    args = ap.parse_args()

    run_dir = ROOT / "runs" / args.run
    records = json.loads((run_dir / "corpus.json").read_text())
    importance = json.loads((run_dir / "importance.json").read_text())
    T = theory_mod.load()

    conjectures = propose_mod.propose(records, importance, per_source=args.per_source)
    print(f"{len(conjectures)} conjectures proposed")
    for s, n in Counter(c["source"] for c in conjectures).most_common():
        print(f"  {s}: {n}")

    results = attempt(T, conjectures, seeds=tuple(args.seeds))
    report = {"budget": ATTEMPT_BUDGET, "seeds": args.seeds, **summarize(results),
              "results": results}
    (run_dir / "conjectures.json").write_text(json.dumps(report, indent=1) + "\n")

    print()
    for s, c in report["by_source"].items():
        print(f"  {s:22s} proved {c['proved']:4d}  unresolved {c['unresolved']:4d}  "
              f"yield {c['yield']:.0%}")
    rec = report["attempt_recall"]
    print(f"\nattempt recall on known statements: {rec['recovered']}/"
          f"{rec['known_statements_tried']} ({rec['recall']:.0%} if measurable) "
          f"-- this bounds every yield above")
    ctrl = report["symmetry_control"]
    print(f"symmetry view check (structural): {ctrl['consistent']}/{ctrl['checked']} "
          f"consistent -> view_consistent={ctrl['view_consistent']}")
    print(f"wrote {run_dir}/conjectures.json")


if __name__ == "__main__":
    main()
