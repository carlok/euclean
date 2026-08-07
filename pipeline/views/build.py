"""Assemble every view for a corpus into one artifact.

Usage:  python3 -m pipeline.views.build --run main
"""

import argparse
import json
import pathlib
import time

from ..kernel import theory as theory_mod
from . import features, symmetry

ROOT = pathlib.Path(__file__).resolve().parents[2]

NUMERIC_PREFIXES = ("rel_", "uses_", "node_", "proof_")
NUMERIC_KEYS = (
    "binders",
    "premises",
    "negated_premises",
    "equational_premises",
    "size",
    "conclusion_existential_vars",
    "distinct_variables",
    "repeated_variables",
    "max_variable_uses",
    "axioms_used",
    "lemmas_used",
    "symmetry_rank",
    "n_binders",
    "direct_uses",
    "downstream_closure",
    "generation_reach",
)


def build(records, theory):
    behaviour = features.behaviour_view(records)
    axiom_names = sorted(theory.env)
    out = {}
    for r in records:
        stmt = r["statement_ast"]
        view = {}
        view.update(features.syntax_features(stmt))
        view.update(features.dependency_features(r, axiom_names))
        view.update(features.proof_features(r))
        view.update(behaviour[r["id"]])
        view.update(symmetry.describe(stmt, theory.relations))
        out[r["id"]] = view
    return out


def numeric_matrix(views):
    """Standardized numeric vectors, plus the key order used."""
    ids = list(views)
    keys = set()
    for v in views.values():
        for k, val in v.items():
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if k in NUMERIC_KEYS or k.startswith(NUMERIC_PREFIXES):
                    keys.add(k)
    keys = sorted(keys)

    raw = [[float(views[i].get(k, 0) or 0) for k in keys] for i in ids]
    n = len(raw)
    means = [sum(col) / n for col in zip(*raw)]
    devs = []
    for j, col in enumerate(zip(*raw)):
        var = sum((x - means[j]) ** 2 for x in col) / n
        devs.append(var**0.5 or 1.0)
    norm = [[(row[j] - means[j]) / devs[j] for j in range(len(keys))] for row in raw]
    return ids, keys, norm


def serializable(views):
    def conv(v):
        if isinstance(v, frozenset):
            return sorted(v)
        if isinstance(v, tuple):
            return [conv(x) for x in v]
        if isinstance(v, list):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {str(k): conv(x) for k, x in v.items()}
        return v

    return {i: {k: conv(v) for k, v in view.items()} for i, view in views.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    args = ap.parse_args()

    run_dir = ROOT / "runs" / args.run
    records = json.loads((run_dir / "corpus.json").read_text())
    T = theory_mod.load()

    t0 = time.time()
    views = build(records, T)
    ids, keys, matrix = numeric_matrix(views)
    print(f"built {len(views)} views over {len(keys)} numeric features in {time.time() - t0:.1f}s")

    (run_dir / "views.json").write_text(json.dumps(serializable(views)) + "\n")
    (run_dir / "vectors.json").write_text(
        json.dumps({"ids": ids, "keys": keys, "matrix": matrix}) + "\n"
    )
    print(f"wrote {run_dir}/views.json and vectors.json")


if __name__ == "__main__":
    main()
