"""A structural importance score, computed without any interpretation.

The point of this file is narrow and worth stating: it ranks theorems using
only properties the corpus can see — how often a result is reused, how much of
the corpus its proof underwrites, how general its statement is, how symmetric,
how many clusters it touches. Nothing here knows what the theory is about.

Whether that ranking has anything to do with mathematical importance is the
question the de-anonymization step asks. This module must not be allowed to
peek at the answer, so it lives on the public side and stays there.
"""

import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]

COMPONENTS = (
    "reuse",
    "downstream",
    "generality",
    "symmetry",
    "cluster_coverage",
    "proof_leverage",
)


def _rank_normalize(values):
    """Percentile rank in [0,1]. Robust to the wildly different scales the
    components come on, and to the long tails most of them have."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    n = max(len(values) - 1, 1)
    for pos, i in enumerate(order):
        out[i] = pos / n
    return out


def score(records, views, assignments, method="kmeans_numeric"):
    ids = [r["id"] for r in records]
    by_id = {r["id"]: r for r in records}

    users = defaultdict(set)
    for r in records:
        for dep in r["proof_dependencies"]:
            users[dep].add(r["id"])

    cluster_of = {i: assignments[i][method] for i in ids if i in assignments}
    clusters_touched = defaultdict(set)
    for rid, us in users.items():
        for u in us:
            if u in cluster_of:
                clusters_touched[rid].add(cluster_of[u])

    raw = {
        "reuse": [views[i]["direct_uses"] for i in ids],
        "downstream": [views[i]["downstream_closure"] for i in ids],
        # a statement with more binders and fewer hypotheses says more
        "generality": [
            views[i]["binders"] - 1.5 * views[i]["premises"] for i in ids
        ],
        "symmetry": [views[i]["symmetry_rank"] for i in ids],
        "cluster_coverage": [len(clusters_touched.get(i, ())) for i in ids],
        # cheap proofs that many expensive proofs rely on are load-bearing
        "proof_leverage": [
            views[i]["downstream_closure"] / max(by_id[i]["proof_size"], 1) for i in ids
        ],
    }
    normed = {k: _rank_normalize(v) for k, v in raw.items()}

    out = []
    for j, i in enumerate(ids):
        parts = {k: round(normed[k][j], 4) for k in COMPONENTS}
        out.append(
            {
                "id": i,
                "statement": by_id[i]["normalized_statement"],
                "components": parts,
                "raw": {k: raw[k][j] for k in COMPONENTS},
                "importance": round(sum(parts.values()) / len(COMPONENTS), 4),
            }
        )
    out.sort(key=lambda r: -r["importance"])
    return out


def main(run="main"):
    run_dir = ROOT / "runs" / run
    records = json.loads((run_dir / "corpus.json").read_text())
    views = json.loads((run_dir / "views.json").read_text())
    assignments = json.loads((run_dir / "assignments.json").read_text())
    ranked = score(records, views, assignments)
    (run_dir / "importance.json").write_text(json.dumps(ranked, indent=1) + "\n")
    print(f"ranked {len(ranked)} theorems; top 15 by structural importance:\n")
    for r in ranked[:15]:
        print(f"  {r['importance']:.3f}  {r['statement'][:120]}")
    print(f"\nwrote {run_dir}/importance.json")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "main")
