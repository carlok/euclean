"""A private Lean package per corpus, so `theory/` is never touched.

`kernel/verify.py` checks against `theory/Theory/Anonymous.lean`, which holds
one theory at a time and which the audit must not rewrite. Each corpus here
gets its own package under `runs/<run>/interest/lean/`: the base module is
emitted from the corpus's own spec, batches are written and checked exactly as
`kernel/verify.py` writes and checks them, and the toolchain is the one pinned
in `theory/lean-toolchain`.
"""

import concurrent.futures
import os
import re
import shutil
import subprocess

from ..kernel import emit, verify
from ..kernel.theory import ROOT

TOOLCHAIN_FILE = ROOT / "theory" / "lean-toolchain"
SENTINEL = "interest-sentinel-ok"
MAX_ERRORS = 1000000


def raw_formula(f, top=False):
    """`emit.formula`, but for the spec's own JSON form, where conjunctions and
    disjunctions are n-ary (`args`) rather than right-nested.

    Lean reads `A ∨ B ∨ C` as `A ∨ (B ∨ C)`, so this is the same proposition
    `emit.formula(F.normalize(f))` gives, written the way the committed base
    module writes it.
    """
    k = f["kind"]

    def wrap(s):
        return s if top else f"({s})"

    if k in ("var", "const"):
        return f["name"]
    if k == "atom":
        return f["rel"] + " " + " ".join(emit.term(a) for a in f["args"])
    if k == "eq":
        return wrap(f"{emit.term(f['lhs'])} = {emit.term(f['rhs'])}")
    if k == "not":
        return wrap(f"¬ {raw_formula(f['arg'])}")
    if k == "imp":
        return wrap(f"{raw_formula(f['lhs'])} → {raw_formula(f['rhs'], top=True)}")
    if k in ("and", "or"):
        sym = " ∧ " if k == "and" else " ∨ "
        parts = f["args"] if "args" in f else [f["lhs"], f["rhs"]]
        return wrap(sym.join(raw_formula(a) for a in parts))
    if k in ("forall", "exists"):
        binder = "∀" if k == "forall" else "∃"
        binds = " ".join(f"({v} : {emit.SORT})" for v in f["vars"])
        return wrap(f"{binder} {binds}, {raw_formula(f['body'], top=True)}")
    raise ValueError(k)


def base_module(spec):
    """The Lean base module for a spec, in the format of the committed one.

    For `theory/spec.json` this reproduces `theory/Theory/Anonymous.lean`
    byte for byte; a test holds it to that.
    """
    sort = spec["sort"]
    lines = [f"axiom {sort} : Type", ""]
    for rel, n in spec["relations"].items():
        lines.append(f"axiom {rel} : " + " → ".join([sort] * n + ["Prop"]))
    lines.append("")
    for a in spec["axioms"]:
        lines.append(f"axiom {a['name']} : {raw_formula(a['formula'], top=True)}")
    return "\n".join(lines) + "\n"


class Package:
    def __init__(self, path, spec):
        self.path = path
        self.spec = spec
        self.src = path / "Theory"
        self.build = path / ".lake" / "build" / "lib" / "lean"
        self._env = None

    def create(self):
        if self.path.exists():
            shutil.rmtree(self.path)
        self.src.mkdir(parents=True)
        (self.build / "Theory").mkdir(parents=True)
        shutil.copy(TOOLCHAIN_FILE, self.path / "lean-toolchain")
        (self.src / "Anonymous.lean").write_text(base_module(self.spec))
        ok, log = self.check("Anonymous")
        if not ok:
            raise RuntimeError(f"base module failed to build:\n{log[:2000]}")
        return self

    def env(self):
        if self._env is None:
            libdir = subprocess.run(
                ["lean", "--print-libdir"], cwd=self.path, capture_output=True, text=True, check=True
            ).stdout.strip()
            env = dict(os.environ)
            env["LEAN_PATH"] = f"{libdir}{os.pathsep}{self.build}"
            self._env = env
        return self._env

    def version(self):
        return subprocess.run(
            ["lean", "--version"], cwd=self.path, capture_output=True, text=True, check=True
        ).stdout.strip()

    def check(self, stem, timeout=None):
        """Compile Theory/<stem>.lean to an .olean. Returns (ok, log)."""
        out = self.build / "Theory" / f"{stem}.olean"
        try:
            r = subprocess.run(
                ["lean", "-o", str(out), f"Theory/{stem}.lean"],
                cwd=self.path, capture_output=True, text=True, env=self.env(), timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return False, f"TIMEOUT after {timeout}s\n{(exc.stdout or '')}"
        return r.returncode == 0, (r.stdout + r.stderr)

    def run(self, stem, timeout=None):
        """Elaborate Theory/<stem>.lean without writing an .olean.

        Lean stops a file after 100 errors by default (`maxErrors`). A tactic
        file is mostly declarations expected to fail, so the cap is lifted;
        otherwise everything after the hundredth failure goes unchecked.
        """
        try:
            r = subprocess.run(
                ["lean", f"-DmaxErrors={MAX_ERRORS}", f"Theory/{stem}.lean"],
                cwd=self.path, capture_output=True, text=True, env=self.env(), timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout or b""
            return None, out.decode() if isinstance(out, bytes) else out
        return r.returncode, (r.stdout + r.stderr)

    # --- the corpus itself, as kernel/verify.py would check it -------------

    def write_batch(self, index, items, imports):
        lines = [f"import {m}" for m in imports]
        lines += ["set_option linter.unusedVariables false"]
        lines += [f"set_option maxHeartbeats {verify.MAX_HEARTBEATS}", ""]
        for name, statement, pf in items:
            lines.append(emit.theorem(name, statement, pf))
        stem = f"B{index:04d}"
        (self.src / f"{stem}.lean").write_text("\n".join(lines))
        return stem

    def verify_corpus(self, items_by_gen, workers=None, log=print):
        """Same batching and import chaining as `chainer.run.verify_corpus_with`."""
        batch_no, imports, failures, modules = 0, ["Theory.Anonymous"], [], []
        workers = workers or (os.cpu_count() or 4)
        for g, items in enumerate(items_by_gen):
            if not items:
                continue
            stems = []
            for i in range(0, len(items), verify.BATCH_SIZE):
                stems.append(self.write_batch(batch_no, items[i : i + verify.BATCH_SIZE], imports))
                batch_no += 1
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(stems))) as pool:
                results = list(pool.map(self.check, stems))
            bad = [(s, lg) for s, (ok, lg) in zip(stems, results) if not ok]
            failures.extend(bad)
            log(f"  generation {g}: {len(stems)} batches, {len(bad)} rejected")
            imports = imports + [f"Theory.{s}" for s in stems]
            modules += stems
            if bad:
                break
        return failures, modules


ERROR_LINE = re.compile(r"^Theory/[A-Za-z0-9_]+\.lean:(\d+):\d+: error", re.M)


def failing_lines(log):
    return {int(m.group(1)) for m in ERROR_LINE.finditer(log)}
