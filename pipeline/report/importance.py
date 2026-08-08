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
    """Percentile rank in [0,1], with ties sharing a rank.

    Robust to the wildly different scales the components come on, and to the
    long tails most of them have.

    Ties get the *average* of the positions they span. The earlier version
    handed each tied value its own position, and since the sort is stable those
    positions followed the input order — which here is the order statements were
    derived in. That mattered enormously rather than marginally: on the
    reference corpus 1832 of 1904 statements share a single value on four of the
    six components, so for most of the corpus those components were recording
    where a statement appeared rather than anything about it. A percentile rank
    must be order-preserving, and this one now is; `report/diagnostics.py`
    checks that it stayed that way.
    """
    n = len(values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    denom = max(n - 1, 1)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 / denom
        for k in range(i, j + 1):
            out[order[k]] = shared
        i = j + 1
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


def aggregate(per_run, min_runs=2):
    """Rank over the ensemble rather than over one draw of it.

    `score` ranks within a single corpus, so the published ordering was always
    one sample. Measured across grid members, the mean rank correlation of that
    ordering is 0.41 with a range spanning strongly negative to 1.0 — the
    measure identifies a stable *set* and does not stably order it. Averaging
    the per-run percentile ranks, which are already comparable across runs by
    construction, orders the set once instead of once per draw.

    Statements are keyed canonically, so members built on re-permuted
    identifiers contribute to the same entry.

    **Absence counts as zero, and that is the whole design.** Averaging only
    over the runs where a statement appeared put statements seen in 2 of 45
    members at the top of the list — a high score from two lucky draws beating
    a moderate score from thirty-four. That is the same failure this project
    keeps finding elsewhere: a measure that rewards rarity. A statement that
    was never derived in a run was not important in that run, so it scores
    zero there, and the ranking becomes level times breadth.

    The conditional mean is still reported, since "scores well when it appears"
    is worth knowing; it is simply not what the list is ordered by.
    """
    from collections import defaultdict

    seen = defaultdict(list)
    example = {}
    for run in per_run:
        for item in run:
            key = item.get("canonical_key") or item["statement"]
            seen[key].append(item)
            example.setdefault(key, item)

    n_runs = max(len(per_run), 1)
    rows = []
    for key, items in seen.items():
        if len(items) < min_runs:
            continue
        comps = {}
        for c in COMPONENTS:
            vals = [i["components"][c] for i in items if c in i.get("components", {})]
            comps[c] = round(sum(vals) / len(vals), 4) if vals else 0.0
        scores = [i["importance"] for i in items]
        conditional = sum(scores) / len(scores)
        rows.append(
            {
                "canonical_key": key,
                "statement": example[key].get("canonical_statement")
                or example[key]["statement"],
                "runs": len(items),
                "of_runs": n_runs,
                "coverage": round(len(items) / n_runs, 4),
                "components": comps,
                # absence scores zero: level times breadth
                "importance": round(sum(scores) / n_runs, 4),
                "importance_when_present": round(conditional, 4),
                "importance_min": round(min(scores), 4),
                "importance_max": round(max(scores), 4),
            }
        )
    rows.sort(key=lambda r: -r["importance"])
    return rows


def aggregate_over_grid(ens_dir=None, min_runs=2, theory=None, base_seed=None):
    """Collect one grid's rankings and aggregate them.

    One grid, not every directory found. `coverage` here is `len(items) /
    n_runs`, so pooling replicates or two theories inflates the denominator
    while leaving each key reachable in only one of them — every coverage figure
    drops, and the drop reads as a real loss of breadth rather than as a
    counting error.
    """
    from ..ensemble import grids

    dirs = grids.member_dirs(
        ens=ens_dir,
        theory=grids.REFERENCE_THEORY if theory is None else theory,
        base_seed=grids.REFERENCE_BASE_SEED if base_seed is None else base_seed,
    )
    per_run = [
        json.loads((d / "importance.json").read_text())
        for d in dirs
        if (d / "importance.json").is_file()
    ]
    return per_run, aggregate(per_run, min_runs=min_runs)


def main(run="main"):
    run_dir = ROOT / "runs" / run
    records = json.loads((run_dir / "corpus.json").read_text())
    views = json.loads((run_dir / "views.json").read_text())
    assignments = json.loads((run_dir / "assignments.json").read_text())
    ranked = score(records, views, assignments)
    (run_dir / "importance.json").write_text(json.dumps(ranked, indent=1) + "\n")
    print(f"ranked {len(ranked)} theorems; top 15 within this run:\n")
    for r in ranked[:15]:
        print(f"  {r['importance']:.3f}  {r['statement'][:120]}")
    print(f"\nwrote {run_dir}/importance.json")

    per_run, agg = aggregate_over_grid()
    if agg:
        out = ROOT / "runs" / "ensemble" / "importance.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(agg, indent=1) + "\n")
        print(f"\naggregated over {len(per_run)} grid members; top 15 over the ensemble:\n")
        for r in agg[:15]:
            print(f"  {r['importance']:.3f}  ({r['runs']:2d}/{r['of_runs']}, "
                  f"{r['importance_when_present']:.2f} when present)  {r['statement'][:95]}")
        print(f"\nwrote {out}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "main")
