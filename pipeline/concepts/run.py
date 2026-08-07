"""Propose definitions, score them, and put them in front of the kernel.

Usage:  python3 -m pipeline.concepts.run --run main
"""

import argparse
import json
import pathlib

from ..kernel import theory as theory_mod, verify
from . import invent

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONCEPT_MODULE = ROOT / "theory" / "Theory" / "Concepts.lean"


def run(run_dir, min_support=8, top=12):
    records = json.loads((run_dir / "corpus.json").read_text())
    assignments = json.loads((run_dir / "assignments.json").read_text())
    by_id = {r["id"]: r for r in records}

    cands = invent.candidates(records, min_support=min_support)
    scored = []
    for i, c in enumerate(cands):
        scored.append(
            {
                "name": f"C{i:03d}",
                "params": c["params"],
                "body": c["body"],
                "theorems": c["theorems"],
                "scores": invent.score(c, by_id, assignments),
            }
        )
    ranked = invent.rank(scored, top=top)
    for i, c in enumerate(ranked):
        c["name"] = f"C{i:02d}"
    return scored, ranked


def write_lean(ranked):
    """A definitional extension plus its two bridge lemmas, kernel-checked.

    The bridges are `fun h => h`. That is not a shortcut — it is the evidence
    that the extension is definitional, and therefore that nothing the enriched
    theory proves was unprovable before.
    """
    lines = ["import Theory.Anonymous", "set_option linter.unusedVariables false", ""]
    for c in ranked:
        lines.append(invent.emit_definition(c["name"], c["body"], c["params"]))
        intro, elims = invent.emit_bridges(c["name"], c["body"], c["params"])
        lines.append(intro)
        lines.extend(elims)
    CONCEPT_MODULE.write_text("\n".join(lines))
    return CONCEPT_MODULE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--min-support", type=int, default=8)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    run_dir = ROOT / "runs" / args.run
    scored, ranked = run(run_dir, args.min_support, args.top)
    print(f"{len(scored)} candidates above support {args.min_support}; scoring top {len(ranked)}")

    path = write_lean(ranked)
    verify.lean_env()
    _, ok, log = verify.check_file(path)
    print(f"kernel check of {path.name}: {'accepted' if ok else 'REJECTED'}")
    if not ok:
        print("\n".join(log.splitlines()[:12]))

    for c in ranked:
        c["verified"] = ok
    (run_dir / "concepts.json").write_text(
        json.dumps({"ranked": ranked, "all_candidates": len(scored)}, indent=1, default=str) + "\n"
    )
    print()
    print(invent.summarize(ranked))
    print(f"\nwrote {run_dir}/concepts.json and {path}")


if __name__ == "__main__":
    main()
