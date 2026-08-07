"""One-way matching of rule premises against ground facts.

Only equality is treated as symmetric, and that is deliberate: `=` is a logical
symbol, so exploiting its symmetry assumes nothing about the theory. The two
relations get no such courtesy — whether either of them is symmetric in any of
its arguments is exactly the sort of thing the system is supposed to find out
for itself, not be handed.
"""

from ..kernel import formula as F


def match_term(pat, ground, sub):
    if pat["kind"] == "var":
        prev = sub.get(pat["name"])
        if prev is not None:
            return sub if F.key(prev) == F.key(ground) else None
        out = dict(sub)
        out[pat["name"]] = ground
        return out
    if pat["kind"] == "const":
        return sub if ground["kind"] == "const" and ground["name"] == pat["name"] else None
    return None


def match_formula(pat, fact, sub):
    """Return an extended substitution, or None. `fact` must be ground."""
    pk, fk = pat["kind"], fact["kind"]
    if pk != fk:
        return None
    if pk == "atom":
        if pat["rel"] != fact["rel"] or len(pat["args"]) != len(fact["args"]):
            return None
        for p, g in zip(pat["args"], fact["args"]):
            sub = match_term(p, g, sub)
            if sub is None:
                return None
        return sub
    if pk == "eq":
        s = match_term(pat["lhs"], fact["lhs"], sub)
        if s is not None:
            s = match_term(pat["rhs"], fact["rhs"], s)
        return s
    if pk == "not":
        return match_formula(pat["arg"], fact["arg"], sub)
    if pk in ("and", "or", "imp"):
        s = match_formula(pat["lhs"], fact["lhs"], sub)
        return match_formula(pat["rhs"], fact["rhs"], s) if s is not None else None
    return None


def index_key(f):
    """Cheap bucket key so a premise only sees facts it could conceivably match."""
    k = f["kind"]
    if k == "atom":
        return ("atom", f["rel"])
    if k == "eq":
        return ("eq",)
    if k == "not":
        inner = f["arg"]
        return ("not",) + (("atom", inner["rel"]) if inner["kind"] == "atom" else (inner["kind"],))
    return (k,)
