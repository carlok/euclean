"""Gate for the case-analysis node, checked the same two ways as everything else.

Sprint 1 produced 1904 theorems and not one of them contained a disjunction. The
calculus could introduce `∨` and had no way to consume it, so anything whose
definition is a disjunction was unreachable rather than merely undiscovered.
This is the test that the gap is closed: a proof that genuinely branches, with
different reasoning on each side, accepted by Lean — and a broken one rejected.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.kernel import formula as F, proof as P, theory, verify  # noqa: E402

T = theory.load()
C = F.Const

REL3 = next(r for r, a in T.relations.items() if a == 3)


def build_suite():
    env = dict(T.env)
    items = []

    def add(name, pf):
        stmt = P.infer(pf, env)
        env[name] = stmt
        items.append((name, stmt, pf))
        return stmt

    a, b, c = C("ca"), C("cb"), C("cc")
    A = F.Atom(REL3, [a, b, c])
    B = F.Atom(REL3, [b, c, a])
    D = F.Atom(REL3, [c, a, b])

    # k000  commutativity of ∨: the two branches need different proofs, so this
    #       cannot pass by accident the way `fun h => h` would
    add(
        "k000",
        P.Gen(
            ["ca", "cb", "cc"],
            P.Lam(
                "h",
                F.Or(A, B),
                P.OrE(
                    P.Hyp("h"),
                    "k0",
                    P.OrR(P.Hyp("k0"), B),
                    "k1",
                    P.OrL(P.Hyp("k1"), A),
                    F.Or(B, A),
                ),
            ),
        ),
    )

    # k001  nested case analysis over a three-way disjunction, each branch
    #       supplying different witnesses — the shape the dimension axiom hands
    #       back, and the reason nesting has to be right
    goal = F.Exists(["w0", "w1", "w2"], F.Atom(REL3, [F.Var("w0"), F.Var("w1"), F.Var("w2")]))
    add(
        "k001",
        P.Gen(
            ["ca", "cb", "cc"],
            P.Lam(
                "h",
                F.Or(A, F.Or(B, D)),
                P.OrE(
                    P.Hyp("h"),
                    "k0",
                    P.ExI(goal, [a, b, c], P.Hyp("k0")),
                    "k1",
                    P.OrE(
                        P.Hyp("k1"),
                        "k2",
                        P.ExI(goal, [b, c, a], P.Hyp("k2")),
                        "k3",
                        P.ExI(goal, [c, a, b], P.Hyp("k3")),
                        goal,
                    ),
                    goal,
                ),
            ),
        ),
    )

    # k002  case analysis collapsing to a single conclusion both branches share
    add(
        "k002",
        P.Gen(
            ["ca", "cb", "cc"],
            P.Lam(
                "h",
                F.Or(A, A),
                P.OrE(P.Hyp("h"), "k0", P.Hyp("k0"), "k1", P.Hyp("k1"), A),
            ),
        ),
    )

    return items


def test_infer_accepts_case_analysis():
    items = build_suite()
    assert len(items) == 3
    for name, stmt, pf in items:
        assert stmt is not None, name
    assert any("orE" in P.node_counts(pf) for _, _, pf in items)


def test_infer_rejects_branches_proving_different_goals():
    a, b, c = C("ca"), C("cb"), C("cc")
    A, B = F.Atom(REL3, [a, b, c]), F.Atom(REL3, [b, c, a])
    bad = P.Lam(
        "h",
        F.Or(A, B),
        # the right branch proves `B ∨ A`, the left proves `A ∨ B`
        P.OrE(P.Hyp("h"), "k0", P.OrL(P.Hyp("k0"), B), "k1", P.OrL(P.Hyp("k1"), A), F.Or(A, B)),
    )
    try:
        P.infer(bad, dict(T.env))
    except P.ProofError:
        return
    raise AssertionError("checker accepted a case analysis whose branches disagree")


def test_lean_accepts_case_analysis():
    items = build_suite()
    verify.clear_batches()
    paths, failures = verify.verify(items, start_index=900)
    for path, log in failures:
        print(f"--- {path} ---\n{log}")
    assert not failures, "the kernel rejected a case-analysis proof"


def test_lean_rejects_a_broken_case_analysis():
    """The emitter is only trustworthy if Lean would have caught it being wrong."""
    a, b, c = C("ca"), C("cb"), C("cc")
    A, B = F.Atom(REL3, [a, b, c]), F.Atom(REL3, [b, c, a])
    # The left branch has `A` in hand but the goal is `B`. The term is assembled
    # directly rather than through `infer`, so that Lean is the one being asked.
    stmt = F.Forall(
        ["v0", "v1", "v2"],
        F.Imp(F.Or(A, B), F.Atom(REL3, [F.Var("v1"), F.Var("v2"), F.Var("v0")])),
    )
    pf = P.Gen(
        ["ca", "cb", "cc"],
        P.Lam("h", F.Or(A, B), P.OrE(P.Hyp("h"), "k0", P.Hyp("k0"), "k1", P.Hyp("k1"), B)),
    )
    path = verify.write_batch(999, [("kbad", stmt, pf)])
    _, ok, log = verify.check_file(path)
    path.unlink()
    assert not ok, "the kernel accepted a case analysis whose left branch proves the wrong thing"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
