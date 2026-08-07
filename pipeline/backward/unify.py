"""Two-way unification over formulas.

`chainer/matching.py` matches a pattern against a *ground* fact and is
deliberately one-way — forward saturation never needs more. Backward search
does: a goal carries variables and so does a rule's conclusion, and both sides
may bind.

Same discipline as everywhere else in this project. Equality is treated as a
logical symbol; the relations are not, so no relation is assumed symmetric in
any argument. Whether one is remains something the pipeline is supposed to find
out rather than be told.
"""

from ..kernel import formula as F


def walk(term, sub):
    while term["kind"] == "var" and term["name"] in sub:
        nxt = sub[term["name"]]
        if nxt["kind"] == "var" and nxt["name"] == term["name"]:
            break
        term = nxt
    return term


def occurs(name, term, sub):
    term = walk(term, sub)
    if term["kind"] == "var":
        return term["name"] == name
    return False  # terms here are variables and constants only; no nesting


def unify_term(a, b, sub):
    a, b = walk(a, sub), walk(b, sub)
    if a["kind"] == "var":
        if b["kind"] == "var" and a["name"] == b["name"]:
            return sub
        if occurs(a["name"], b, sub):
            return None
        out = dict(sub)
        out[a["name"]] = b
        return out
    if b["kind"] == "var":
        return unify_term(b, a, sub)
    return sub if a["name"] == b["name"] else None


def unify(a, b, sub=None):
    """Unify two formulas. Returns a substitution or None.

    Quantifiers are compared structurally: two goals differing in binder
    *structure* are not unified, only ones whose bodies unify under matching
    binder counts. That is conservative — it will miss some genuine matches —
    and conservative is the right direction here, since a wrong unification
    produces a proof term the kernel then rejects, wasting a whole search.
    """
    sub = {} if sub is None else sub
    if a["kind"] != b["kind"]:
        return None
    k = a["kind"]
    if k in ("var", "const"):
        return unify_term(a, b, sub)
    if k == "atom":
        if a["rel"] != b["rel"] or len(a["args"]) != len(b["args"]):
            return None
        for x, y in zip(a["args"], b["args"]):
            sub = unify_term(x, y, sub)
            if sub is None:
                return None
        return sub
    if k == "eq":
        s = unify_term(a["lhs"], b["lhs"], sub)
        return unify_term(a["rhs"], b["rhs"], s) if s is not None else None
    if k == "not":
        return unify(a["arg"], b["arg"], sub)
    if k in F.BINARY:
        s = unify(a["lhs"], b["lhs"], sub)
        return unify(a["rhs"], b["rhs"], s) if s is not None else None
    if k in F.QUANT:
        if len(a["vars"]) != len(b["vars"]):
            return None
        return unify(a["body"], b["body"], sub)
    return None


def apply(formula, sub):
    """Resolve a substitution fully through chains before substituting."""
    if not sub:
        return formula
    resolved = {}
    for name in sub:
        resolved[name] = walk(F.Var(name), sub)
    return F.subst(formula, resolved)


def rename_apart(stmt, tag):
    """Give a rule's variables names no goal can collide with."""
    if stmt["kind"] != "forall":
        return stmt, []
    fresh = [f"_{tag}_{v}" for v in stmt["vars"]]
    mapping = {v: F.Var(n) for v, n in zip(stmt["vars"], fresh)}
    return F.subst(stmt["body"], mapping), fresh
