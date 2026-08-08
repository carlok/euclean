"""Gate for statements that are true because their hypotheses cannot hold.

Found by reading a corpus back through the interpretation rather than by any
check in the pipeline. A theory one of whose axioms forbids a relation from
holding of an element and itself produced

    Lt b1 b0 → Lt b1 b1 → ∃ b2, Lt b2 b0

whose second premise the axioms forbid. The statement is true, the kernel
accepts it, and it says nothing.

This is the second time this project has shipped vacuously true statements. The
first was assumed atoms contradicting one another, fixed at seed time. Nothing
looked at *derived* premises, which is this case.

The check is deliberately narrow. Deciding whether a premise set is satisfiable
is not on offer here; matching one premise against an atom the axioms forbid
outright is a single comparison, and it covers the failure observed.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.chainer import filters  # noqa: E402
from pipeline.kernel import formula as F, theory as theory_mod  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _theory(axioms, relations):
    return theory_mod.Theory({"sort": "Obj", "relations": relations, "axioms": axioms})


def _forbids_repeat():
    """A theory whose single axiom forbids a relation holding of a repeated arg."""
    return _theory(
        [
            {
                "name": "a0",
                "formula": F.Forall(
                    ["a"], F.Not(F.Atom("Lt", [F.Var("a"), F.Var("a")]))
                ),
            }
        ],
        {"Lt": 2},
    )


def test_a_forbidden_atom_is_recognised():
    pats = filters.refuted_premises(_forbids_repeat())
    assert len(pats) == 1 and pats[0]["rel"] == "Lt", pats


def test_a_premise_the_axioms_forbid_is_rejected():
    """The exact shape that was found in a real corpus."""
    refuted = filters.refuted_premises(_forbids_repeat())
    stmt = F.Forall(
        ["x", "y"],
        F.Imp(
            F.Atom("Lt", [F.Var("x"), F.Var("y")]),
            F.Imp(
                F.Atom("Lt", [F.Var("x"), F.Var("x")]),  # forbidden
                F.Atom("Lt", [F.Var("y"), F.Var("x")]),
            ),
        ),
    )
    assert filters.vacuous_premise(stmt, refuted) is True
    keep, reason = filters.assess(stmt, set(), set(), refuted)
    assert keep is False and reason == "vacuous-premise", reason


def test_a_satisfiable_premise_survives():
    """`Lt x y` is not forbidden; only the repeated-argument instance is.

    Rejecting on the relation alone would discard most of the corpus, so the
    hole-matching has to respect repetition.
    """
    refuted = filters.refuted_premises(_forbids_repeat())
    stmt = F.Forall(
        ["x", "y"],
        F.Imp(
            F.Atom("Lt", [F.Var("x"), F.Var("y")]),
            F.Atom("Lt", [F.Var("y"), F.Var("x")]),
        ),
    )
    assert filters.vacuous_premise(stmt, refuted) is False


def test_a_theory_with_no_forbidden_atom_is_unaffected():
    """The subject theory has none, so this filter must be inert on it.

    Its axioms use disequality inside implications rather than a standalone
    negative atom, so there is nothing to instantiate. Measured: the filter
    rejects zero statements on both the subject and the control, and its whole
    effect falls on a theory neither published number depends on.
    """
    T = theory_mod.load()
    assert filters.refuted_premises(T) == [], (
        "the subject theory now forbids an atom outright; the claim that this "
        "filter changes no published number needs re-measuring"
    )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
