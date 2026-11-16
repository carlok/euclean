"""A toy theory and hand-built corpus shared by the interest tests (no tests here).

Synthetic on purpose: the tests must not compute any score on a real corpus
before the pre-registration is frozen, and a toy keeps every expected value
checkable by hand.
"""

from pipeline.kernel import emit, formula as F, proof as P
from pipeline.kernel import theory as theory_mod


def v(n):
    return F.Var(n)


def c(n):
    return F.Const(n)


def R(a, b):
    return F.Atom("R0", [a, b])


SPEC = {
    "sort": "Obj",
    "relations": {"R0": 2},
    "axioms": [
        # composition
        {"name": "a0", "formula": F.Forall(["v0", "v1", "v2"],
                                           F.Imp(R(v("v0"), v("v1")),
                                                 F.Imp(R(v("v1"), v("v2")), R(v("v0"), v("v2")))))},
        # swap
        {"name": "a1", "formula": F.Forall(["v0", "v1"], F.Imp(R(v("v0"), v("v1")), R(v("v1"), v("v0"))))},
    ],
    "seed": 0,
    "theory": "ttoy",
}


def theory():
    return theory_mod.Theory(SPEC)


def record(rid, gen, pf, env):
    stmt = P.infer(pf, env)
    refs = P.references(pf)
    return {
        "id": rid,
        "generation": gen,
        "statement": emit.formula(stmt, top=True),
        "normalized_statement": emit.formula(stmt, top=True),
        "statement_ast": stmt,
        "proof_ast": pf,
        "axiom_dependencies": sorted(k for k in refs if k in ("a0", "a1")),
        "proof_dependencies": sorted(k for k in refs if k not in ("a0", "a1")),
        "proof_size": P.size(pf),
        "verification": True,
    }


def corpus():
    """Five statements whose labels are known by construction.

    inst   instance of a0 (v2 := v0), footprint {a0}            -> R1
    chain  a0 applied twice, footprint {a0}, conclusion R0 _ _   -> R2 (every holder cites a0)
    mixed  a1 then a0, conclusion R0 _ _                         -> R2
    diag   a1 and a0, conclusion R0 x x, no axiom concludes that -> N
    dup    the same statement as chain, derived later            -> R0
    lem    cites the lemma `inst`, so its footprint is {a0} through it
    """
    T = theory()
    env = dict(T.env)
    x, y, z, w = c("p0"), c("p1"), c("p2"), c("p3")
    out = []

    pf = P.Gen(["p0", "p1"], P.Lam("h0", R(x, y), P.Lam("h1", R(y, x),
         P.MP(P.MP(P.Ax("a0", [x, y, x]), P.Hyp("h0")), P.Hyp("h1")))))
    out.append(record("t0_00000", 0, pf, env))

    pf = P.Gen(["p0", "p1", "p2", "p3"], P.Lam("h0", R(x, y), P.Lam("h1", R(y, z), P.Lam("h2", R(z, w),
         P.MP(P.MP(P.Ax("a0", [x, z, w]),
                   P.MP(P.MP(P.Ax("a0", [x, y, z]), P.Hyp("h0")), P.Hyp("h1"))),
              P.Hyp("h2"))))))
    out.append(record("t0_00001", 0, pf, env))

    pf = P.Gen(["p0", "p1", "p2"], P.Lam("h0", R(y, x), P.Lam("h1", R(y, z),
         P.MP(P.MP(P.Ax("a0", [x, y, z]), P.MP(P.Ax("a1", [y, x]), P.Hyp("h0"))), P.Hyp("h1")))))
    out.append(record("t0_00002", 0, pf, env))

    pf = P.Gen(["p0", "p1"], P.Lam("h0", R(x, y),
         P.MP(P.MP(P.Ax("a0", [x, y, x]), P.Hyp("h0")), P.MP(P.Ax("a1", [x, y]), P.Hyp("h0")))))
    out.append(record("t0_00003", 0, pf, env))

    out.append(record("t1_00000", 1, out[1]["proof_ast"], env))

    for r in out:
        env[r["id"]] = r["statement_ast"]
    pf = P.Gen(["p0", "p1"], P.Lam("h0", R(x, y), P.Lam("h1", R(y, x),
         P.MP(P.MP(P.Ax("t0_00000", [x, y]), P.Hyp("h0")), P.Hyp("h1")))))
    out.append(record("t1_00001", 1, pf, env))
    return out
