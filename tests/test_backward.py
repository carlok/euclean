"""Gate for the backward prover.

Two things are pinned here, and the second cost an hour to find.

The prover must produce terms the existing kernel accepts — it builds them with
the same `kernel/proof.py` constructors precisely so there is no separate trust
story, and that is asserted rather than assumed.

And any measurement comparing a prover against a corpus must first check that
the loaded theory is the one the corpus was built from. The ensemble driver
rewrites `theory/spec.json` in place as it cycles anonymizations, so a
measurement taken while a grid is running silently compares a seed-0 corpus
against a seed-1 theory. That happened, produced a plausible-looking 0%, and was
only caught because a one-step axiom failed to unify with its own instance.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.backward import search as B, unify as U  # noqa: E402
from pipeline.kernel import formula as F, proof as P, theory  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = theory.load()


def _corpus():
    p = ROOT / "runs" / "main" / "corpus.json"
    return json.loads(p.read_text()) if p.exists() else None


def test_theory_matches_the_reference_corpus():
    """Guard against measuring across a spec swap. See the module docstring."""
    summary = ROOT / "runs" / "main" / "summary.json"
    if not summary.exists():
        print("  (no run summary; skipping)")
        return
    recorded = json.loads(summary.read_text()).get("theory_seed")
    assert recorded == T.seed, (
        f"loaded theory is seed {T.seed} but the reference corpus was built from "
        f"seed {recorded}. A grid run rewrites theory/spec.json in place; wait for "
        "it to finish before measuring."
    )


def test_unification_is_two_way():
    """Forward matching is one-way by design; backward search needs both sides."""
    a = F.Atom("R1", [F.Var("x"), F.Const("c"), F.Var("x"), F.Var("y")])
    b = F.Atom("R1", [F.Const("c"), F.Var("z"), F.Var("w"), F.Const("d")])
    sub = U.unify(a, b, {})
    assert sub is not None
    assert U.walk(F.Var("x"), sub)["name"] == "c"
    assert U.walk(F.Var("y"), sub)["name"] == "d"


def test_unification_refuses_a_clash():
    a = F.Atom("R1", [F.Var("x"), F.Var("x")])
    b = F.Atom("R1", [F.Const("c"), F.Const("d")])
    assert U.unify(a, b, {}) is None


def test_relations_are_not_assumed_symmetric():
    """Equality is a logical symbol; a relation's argument order is not."""
    a = F.Atom("R0", [F.Const("p"), F.Const("q"), F.Const("r")])
    b = F.Atom("R0", [F.Const("r"), F.Const("q"), F.Const("p")])
    assert U.unify(a, b, {}) is None


def test_found_proofs_typecheck():
    records = _corpus()
    if not records:
        print("  (no corpus; skipping)")
        return
    env = dict(T.env)
    checked = 0
    for r in records[:40]:
        pf = B.prove_closed(r["statement_ast"], env, seconds=2.0)
        if pf is None:
            continue
        got = P.infer(pf, env)  # raises if the term is malformed
        assert F.same(got, r["statement_ast"]), (
            "the prover returned a term proving something other than the goal"
        )
        checked += 1
    assert checked > 0, "the prover proved nothing at all on the reference corpus"


def test_budget_is_respected():
    """A prover that ignores its budget cannot be used inside a grid."""
    import time

    goal = F.Atom("R1", [F.Const("z0"), F.Const("z1"), F.Const("z2"), F.Const("z3")])
    started = time.monotonic()
    B.prove(goal, dict(T.env), {}, B.Budget(depth=12, seconds=1.0))
    assert time.monotonic() - started < 5.0, "the prover overran its deadline"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
