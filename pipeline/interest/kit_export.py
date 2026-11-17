"""Export the audit's corpora in the kit's library format, with their frozen labels.

Each audited corpus becomes `kit/data/euclean/<run>.jsonl`: the axioms, then
every kernel-checked statement in dependency order, with what its proof cites,
the cost of its own proof step under the audit's three measures, its frozen
restatement label, and, under `reference`, the values the audit computed. The
kit's tests recompute those values from the library alone; agreement is what
makes the kit the audited metric rather than a resemblance of it.

Everything exported is anonymized and passes `tools/leakguard.py`, like the rest
of the public tree. Nothing here reads the interpretation.

Usage:  python -m pipeline.interest.kit_export
"""

import hashlib
import json

from ..kernel import formula as F, proof as P
from ..kernel.theory import ROOT
from . import lean, metric, plan, run as run_mod

OUT = ROOT / "kit" / "data" / "euclean"

REFERENCE_KEYS = (
    "L0_raw", "L0_canon", "direct_users", "footprint", "importance",
    "trivial", "trivial_plus_grind", "relevant", "restatement_similarity", "reward_primary",
)


def export(run):
    run_dir, summary, T, records, lab, label_sha, tac, _, imp = run_mod.load(run)
    local, _ = run_mod.local_difficulty(records, tac)
    spec = json.loads((ROOT / summary["spec_path"]).read_text())
    scores = {r["id"]: r for r in map(json.loads, (run_dir / "interest" / "scores.jsonl").read_text().splitlines())}
    ids = {r["id"] for r in records}

    definitions = {T.sort: {"statement": "Type", "uses": []}}
    for rel, stmt in metric.declarations(T).items():
        if rel != T.sort:
            definitions[rel] = {"statement": stmt, "uses": [T.sort]}

    decls = []
    for ax in spec["axioms"]:
        decls.append({"name": ax["name"], "axiom": True, "statement": lean.raw_formula(ax["formula"], top=True),
                      "uses": sorted(metric.vocabulary(F.normalize(ax["formula"]), T.sort))})
    axiom_names = {ax["name"] for ax in spec["axioms"]}

    for r in records:
        rid = r["id"]
        refs = P.references(r["proof_ast"])
        premises = {n: m for n, m in sorted(refs.items()) if n in ids or n in axiom_names}
        s = scores[rid]
        ref = {k: s[k] for k in REFERENCE_KEYS}
        ref.update({k: v for k, v in s.items() if k.startswith(("log10_I0_", "V_")) and not k.endswith("_local")})
        decls.append({
            "name": rid,
            "axiom": False,
            "statement": r["statement"],
            "uses": sorted(metric.vocabulary(r["statement_ast"], T.sort)),
            "premises": premises,
            "cost": {x: local[x][rid] for x in ("loc", "term", "tac")},
            "label": lab[rid]["label"],
            "reference": ref,
        })

    head = {
        "format": "interestkit-library/1",
        "definitions": definitions,
        "costs": ["loc", "term", "tac"],
        "meta": {
            "source": "euclean interestingness audit",
            "run": run,
            "theory": summary["theory"],
            "role": "subject" if summary["theory"] == plan.SUBJECT else "control",
            "permutation": summary["theory_seed"],
            "chainer_seed": int(run.rsplit("-s", 1)[1]),
            "label_sha256": label_sha,
            "labels": {"R0": "an axiom's conclusion up to canonical form",
                       "R1": "single-axiom footprint, instantiation and argument permutation only",
                       "R2": "every supporting proof cites the axiom whose conclusion it is",
                       "N": "not a restatement"},
            "costs": {"loc": "LoC of the emitted proof step under one fixed layout",
                      "term": "size of the proof term",
                      "tac": "1 if a fixed tactic ladder closes it, else loc"},
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{run}.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for row in [head] + decls:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return path, len(decls) - len(spec["axioms"])


def main():
    manifest = {"report": "docs/interest-audit.md",
                "report_sha256": hashlib.sha256((ROOT / "docs" / "interest-audit.md").read_bytes()).hexdigest(),
                "corpora": []}
    for run in plan.corpora():
        path, n = export(run)
        manifest["corpora"].append({"file": path.name, "statements": n,
                                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(f"wrote {path.relative_to(ROOT)}  ({n} statements, {path.stat().st_size // 1024} KiB)")
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")


if __name__ == "__main__":
    main()
