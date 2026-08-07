"""Symmetry view: what can be permuted without changing the statement.

Two kinds are computed, and they answer different questions.

Variable symmetry asks which of a theorem's own universally quantified
positions are interchangeable. Relation-argument symmetry asks whether a
relation can have two of its argument slots swapped throughout and leave the
statement intact — which, aggregated over the corpus, is how a slot-level
invariance of an opaque relation would become visible without anyone having
been told the relation means anything.

A full automorphism search is exponential in the number of binders, so this
computes the transpositions that work and reports the group they generate.
That under-reports nothing for the shapes seen here — every symmetry found so
far is transposition-generated — but it is an approximation, and callers should
treat it as a lower bound.
"""

import itertools

from ..canon import normalize as N
from ..kernel import formula as F


def _permute_leading_vars(stmt, perm):
    """perm maps binder index -> binder index."""
    if stmt["kind"] != "forall":
        return stmt
    vars_ = stmt["vars"]
    mapping = {vars_[i]: F.Var(vars_[perm[i]]) for i in range(len(vars_))}
    return F.Forall(vars_, F.subst(stmt["body"], mapping))


def variable_transpositions(stmt, limit=10):
    """Pairs of leading ∀ binders that may be swapped."""
    if stmt["kind"] != "forall":
        return []
    n = min(len(stmt["vars"]), limit)
    base = N.key(stmt)
    out = []
    for i, j in itertools.combinations(range(n), 2):
        perm = list(range(len(stmt["vars"])))
        perm[i], perm[j] = perm[j], perm[i]
        if N.key(_permute_leading_vars(stmt, perm)) == base:
            out.append((i, j))
    return out


def _swap_relation_args(f, rel, i, j):
    k = f["kind"]
    if k == "atom":
        if f["rel"] != rel or max(i, j) >= len(f["args"]):
            return f
        args = list(f["args"])
        args[i], args[j] = args[j], args[i]
        return F.Atom(rel, args)
    if k in ("var", "const", "eq"):
        return f
    if k == "not":
        return F.Not(_swap_relation_args(f["arg"], rel, i, j))
    if k in F.BINARY:
        return {
            "kind": k,
            "lhs": _swap_relation_args(f["lhs"], rel, i, j),
            "rhs": _swap_relation_args(f["rhs"], rel, i, j),
        }
    if k in F.QUANT:
        return {"kind": k, "vars": list(f["vars"]), "body": _swap_relation_args(f["body"], rel, i, j)}
    raise ValueError(k)


def relation_transpositions(stmt, relations):
    """Argument slots of a relation that this statement cannot tell apart."""
    base = N.key(stmt)
    out = {}
    for rel, arity in relations.items():
        found = []
        for i, j in itertools.combinations(range(arity), 2):
            if N.key(_swap_relation_args(stmt, rel, i, j)) == base:
                found.append((i, j))
        if found:
            out[rel] = found
    return out


def orbit_signature(transpositions, n):
    """Group the positions the transpositions merge, as a canonical partition."""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in transpositions:
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return tuple(sorted(tuple(sorted(g)) for g in groups.values()))


def describe(stmt, relations):
    n = len(stmt["vars"]) if stmt["kind"] == "forall" else 0
    var_tr = variable_transpositions(stmt)
    rel_tr = relation_transpositions(stmt, relations)
    return {
        "n_binders": n,
        "variable_transpositions": var_tr,
        "variable_orbits": orbit_signature(var_tr, n),
        "relation_transpositions": {r: v for r, v in sorted(rel_tr.items())},
        "symmetry_rank": len(var_tr) + sum(len(v) for v in rel_tr.values()),
    }
