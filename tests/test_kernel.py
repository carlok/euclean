"""Phase-1 gate: a hand-built suite exercising every node of the calculus.

Each derivation is checked twice — once by `proof.infer`, which is cheap and
local, and once by the Lean kernel, which is the one that counts. The suite is
written against whatever the loaded spec happens to call things; it asserts the
shapes it needs up front, so a reseeded theory fails loudly instead of silently
proving something else.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.kernel import emit, formula as F, proof as P, theory, verify  # noqa: E402

T = theory.load()
C = F.Const


def axiom_by_shape():
    """Locate the axioms this suite needs by shape, never by name.

    Names are seed-dependent; shapes are not. Anything here that fails to
    resolve means the theory changed, not that the kernel is broken.
    """
    found = {}
    for name in T.axiom_names:
        st = T.statement(name)
        body = st["body"] if st["kind"] == "forall" else st
        nvars = len(st["vars"]) if st["kind"] == "forall" else 0
        ps, concl = F.premises(body)
        sig = (nvars, len(ps), concl["kind"])
        # ∀ x y, R x y y x  — no premises, one atom
        if sig == (2, 0, "atom") and concl["args"] == [
            F.Var(st["vars"][0]),
            F.Var(st["vars"][1]),
            F.Var(st["vars"][1]),
            F.Var(st["vars"][0]),
        ]:
            found["swap"] = name
        # ∀ 6 vars, two premises, atomic conclusion
        elif sig == (6, 2, "atom"):
            found["chain"] = name
        # ∀ 3 vars, one premise, equational conclusion
        elif sig == (3, 1, "eq"):
            found["collapse4"] = name
        # ∀ 2 vars, one premise, equational conclusion
        elif sig == (2, 1, "eq"):
            found["collapse3"] = name
        # ∀ 4 vars, no premises, existential conclusion
        elif sig == (4, 0, "exists"):
            found["build"] = name
        # ∀ 5 vars, three premises, existential conclusion binding two
        elif sig == (5, 3, "exists") and len(concl["vars"]) == 2:
            found["fork"] = name
    missing = {"swap", "chain", "collapse4", "collapse3", "build", "fork"} - found.keys()
    assert not missing, f"theory does not have the expected shapes: {sorted(missing)}"
    return found


AX = axiom_by_shape()


def build_suite():
    """Returns [(name, statement, proof)] plus a growing env of proved lemmas."""
    env = dict(T.env)
    items = []

    def add(name, pf):
        stmt = P.infer(pf, env)
        env[name] = stmt
        items.append((name, stmt, pf))
        return stmt

    a, b, c, d, t = (C(x) for x in ("ca", "cb", "cc", "cd", "ct"))

    # t000  reflexivity of the 4-ary relation, from `swap` chained with itself
    add(
        "t000",
        # the chain lands on `R1 cb ca cb ca`, so generalize in that order to
        # get the binders in the shape later lemmas want
        P.Gen(
            ["cb", "ca"],
            P.MP(
                P.MP(P.Ax(AX["chain"], [a, b, b, a, b, a]), P.Ax(AX["swap"], [a, b])),
                P.Ax(AX["swap"], [a, b]),
            ),
        ),
    )

    # t001  symmetry, using t000 as a lemma (tests lemma reference, not just axioms)
    R1 = T.statement(AX["swap"])["body"]["rel"]
    add(
        "t001",
        P.Gen(
            ["ca", "cb", "cc", "cd"],
            P.Lam(
                "h",
                F.Atom(R1, [a, b, c, d]),
                P.MP(
                    P.MP(P.Ax(AX["chain"], [a, b, c, d, a, b]), P.Hyp("h")),
                    P.Ax("t000", [a, b]),
                ),
            ),
        ),
    )

    # t002  transitivity, composing t001 with the axiom
    add(
        "t002",
        P.Gen(
            ["ca", "cb", "cc", "cd", "ce", "cf"],
            P.Lam(
                "h1",
                F.Atom(R1, [a, b, c, d]),
                P.Lam(
                    "h2",
                    F.Atom(R1, [c, d, C("ce"), C("cf")]),
                    P.MP(
                        P.MP(
                            P.Ax(AX["chain"], [c, d, a, b, C("ce"), C("cf")]),
                            P.MP(P.Ax("t001", [a, b, c, d]), P.Hyp("h1")),
                        ),
                        P.Hyp("h2"),
                    ),
                ),
            ),
        ),
    )

    # t003  a degenerate instance, obtained by opening an existential and then
    #       rewriting along the equation the collapse axiom hands back
    src = P.Ax(AX["build"], [a, a, b, b])
    s0 = C("s0")
    eq = P.MP(P.Ax(AX["collapse4"], [a, s0, b]), P.AndR(P.Hyp("h")))
    goal003 = F.Atom(R1, [a, a, b, b])
    add(
        "t003",
        P.Gen(
            ["ca", "cb"],
            P.ExE(
                src,
                ["s0"],
                "h",
                goal003,
                P.EqSubst(P.EqSymm(eq), "z0", F.Atom(R1, [a, F.Var("z0"), b, b]),
                          P.AndR(P.Hyp("h"))),
            ),
        ),
    )

    # t004  the same manoeuvre on the 3-ary relation
    R0 = T.statement(AX["collapse3"])["body"]["lhs"]["rel"]
    src4 = P.Ax(AX["build"], [a, b, b, b])
    eq4 = P.MP(P.Ax(AX["collapse4"], [b, s0, b]), P.AndR(P.Hyp("h")))
    add(
        "t004",
        P.Gen(
            ["ca", "cb"],
            P.ExE(
                src4,
                ["s0"],
                "h",
                F.Atom(R0, [a, b, b]),
                P.EqSubst(P.EqSymm(eq4), "z0", F.Atom(R0, [a, b, F.Var("z0")]),
                          P.AndL(P.Hyp("h"))),
            ),
        ),
    )

    # t005  existential introduction, witnessed by t004
    add(
        "t005",
        P.Gen(
            ["ca", "cb"],
            P.ExI(
                F.Exists(["w"], F.Atom(R0, [a, b, F.Var("w")])),
                [b],
                P.Ax("t004", [a, b]),
            ),
        ),
    )

    # t006  conjunction introduction
    add(
        "t006",
        P.Gen(
            ["ca", "cb"],
            P.AndI(P.Ax("t000", [a, b]), P.Ax(AX["swap"], [a, b])),
        ),
    )

    # t007, t011  disjunction introduction, both sides
    add(
        "t007",
        P.Gen(
            ["ca", "cb", "cc"],
            P.Lam(
                "h",
                F.Atom(R0, [a, b, c]),
                P.OrL(P.Hyp("h"), F.Atom(R0, [b, c, a])),
            ),
        ),
    )
    add(
        "t011",
        P.Gen(
            ["ca", "cb", "cc"],
            P.Lam(
                "h",
                F.Atom(R0, [a, b, c]),
                P.OrR(P.Hyp("h"), F.Atom(R0, [b, c, a])),
            ),
        ),
    )

    # t008  reflexivity of equality
    add("t008", P.Gen(["ca"], P.EqRefl(a)))

    # t009  ex falso: the collapse axiom contradicts an assumed disequality
    add(
        "t009",
        P.Gen(
            ["ca", "cb"],
            P.Lam(
                "h1",
                F.Atom(R0, [a, b, a]),
                P.Lam(
                    "h2",
                    F.Not(F.Eq(a, b)),
                    P.Absurd(
                        P.MP(P.Ax(AX["collapse3"], [a, b]), P.Hyp("h1")),
                        P.Hyp("h2"),
                        F.Atom(R0, [b, a, b]),
                    ),
                ),
            ),
        ),
    )

    # t010  a two-constant existential elimination, re-existentialized —
    #       the nesting case the emitter has to get right
    fork = T.statement(AX["fork"])
    prem = F.premises(F.instantiate(fork, [a, b, c, d, t]))[0]
    src10 = P.MP(
        P.MP(P.MP(P.Ax(AX["fork"], [a, b, c, d, t]), P.Hyp("p0")), P.Hyp("p1")),
        P.Hyp("p2"),
    )
    body10 = P.ExI(
        F.Exists(["w"], F.Atom(R0, [a, b, F.Var("w")])),
        [C("s1")],
        P.AndL(P.Hyp("h")),
    )
    add(
        "t010",
        P.Gen(
            ["ca", "cb", "cc", "cd", "ct"],
            P.Lam(
                "p0",
                prem[0],
                P.Lam(
                    "p1",
                    prem[1],
                    P.Lam(
                        "p2",
                        prem[2],
                        P.ExE(
                            src10,
                            ["s1", "s2"],
                            "h",
                            F.Exists(["w"], F.Atom(R0, [a, b, F.Var("w")])),
                            body10,
                        ),
                    ),
                ),
            ),
        ),
    )

    return items


def test_infer_accepts_the_suite():
    items = build_suite()
    assert len(items) == 12
    for name, stmt, pf in items:
        assert stmt is not None, name
        assert P.size(pf) >= 1


def test_infer_rejects_a_broken_term():
    env = dict(T.env)
    bad = P.MP(P.Ax(AX["swap"], [C("ca"), C("cb")]), P.Ax(AX["swap"], [C("ca"), C("cb")]))
    try:
        P.infer(bad, env)
    except P.ProofError:
        return
    raise AssertionError("checker accepted modus ponens on a non-implication")


def test_lean_accepts_the_suite():
    items = build_suite()
    verify.clear_batches()
    paths, failures = verify.verify(items)
    for path, log in failures:
        print(f"--- {path} ---\n{log}")
    assert not failures, f"{len(failures)} batch(es) rejected by the kernel"


def test_metadata_is_readable_off_the_term():
    items = build_suite()
    name, stmt, pf = items[3]
    refs = P.references(pf)
    assert refs, "proof term records no dependencies"
    assert P.depth(pf) > 1
    assert set(P.node_counts(pf)) & {"exE", "eqSubst"}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
