"""Batch verification against the Lean kernel.

Theorems are emitted into batch modules of a few hundred each and checked in
parallel. `lake env` is consulted exactly once for LEAN_PATH; after that we
invoke `lean` directly, which removes a per-batch process-spawn tax that
otherwise dominates the recheck time.
"""

import concurrent.futures
import functools
import os
import pathlib
import subprocess

from . import emit

ROOT = pathlib.Path(__file__).resolve().parents[2]
THEORY_DIR = ROOT / "theory"
BATCH_SIZE = 200


class VerificationError(RuntimeError):
    pass


def lean_signature(theory_dir=None):
    """Relation name -> arity, read from the Lean base module.

    The point of comparison for `assert_theory_matches`. Declarations look like
    `axiom R0 : Obj → Obj → Obj → Prop`, so the arity is the count of argument
    sorts before `Prop`.
    """
    path = (theory_dir or THEORY_DIR) / "Theory" / "Anonymous.lean"
    if not path.exists():
        raise VerificationError(f"no base module at {path}")
    sig = {}
    sort = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("axiom "):
            continue
        head, _, rhs = line[len("axiom "):].partition(":")
        name, rhs = head.strip(), rhs.strip()
        if rhs == "Type":
            sort = name
            continue
        if sort and rhs.endswith("Prop"):
            sig[name] = rhs.count(sort)
    return sig


def assert_theory_matches(theory, theory_dir=None):
    """Refuse to check a corpus against a base module built from other axioms.

    Before a second theory existed, "which axioms Python reasons about" and
    "which axioms Lean checks against" were the same thing, because both were
    whatever sat in `theory/`. They are now independent, and the generator
    rewrites that directory in place. Nothing else would notice the mismatch:
    Lean would reject every batch and the run would read as a theory that
    derives nothing.
    """
    got = lean_signature(theory_dir)
    want = dict(theory.relations)
    if got != want:
        raise VerificationError(
            f"the Lean base module declares {got} but the loaded theory has {want}. "
            f"The generator rewrites theory/ in place — regenerate for theory "
            f"{theory.name!r} before verifying."
        )


@functools.lru_cache(maxsize=8)
def lean_env(fingerprint=None):
    """Build the base theory once, then capture the environment lean needs.

    Keyed by `fingerprint` — pass `theory.spec_hash`. A zero-argument cache
    returns the first theory's LEAN_PATH for every later one, which is only
    harmless while there is one theory.
    """
    # only the base module: `lake build Theory` would drag in every batch via
    # the library glob, so one bad batch would take down the whole environment
    build = subprocess.run(
        ["lake", "build", "Theory.Anonymous"], cwd=THEORY_DIR, capture_output=True, text=True
    )
    if build.returncode != 0:
        raise VerificationError(f"base theory failed to build:\n{build.stdout}{build.stderr}")
    r = subprocess.run(
        ["lake", "env", "printenv", "LEAN_PATH"],
        cwd=THEORY_DIR,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise VerificationError(f"could not read LEAN_PATH:\n{r.stderr}")
    env = dict(os.environ)
    env["LEAN_PATH"] = r.stdout.strip()
    return env


def write_batch(index, items, imports=("Theory.Anonymous",)):
    """items: iterable of (name, statement, proof). Returns the written path."""
    # generated binders are frequently unused; the linter has nothing useful to
    # say about machine-written terms and its output buries real errors
    lines = [f"import {m}" for m in imports]
    lines += ["set_option linter.unusedVariables false", ""]
    for name, statement, pf in items:
        lines.append(emit.theorem(name, statement, pf))
    path = THEORY_DIR / "Theory" / f"B{index:04d}.lean"
    path.write_text("\n".join(lines))
    return path


def olean_dir():
    d = THEORY_DIR / ".lake" / "build" / "lib" / "lean" / "Theory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def check_file(path):
    # emit the .olean too: later generations cite earlier ones, and an import
    # cannot be satisfied by a source file that was merely checked
    out = olean_dir() / f"{path.stem}.olean"
    r = subprocess.run(
        ["lean", "-o", str(out), str(path.relative_to(THEORY_DIR))],
        cwd=THEORY_DIR,
        capture_output=True,
        text=True,
        env=lean_env(),
    )
    return path, r.returncode == 0, (r.stdout + r.stderr).strip()


def check_files(paths, workers=None):
    workers = workers or min(len(paths), (os.cpu_count() or 4))
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for res in pool.map(check_file, paths):
            results.append(res)
    return results


def verify(items, start_index=0, batch_size=BATCH_SIZE, workers=None):
    """Emit and kernel-check everything. Returns (paths, failures)."""
    items = list(items)
    lean_env()  # build the base theory before anything is written
    paths = []
    for i in range(0, len(items), batch_size):
        paths.append(write_batch(start_index + i // batch_size, items[i : i + batch_size]))
    failures = [(p, log) for p, ok, log in check_files(paths, workers) if not ok]
    return paths, failures


def clear_batches():
    for p in (THEORY_DIR / "Theory").glob("B[0-9]*.lean"):
        p.unlink()
    lake_dir = THEORY_DIR / ".lake" / "build"
    if lake_dir.exists():
        for p in lake_dir.rglob("B[0-9]*.*"):
            p.unlink()
