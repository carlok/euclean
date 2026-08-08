"""Recompute every stored importance ranking after a scoring change.

`report/importance._rank_normalize` used to break ties by input order, which is
derivation order, so most of each ranking below the top was an artifact. Fixing
it invalidates every `importance.json` written before the fix -- the reference
run and every grid member.

Nothing needs re-deriving. Each member already stores its corpus, views and
cluster assignments, so the ranking can be rebuilt from disk in seconds rather
than by re-running the chainer for hours.

The canonical key and canonical statement are re-attached exactly as
`ensemble/run.run_one` attaches them, from the relation map recorded in the
member's own summary. Recomputing them from the live theory would be wrong:
each member was built under its own identifier permutation.

Usage:
  python3 tools/rescore_importance.py --dry-run
  python3 tools/rescore_importance.py
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.canon import normalize as N, relations as R  # noqa: E402
from pipeline.kernel import emit  # noqa: E402
from pipeline.report import importance as importance_mod  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def rescore_dir(d, dry_run=False):
    """Rebuild one directory's importance.json. Returns (changed, detail)."""
    need = ("corpus.json", "views.json", "assignments.json", "importance.json")
    if not all((d / f).is_file() for f in need):
        return None, "missing inputs"

    records = json.loads((d / "corpus.json").read_text())
    views = json.loads((d / "views.json").read_text())
    assignments = json.loads((d / "assignments.json").read_text())
    old = json.loads((d / "importance.json").read_text())

    summary_path = d / "summary.json"
    relmap = None
    if summary_path.is_file():
        relmap = json.loads(summary_path.read_text()).get("relation_canonical_map")

    ranking = importance_mod.score(records, views, assignments)

    if relmap:
        by_id = {r["id"]: r for r in records}
        for item in ranking:
            stmt = by_id[item["id"]]["statement_ast"]
            item["canonical_key"] = repr(R.key(stmt, relmap))
            item["canonical_statement"] = emit.formula(
                N.canonical(R.apply(stmt, relmap)), top=True
            )
    elif old and "canonical_key" in old[0]:
        # a ranking that had keys must not silently lose them
        return None, "had canonical keys but no relation map to rebuild them"

    # Compare as sets. Averaged ranks make genuine ties genuinely equal, so the
    # order among them shuffles without the content changing; an ordered
    # comparison reports every ranking as changed and says nothing.
    old_top = {r["id"] for r in old[:10]}
    new_top = {r["id"] for r in ranking[:10]}
    moved = old_top != new_top
    detail = "top-10 membership " + ("changed" if moved else "unchanged")

    if not dry_run:
        (d / "importance.json").write_text(json.dumps(ranking) + "\n")
    return moved, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    targets = [p.parent for p in sorted(ROOT.glob("runs/*/importance.json"))]
    targets += [p.parent for p in sorted(ROOT.glob("runs/ens/*/importance.json"))]

    done = skipped = changed_top = 0
    for d in targets:
        moved, detail = rescore_dir(d, dry_run=args.dry_run)
        if moved is None:
            skipped += 1
            print(f"  skip {d.relative_to(ROOT)}: {detail}")
            continue
        done += 1
        changed_top += bool(moved)

    verb = "would rescore" if args.dry_run else "rescored"
    print(f"\n{verb} {done} rankings ({changed_top} with a changed top-10), skipped {skipped}")
    if not args.dry_run:
        print("Re-run pipeline.ensemble.stability and pipeline.report.diagnostics next.")


if __name__ == "__main__":
    main()
