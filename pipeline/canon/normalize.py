"""Canonical form for statements.

Clustering raw Lean text would mostly rediscover the emitter's habits, so
superficial differences are normalized away first: binder names, the order of
independent hypotheses, hypotheses stated twice, and binders that bind nothing.

Both forms are kept downstream. The canonical form decides identity; the raw
form is what Lean checked and what a human reads.
"""

from ..kernel import formula as F


def drop_vacuous(f):
    """Remove quantifier binders that do not occur in their body."""
    k = f["kind"]
    if k in ("var", "const", "atom", "eq"):
        return f
    if k == "not":
        return F.Not(drop_vacuous(f["arg"]))
    if k in F.BINARY:
        return {"kind": k, "lhs": drop_vacuous(f["lhs"]), "rhs": drop_vacuous(f["rhs"])}
    if k in F.QUANT:
        body = drop_vacuous(f["body"])
        used = F.free_vars(body)
        kept = [v for v in f["vars"] if v in used]
        return {"kind": k, "vars": kept, "body": body} if kept else body
    raise ValueError(k)


def dedupe_premises(f):
    """`A → A → B` and `A → B` say the same thing; keep one copy."""
    k = f["kind"]
    if k in F.QUANT:
        return {"kind": k, "vars": list(f["vars"]), "body": dedupe_premises(f["body"])}
    if k != "imp":
        return f
    ps, concl = F.premises(f)
    seen, kept = set(), []
    for p in ps:
        key = F.key(p)
        if key not in seen:
            seen.add(key)
            kept.append(p)
    out = dedupe_premises(concl)
    for p in reversed(kept):
        out = F.Imp(p, out)
    return out


def sort_premises(f):
    """Hypotheses of an implication chain are unordered; impose one."""
    k = f["kind"]
    if k in F.QUANT:
        return {"kind": k, "vars": list(f["vars"]), "body": sort_premises(f["body"])}
    if k != "imp":
        return f
    ps, concl = F.premises(f)
    ps = sorted(ps, key=lambda p: repr(F.key(p)))
    out = sort_premises(concl)
    for p in reversed(ps):
        out = F.Imp(p, out)
    return out


def alpha_normalize(f, prefix="b"):
    """Rename every bound variable to b0, b1, ... in order of first encounter."""
    counter = [0]

    def go(g, env):
        k = g["kind"]
        if k == "var":
            return F.Var(env.get(g["name"], g["name"]))
        if k == "const":
            return dict(g)
        if k == "atom":
            return F.Atom(g["rel"], [go(a, env) for a in g["args"]])
        if k == "eq":
            return F.Eq(go(g["lhs"], env), go(g["rhs"], env))
        if k == "not":
            return F.Not(go(g["arg"], env))
        if k in F.BINARY:
            return {"kind": k, "lhs": go(g["lhs"], env), "rhs": go(g["rhs"], env)}
        if k in F.QUANT:
            inner = dict(env)
            names = []
            for v in g["vars"]:
                nv = f"{prefix}{counter[0]}"
                counter[0] += 1
                inner[v] = nv
                names.append(nv)
            return {"kind": k, "vars": names, "body": go(g["body"], inner)}
        raise ValueError(k)

    return go(f, {})


def canonical(f):
    """Two passes: names must settle before hypotheses can be ordered by name,
    and ordering them changes which names come first."""
    g = dedupe_premises(drop_vacuous(f))
    g = alpha_normalize(g)
    g = sort_premises(g)
    return alpha_normalize(g)


def key(f):
    return F.key(canonical(f))
