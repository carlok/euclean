"""The fixed tactic ladder: the paper's triviality check, and V_tac.

Patel et al. (arXiv:2609.28603) mark a candidate trivial when one of
assumption, rfl, simp, tauto or simp_all closes it (Sec. 3.3, App. C.1.2), and
name line counts' dependence on automation as a limitation of their metric
(Sec. 4). Both are measured here with Lean.

`tauto` is a Mathlib tactic. The pinned toolchain has no Mathlib, so the
triviality rung is the four tactics that exist in core Lean; `grind` with no
premises is run as a separate, stronger stand-in and reported as secondary.

Rungs, each a separate declaration under the same heartbeat budget:

    triv    first | assumption | rfl | simp | simp_all, each required to close
    grind0  grind, given nothing
    grind   grind, given exactly the axioms and lemmas the stored proof cites

The budget is Lean's own deterministic heartbeat count rather than wall-clock
time, so a re-run gets the same answer on a different machine.
"""

import concurrent.futures
import json
import os
import time

from ..kernel import emit, proof as P
from .lean import SENTINEL, failing_lines

HEARTBEATS = 200000
BATCH = 200
FILE_TIMEOUT = 3600

RUNGS = {
    "triv": "first | (assumption; done) | (rfl; done) | (simp; done) | (simp_all; done)",
    "grind0": "grind",
    "grind": None,  # built per statement from its cited premises
}


def tactic_for(rung, record):
    if rung != "grind":
        return RUNGS[rung]
    names = sorted(P.references(record["proof_ast"]))
    return f"grind [{', '.join(names)}]" if names else "grind"


def attempt_line(rung, record):
    stmt = emit.formula(record["statement_ast"], top=True)
    return (
        f"set_option maxHeartbeats {HEARTBEATS} in "
        f"theorem tac_{rung}_{record['id']} : {stmt} := by {tactic_for(rung, record)}"
    )


def run_ladder(package, records, modules, rungs=("triv", "grind0", "grind"), workers=None, log=print):
    """Every rung on every record. Returns (results, meta).

    results: id -> {rung: True | False | None}; None means the file holding the
    attempt did not finish (timeout or crash), which is reported, not guessed.
    """
    header = [f"import Theory.{m}" for m in ["Anonymous"] + list(modules)]
    header += ["set_option linter.unusedVariables false", ""]
    jobs = []
    for rung in rungs:
        for i in range(0, len(records), BATCH):
            chunk = records[i : i + BATCH]
            stem = f"X{rung}{i // BATCH:04d}"
            lines = list(header)
            line_of = {}
            for r in chunk:
                lines.append(attempt_line(rung, r))
                line_of[len(lines)] = r["id"]  # 1-based line numbers, as Lean reports them
            lines.append(f'#eval IO.println "{SENTINEL}"')
            (package.src / f"{stem}.lean").write_text("\n".join(lines) + "\n")
            jobs.append((rung, stem, line_of))

    results = {r["id"]: {} for r in records}
    meta = {"heartbeats": HEARTBEATS, "batch": BATCH, "file_timeout_s": FILE_TIMEOUT,
            "files": len(jobs), "incomplete_files": [], "seconds": None,
            "lean": package.version(), "rungs": {k: RUNGS[k] or "grind [cited premises]" for k in rungs}}
    t0 = time.time()

    def one(job):
        rung, stem, line_of = job
        code, out = package.run(stem, timeout=FILE_TIMEOUT)
        return rung, stem, line_of, code, out

    workers = workers or (os.cpu_count() or 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for n, (rung, stem, line_of, code, out) in enumerate(pool.map(one, jobs), 1):
            finished = code is not None and SENTINEL in out
            bad = failing_lines(out)
            for line, rid in line_of.items():
                results[rid][rung] = (line not in bad) if finished else None
            if not finished:
                meta["incomplete_files"].append(stem)
            if n % 10 == 0 or n == len(jobs):
                log(f"  tactic files {n}/{len(jobs)}, {time.time() - t0:.0f}s")
    meta["seconds"] = round(time.time() - t0, 1)
    return results, meta


def write(path, results, meta):
    path.write_text(json.dumps({"meta": meta, "results": results}, indent=1, sort_keys=True) + "\n")


def read(path):
    data = json.loads(path.read_text())
    return data["results"], data["meta"]


def main():
    import argparse

    from ..kernel.theory import ROOT
    from .lean import Package

    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--workers", type=int, default=None,
                    help="Lean processes at once; the result does not depend on it")
    args = ap.parse_args()
    run_dir = ROOT / "runs" / args.run
    summary = json.loads((run_dir / "summary.json").read_text())
    spec = json.loads((ROOT / summary["spec_path"]).read_text())
    records = json.loads((run_dir / "corpus.json").read_text())
    pkg = Package(run_dir / "interest" / "lean", spec)
    results, meta = run_ladder(pkg, records, summary["lean_modules"], workers=args.workers)
    write(run_dir / "interest" / "tactics.json", results, meta)
    print(f"{args.run}: ladder done in {meta['seconds']}s, "
          f"{len(meta['incomplete_files'])} incomplete files")


if __name__ == "__main__":
    main()
