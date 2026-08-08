"""Relation names that survive re-seeding, so runs can be compared.

Each ensemble configuration re-permutes the opaque identifiers, so `R0` in one
run is `R1` in another. Comparing findings across the grid therefore needs a
name that depends only on structure — and it has to be derivable from the public
theory alone, because the translation table is exactly what the experiment is
not allowed to look at.

Arity does most of the work: a 3-place and a 4-place relation cannot be confused
no matter how they are labelled. Two relations of the *same* arity are the hard
case, and the first version of this module got it wrong in a way that would have
been very expensive to discover later.

## Why this is colour refinement and not a fingerprint

The original fingerprint recorded, per axiom, `(binder count, premise count,
conclusion kind, occurrences in premises, occurrences in conclusion)`. Its
docstring claimed it also recorded *argument positions*. It did not, and that
gap is exactly what it needed: for a theory whose two same-arity relations
appear in the same number of axioms in the same syntactic roles, every one of
those numbers ties. `sorted` is stable, so on a tie the order fell through to
the iteration order of the `relations` dict — which is JSON key order, which the
anonymizer permutes per seed. The canonical name of a relation would then depend
on the seed, which is the one thing a canonical name may not do.

That failure was silent and self-confirming. Keys mentioning such a relation
would land in different buckets on different seeds, survival would collapse
toward chance, and the result would read as a clean confirmation that structure
does not survive re-anonymization.

The tie was blindness rather than genuine symmetry: swapping the two relations
does *not* map that axiom set to itself. So the information needed to separate
them was present, and the fingerprint could not see it.

What separates them is not how often a relation occurs but *what it shares
arguments with*. That is a graph question, so this uses the standard answer:
one-dimensional Weisfeiler-Leman refinement. Every relation starts coloured by
arity; a relation's next colour is its current colour plus the multiset of
positional contexts in which it occurs, where the *other* relations in those
contexts are named by their current colours rather than by their identifiers.
Iterating to a fixpoint spreads structural information as far as it will go, and
because no identifier is ever read, the result cannot depend on how the theory
was labelled.

Refinement can still leave two relations sharing a colour. That means the theory
really is symmetric in them, or 1-WL cannot tell — either way there is no
structural ground for an order, so `canonical_map` raises rather than inventing
one from dict order. A canonical map decided by key order is not a canonical
map, and it must not be possible to obtain one by accident.
"""

from ..kernel import formula as F


def _atoms(f, out):
    """Every atom in a formula, in traversal order, as live references."""
    k = f["kind"]
    if k in ("var", "const", "eq"):
        return out
    if k == "atom":
        out.append(f)
        return out
    if k == "not":
        return _atoms(f["arg"], out)
    if k in F.BINARY:
        return _atoms(f["rhs"], _atoms(f["lhs"], out))
    if k in F.QUANT:
        return _atoms(f["body"], out)
    raise ValueError(k)


def _term_id(t):
    """Identity of an argument *within one axiom*.

    Comparing names across axioms would not be safe, but within an axiom the
    anonymizer renames consistently, so two positions holding the same name hold
    the same term. Only this sameness is used, never the name itself.
    """
    return (t["kind"], t["name"])


def _contexts(rel, theory, colour):
    """The positional contexts `rel` occurs in, with neighbours given by colour.

    For each occurrence, each argument position records which *other* positions
    in the same axiom hold the same term, identified by the colour of the
    relation holding them. This is what makes two same-arity relations
    separable: it is the difference between an argument that feeds another
    relation's first position and one that feeds its second.
    """
    rows = []
    for name in sorted(theory.env):
        stmt = theory.env[name]
        binders = len(stmt["vars"]) if stmt["kind"] == "forall" else 0
        body = stmt["body"] if stmt["kind"] == "forall" else stmt
        premises, concl = F.premises(body)

        everywhere = _atoms(body, [])
        for role, part in [("p", p) for p in premises] + [("c", concl)]:
            for atom in _atoms(part, []):
                if atom["rel"] != rel:
                    continue
                signature = []
                for i, arg in enumerate(atom["args"]):
                    here = _term_id(arg)
                    links = sorted(
                        (repr(colour.get(other["rel"], ())), j)
                        for other in everywhere
                        for j, a2 in enumerate(other["args"])
                        if other is not atom and _term_id(a2) == here
                    )
                    signature.append((i, tuple(links)))
                rows.append((role, binders, len(premises), concl["kind"], tuple(signature)))

    # Rows are sorted because axiom *names* are permuted too, so the order in
    # which axioms are visited carries no structural information.
    return (len(rows), tuple(sorted(repr(r) for r in rows)))


def _partition(colour):
    """The equivalence classes a colouring induces, ignoring the colours."""
    classes = {}
    for rel, c in colour.items():
        classes.setdefault(repr(c), set()).add(rel)
    return sorted(sorted(v) for v in classes.values())


def refine(theory):
    """Colour every relation by structure alone. Arity stays the leading term."""
    colour = {rel: (arity, 0) for rel, arity in theory.relations.items()}

    for _ in range(len(colour) + 1):
        signatures = {rel: repr((colour[rel], _contexts(rel, theory, colour))) for rel in colour}
        ranks = {s: i for i, s in enumerate(sorted(set(signatures.values())))}
        nxt = {rel: (theory.relations[rel], ranks[signatures[rel]]) for rel in colour}
        if _partition(nxt) == _partition(colour):
            return nxt
        colour = nxt
    return colour


def canonical_map(theory):
    """anon name -> `Rel{arity}_{k}`, stable across identifier permutations."""
    colour = refine(theory)

    by_arity = {}
    for rel, arity in theory.relations.items():
        by_arity.setdefault(arity, []).append(rel)

    mapping = {}
    for arity, rels in by_arity.items():
        ordered = sorted(rels, key=lambda r: repr(colour[r]))
        for a, b in zip(ordered, ordered[1:]):
            if repr(colour[a]) == repr(colour[b]):
                raise ValueError(
                    f"relations of arity {arity} are indistinguishable after colour "
                    f"refinement, so there is no structural order to canonicalize by. "
                    f"Falling back to declaration order would make the canonical name "
                    f"depend on the seed, which is the one thing it may not do."
                )
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
