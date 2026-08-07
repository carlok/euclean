"""Proof term -> Lean 4 source. Pure, total, and deliberately unclever.

Everything is fully parenthesized. Elegance in the generated Lean is worth
nothing here; the only property that matters is that what the kernel checks is
exactly the term we built.
"""

from . import formula as F

SORT = "Obj"


# --- formulas -------------------------------------------------------------


def term(t):
    return t["name"]


def formula(f, top=False):
    k = f["kind"]
    if k in ("var", "const"):
        return f["name"]
    if k == "atom":
        return f["rel"] + " " + " ".join(term(a) for a in f["args"])
    if k == "eq":
        return _wrap(f"{term(f['lhs'])} = {term(f['rhs'])}", top)
    if k == "not":
        return _wrap(f"¬ {formula(f['arg'])}", top)
    if k == "imp":
        return _wrap(f"{formula(f['lhs'])} → {formula(f['rhs'], top=True)}", top)
    if k == "and":
        return _wrap(f"{formula(f['lhs'])} ∧ {formula(f['rhs'])}", top)
    if k == "or":
        return _wrap(f"{formula(f['lhs'])} ∨ {formula(f['rhs'])}", top)
    if k in ("forall", "exists"):
        binder = "∀" if k == "forall" else "∃"
        binds = " ".join(f"({v} : {SORT})" for v in f["vars"])
        return _wrap(f"{binder} {binds}, {formula(f['body'], top=True)}", top)
    raise ValueError(k)


def _wrap(s, top):
    return s if top else f"({s})"


# --- proofs ---------------------------------------------------------------


def proof(pf):
    t = pf["t"]

    if t == "hyp":
        return pf["name"]

    if t == "ax":
        if not pf["args"]:
            return pf["name"]
        return "(" + pf["name"] + " " + " ".join(term(a) for a in pf["args"]) + ")"

    if t == "mp":
        return f"({proof(pf['fn'])} {proof(pf['arg'])})"

    if t == "lam":
        return f"(fun ({pf['hyp']} : {formula(pf['prop'], top=True)}) => {proof(pf['body'])})"

    if t == "andI":
        return f"(And.intro {proof(pf['lhs'])} {proof(pf['rhs'])})"
    if t == "andL":
        return f"(And.left {proof(pf['p'])})"
    if t == "andR":
        return f"(And.right {proof(pf['p'])})"

    if t == "orL":
        return f"(Or.inl {proof(pf['p'])})"
    if t == "orR":
        return f"(Or.inr {proof(pf['p'])})"

    if t == "orE":
        return (
            f"(Or.elim {proof(pf['src'])} "
            f"(fun {pf['hyp0']} => {proof(pf['body0'])}) "
            f"(fun {pf['hyp1']} => {proof(pf['body1'])}))"
        )

    if t == "exI":
        parts = [term(w) for w in pf["witnesses"]] + [proof(pf["body"])]
        return "⟨" + ", ".join(parts) + "⟩"

    if t == "exE":
        # `∃ x y z, A` is nested Exists, so the elimination nests too. Only the
        # innermost binder gets the caller's hypothesis name; the intermediate
        # ones bind the remaining existentials and are consumed immediately.
        consts, h = pf["consts"], pf["hyp"]
        n = len(consts)
        sources = [proof(pf["src"])] + [f"{h}_{i}" for i in range(n - 1)]
        binders = [f"{h}_{i}" for i in range(n - 1)] + [h]
        expr = proof(pf["body"])
        for i in range(n - 1, -1, -1):
            expr = f"(Exists.elim {sources[i]} (fun {consts[i]} {binders[i]} => {expr}))"
        return expr

    if t == "gen":
        binds = " ".join(f"({c} : {SORT})" for c in pf["consts"])
        return f"(fun {binds} => {proof(pf['body'])})"

    if t == "eqRefl":
        return "rfl"
    if t == "eqSymm":
        return f"(Eq.symm {proof(pf['p'])})"
    if t == "eqSubst":
        motive = f"(fun ({pf['mvar']} : {SORT}) => {formula(pf['mbody'], top=True)})"
        return f"(Eq.subst (motive := {motive}) {proof(pf['eq'])} {proof(pf['p'])})"

    if t == "absurd":
        return f"(absurd {proof(pf['p'])} {proof(pf['np'])})"

    raise ValueError(f"cannot emit proof node {t!r}")


def theorem(name, statement, pf):
    return f"theorem {name} : {formula(statement, top=True)} :=\n  {proof(pf)}\n"
