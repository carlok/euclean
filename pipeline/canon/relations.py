"""Relation names that survive re-seeding, so runs can be compared.

Each ensemble configuration re-permutes the opaque identifiers, so `R0` in one
run is `R1` in another. Comparing findings across the grid therefore needs a
name that depends only on structure — and it has to be derivable from the public
theory alone, because the translation table is exactly what the experiment is
not allowed to look at.

Arity does most of the work: a 3-place and a 4-place relation cannot be confused
no matter how they are labelled. When two relations share an arity, they are
ordered by a fingerprint taken from how they occur across the axioms — how many
axioms mention them, in what positions, under what quantifier shapes. That is a
property of the theory's structure, not of anyone's reading of it.
"""

from ..kernel import formula as F


def _occurrence_fingerprint(rel, theory):
    """How a relation sits inside the axiom set, as a sortable structure."""
    rows = []
    for name in sorted(theory.env):
        stmt = theory.env[name]
        binders = len(stmt["vars"]) if stmt["kind"] == "forall" else 0
        body = stmt["body"] if stmt["kind"] == "forall" else stmt
        premises, concl = F.premises(body)
        in_premises = sum(F.relations(p).get(rel, 0) for p in premises)
        in_conclusion = F.relations(concl).get(rel, 0)
        if in_premises or in_conclusion:
            rows.append((binders, len(premises), concl["kind"], in_premises, in_conclusion))
    return (len(rows), tuple(sorted(repr(r) for r in rows)))


def canonical_map(theory):
    """anon name -> `Rel{arity}_{k}`, stable across identifier permutations."""
    by_arity = {}
    for rel, arity in theory.relations.items():
        by_arity.setdefault(arity, []).append(rel)

    mapping = {}
    for arity, rels in by_arity.items():
        ordered = sorted(rels, key=lambda r: _occurrence_fingerprint(r, theory))
        for k, rel in enumerate(ordered):
            mapping[rel] = f"Rel{arity}_{k}"
    return mapping


def apply(f, mapping):
    """Rewrite relation symbols. Unknown symbols pass through — invented
    concepts carry their own names and are compared separately."""
    k = f["kind"]
    if k == "atom":
        return F.Atom(mapping.get(f["rel"], f["rel"]), list(f["args"]))
    if k in ("var", "const", "eq"):
        return f
    if k == "not":
        return F.Not(apply(f["arg"], mapping))
    if k in F.BINARY:
        return {"kind": k, "lhs": apply(f["lhs"], mapping), "rhs": apply(f["rhs"], mapping)}
    if k in F.QUANT:
        return {"kind": k, "vars": list(f["vars"]), "body": apply(f["body"], mapping)}
    raise ValueError(k)


def key(f, mapping):
    """Canonical, seed-independent identity for a statement or concept body."""
    from . import normalize as N

    return N.key(apply(f, mapping))
