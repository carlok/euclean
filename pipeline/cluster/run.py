"""Run every clustering method, summarize the clusters, compare the results.

Usage:  python3 -m pipeline.cluster.run --run main
"""

import argparse
import json
import pathlib
from collections import Counter

from ..views import kernels
from . import methods, sk

ROOT = pathlib.Path(__file__).resolve().parents[2]

SUMMARY_KEYS = (
    "conclusion_kind",
    "conclusion_relation",
    "binders",
    "premises",
    "negated_premises",
    "conclusion_existential_vars",
    "variable_orbits",
    "axioms_used",
    "lemmas_used",
    "proof_depth",
)


def summarize_cluster(member_ids, views, records_by_id):
    """What the members of a cluster actually have in common.

    Cluster assignments on their own are close to useless for this experiment —
    the question is never "which bucket" but "what do these share", so the
    shared-value and shared-dependency analysis is the real output here.
    """
    members = [views[i] for i in member_ids]
    shared = {}
    for key in SUMMARY_KEYS:
        vals = {json.dumps(m.get(key), sort_keys=True) for m in members}
        if len(vals) == 1:
            shared[key] = json.loads(next(iter(vals)))

    dep_sets = [set(m["dependency_set"]) for m in members]
    common_deps = set.intersection(*dep_sets) if dep_sets else set()
    all_deps = set.union(*dep_sets) if dep_sets else set()

    wl = Counter(m["wl"] for m in members)
    concl = Counter(str(m.get("conclusion_relation")) for m in members)
    orbits = Counter(json.dumps(m.get("variable_orbits")) for m in members)

    reps = sorted(member_ids, key=lambda i: views[i]["size"])[:4]

    return {
        "size": len(member_ids),
        "shared_features": shared,
        "common_dependencies": sorted(common_deps),
        "dependency_union": sorted(all_deps),
        "distinct_structures": len(wl),
        "structural_concentration": wl.most_common(1)[0][1] / len(members),
        "conclusion_relations": dict(concl),
        "orbit_signatures": len(orbits),
        "dominant_orbit_share": orbits.most_common(1)[0][1] / len(members),
        "representatives": [
            {"id": i, "statement": records_by_id[i]["normalized_statement"]} for i in reps
        ],
    }


def run(run_dir, k=28, threshold=0.34, seed=0, only=None):
    records = json.loads((run_dir / "corpus.json").read_text())
    views = json.loads((run_dir / "views.json").read_text())
    vec = json.loads((run_dir / "vectors.json").read_text())
    ids, matrix = vec["ids"], vec["matrix"]
    by_id = {r["id"]: r for r in records}

    dep_sets = [set(views[i]["dependency_set"]) for i in ids]

    extras = {}
    dist = sk.jaccard_matrix(dep_sets)

    # WL kernel over formula graphs, fit on this corpus only
    stmts = [by_id[i]["statement_ast"] for i in ids]
    X, _ = kernels.feature_matrix(stmts)
    emb, explained = kernels.svd_embedding(X)
    extras["wl_svd_explained_variance"] = round(explained, 4)
    extras["wl_features"] = int(X.shape[1])

    # Every method is tagged with the space it actually optimizes in, so that
    # each can be scored on its own terms as well as on a common reference.
    # Judging a syntax-based clustering purely by a dependency metric would
    # understate it for reasons that have nothing to do with its quality.
    spaces = {
        "numeric": sk.l2_distance_matrix(matrix),
        "dependency": dist,
        "wl": sk.l2_distance_matrix(emb.tolist()),
    }

    labelings = {
        # hand-rolled baselines, retained for comparison
        "baseline_kmeans": (methods.kmeans(matrix, k, seed=seed), "numeric"),
        "baseline_single_linkage": (methods.single_linkage(dep_sets, threshold), "dependency"),
        "bucket_structure": (methods.bucket([views[i]["wl"] for i in ids]), "wl"),
        "kmeans_numeric": (sk.kmeans(matrix, k, seed=seed), "numeric"),
        "linkage_dependency": (sk.average_linkage(dist, threshold), "dependency"),
        "density_dependency": (sk.density(dist), "dependency"),
        "kmeans_wl_embedding": (sk.kmeans(emb.tolist(), k, seed=seed), "wl"),
        "spectral_wl": (sk.spectral(kernels.gram(X), k, seed=seed), "wl"),
    }
    # An ensemble member does not need the full method comparison — that is a
    # property of the main run. Spectral clustering alone is a cubic
    # eigendecomposition, and running eight methods per member is what made the
    # first grid attempt slower than the generation it was analyzing.
    if only:
        labelings = {n: v for n, v in labelings.items() if n in only}
    method_space = {n: s for n, (_, s) in labelings.items()}
    labelings = {n: lab for n, (lab, _) in labelings.items()}

    report = {"n": len(ids), "methods": {}, "agreement": {}, "representation": extras}
    for name, assign in labelings.items():
        coh = methods.cohesion(assign, dep_sets)
        base = methods.shuffled_baseline(assign, dep_sets, seed=seed)
        groups = {}
        for i, a in zip(ids, assign):
            if a != -1:
                groups.setdefault(a, []).append(i)
        big = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        report["methods"][name] = {
            **sk.label_stats(assign),
            "cohesion": round(coh, 4),
            "cohesion_shuffled_baseline": round(base, 4),
            "lift_over_baseline": round(coh - base, 4),
            "space": method_space[name],
            "silhouette_own_space": sk.silhouette(spaces[method_space[name]], assign),
            "silhouette_dependency": sk.silhouette(dist, assign),
            "clusters_detail": {
                str(cid): summarize_cluster(m, views, by_id) for cid, m in big[:12]
            },
        }

    names = list(labelings)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            report["agreement"][f"{a}~{b}"] = round(
                methods.entropy_agreement(labelings[a], labelings[b]), 4
            )

    assignments = {i: {m: labelings[m][j] for m in labelings} for j, i in enumerate(ids)}
    return report, assignments


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--k", type=int, default=28)
    ap.add_argument("--threshold", type=float, default=0.34)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    run_dir = ROOT / "runs" / args.run
    report, assignments = run(run_dir, args.k, args.threshold, args.seed)

    (run_dir / "clusters.json").write_text(json.dumps(report, indent=1) + "\n")
    (run_dir / "assignments.json").write_text(json.dumps(assignments) + "\n")

    print(f"{report['n']} theorems")
    for name, m in report["methods"].items():
        own, dep = m["silhouette_own_space"], m["silhouette_dependency"]
        f = lambda v: f"{v:+.3f}" if v is not None else "  n/a"
        print(
            f"  {name:24s} [{m['space']:10s}] clusters={m['clusters']:4d} "
            f"largest={m['largest']:5d} noise={m['noise']:4d} "
            f"lift={m['lift_over_baseline']:+.3f} sil_own={f(own)} sil_dep={f(dep)}"
        )
    top = sorted(report["agreement"].items(), key=lambda kv: -kv[1])[:5]
    print("  strongest agreements (NMI):", ", ".join(f"{k}={v}" for k, v in top))
    print(f"wrote {run_dir}/clusters.json")


if __name__ == "__main__":
    main()
