"""Extract a schema for every cluster, and mine recurring proof motifs.

Usage:  python3 -m pipeline.patterns.run --run main
"""

import argparse
import json
import pathlib
from collections import defaultdict

from ..canon import normalize as N
from . import antiunify as A, motifs

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _shape(stmt):
    """Coarse quantifier/premise signature used to stratify a cluster."""
    from ..kernel import formula as F

    binders = len(stmt["vars"]) if stmt["kind"] == "forall" else 0
    body = stmt["body"] if stmt["kind"] == "forall" else stmt
    ps, concl = F.premises(body)
    return (
        binders,
        len(ps),
        concl["kind"],
        len(concl["vars"]) if concl["kind"] == "exists" else 0,
    )


def cluster_schemas(records, assignments, method, min_size=4, max_members=60):
    by_id = {r["id"]: r for r in records}
    groups = defaultdict(list)
    for rid, labels in assignments.items():
        if rid in by_id:
            groups[labels[method]].append(rid)

    out = []
    for cid, member_ids in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(member_ids) < min_size:
            continue

        # Anti-unifying across different quantifier shapes yields a bare hole:
        # the very first structural mismatch generalizes the whole formula. So
        # split each cluster by coarse shape first and schematize the largest
        # stratum. The stratum size is reported, since a schema over 8 of 56
        # members is a weaker claim than one over all of them.
        strata = defaultdict(list)
        for i in member_ids:
            strata[_shape(by_id[i]["statement_ast"])].append(i)
        stratum = max(strata.values(), key=len)
        if len(stratum) < min_size:
            continue

        members = sorted(stratum, key=lambda i: by_id[i]["proof_size"])[:max_members]
        forms = [N.canonical(by_id[i]["statement_ast"]) for i in members]
        schema, nvars = A.generalize(forms)
        if schema is None:
            continue
        spec = A.specificity(schema)

        # how far the schema reaches beyond the cluster it came from
        covered = sum(
            1 for r in records if A.instance_of(schema, N.canonical(r["statement_ast"]), {})
        )
        out.append(
            {
                "cluster": cid,
                "method": method,
                "size": len(member_ids),
                "stratum_size": len(stratum),
                "generalized_over": len(members),
                "schema": A.render(schema),
                "schema_ast": schema,
                "pattern_variables": nvars,
                "specificity": round(spec, 3),
                "corpus_coverage": covered,
                "coverage_beyond_stratum": covered - len(stratum),
                "examples": [by_id[i]["normalized_statement"] for i in members[:3]],
            }
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--method", default="kmeans_numeric")
    ap.add_argument("--min-size", type=int, default=4)
    args = ap.parse_args()

    run_dir = ROOT / "runs" / args.run
    records = json.loads((run_dir / "corpus.json").read_text())
    assignments = json.loads((run_dir / "assignments.json").read_text())

    schemas = {}
    for method in ("kmeans_numeric", "linkage_dependency", "bucket_structure"):
        schemas[method] = cluster_schemas(records, assignments, method, args.min_size)

    report = {
        "schemas": schemas,
        "proof_motifs": motifs.top_motifs(records),
    }
    slim = {
        "schemas": {
            m: [{k: v for k, v in s.items() if k != "schema_ast"} for s in ss]
            for m, ss in schemas.items()
        },
        "proof_motifs": report["proof_motifs"],
    }
    (run_dir / "patterns.json").write_text(json.dumps(slim, indent=1) + "\n")

    for method, ss in schemas.items():
        useful = [s for s in ss if s["specificity"] >= 0.4]
        print(f"{method}: {len(ss)} clusters schematized, {len(useful)} with specificity >= 0.4")
        for s in sorted(ss, key=lambda x: -x["specificity"])[:4]:
            print(
                f"   [{s['stratum_size']:3d}/{s['size']:4d} members, spec {s['specificity']:.2f}, "
                f"reach +{s['coverage_beyond_stratum']}]  {s['schema'][:120]}"
            )
    print(f"wrote {run_dir}/patterns.json")


if __name__ == "__main__":
    main()
