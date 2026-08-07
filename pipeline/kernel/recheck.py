"""Re-verify a stored corpus against the kernel, without regenerating it.

Generation is stochastic and slow; verification is neither. Keeping them apart
means the durable record in `runs/<id>/corpus.json` can be re-checked at any
time, and the per-theorem files under `generated/` and `metadata/` can be
restored for whichever run is currently the subject of attention.

Usage:  python3 -m pipeline.kernel.recheck --run main
"""

import argparse
import json
import pathlib
from collections import defaultdict

from . import emit, proof as P, theory as theory_mod, verify

ROOT = pathlib.Path(__file__).resolve().parents[2]


def recheck(run, write_files=True, log=print):
    run_dir = ROOT / "runs" / run
    records = json.loads((run_dir / "corpus.json").read_text())
    T = theory_mod.load()

    # a local re-check first: cheap, and it localizes a bad term to one theorem
    env = dict(T.env)
    local_failures = []
    by_gen = defaultdict(list)
    for r in records:
        by_gen[r["generation"]].append(r)
    for g in sorted(by_gen):
        for r in by_gen[g]:
            try:
                got = P.infer(r["proof_ast"], env)
                assert emit.formula(got, top=True) == r["statement"]
            except Exception as exc:
                local_failures.append((r["id"], repr(exc)[:120]))
            env[r["id"]] = r["statement_ast"]
    log(f"local check: {len(records)} terms, {len(local_failures)} failures")
    for rid, msg in local_failures[:5]:
        log(f"   {rid}: {msg}")

    items_by_gen = [
        [(r["id"], r["statement_ast"], r["proof_ast"]) for r in by_gen[g]]
        for g in sorted(by_gen)
    ]
    from ..chainer import run as chainer_run

    failures = chainer_run.verify_corpus(items_by_gen, log=log)

    if write_files and not failures and not local_failures:
        gen_dir, meta_dir = ROOT / "generated", ROOT / "metadata"
        for d in (gen_dir, meta_dir):
            for old in d.glob("theorem_*"):
                old.unlink()
        for i, r in enumerate(records):
            stem = f"theorem_{i:06d}"
            (gen_dir / f"{stem}.lean").write_text(
                emit.theorem(r["id"], r["statement_ast"], r["proof_ast"])
            )
            slim = {k: v for k, v in r.items() if not k.endswith("_ast")}
            slim["verification"] = True
            (meta_dir / f"{stem}.json").write_text(json.dumps(slim, indent=1) + "\n")
        log(f"restored {len(records)} files under generated/ and metadata/")

    return local_failures, failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    local, kernel = recheck(args.run, write_files=not args.no_write)
    if local or kernel:
        print(f"FAILED: {len(local)} local, {len(kernel)} kernel")
        raise SystemExit(1)
    print("all theorems accepted by the kernel")


if __name__ == "__main__":
    main()
