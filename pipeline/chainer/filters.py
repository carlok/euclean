"""Which generated consequences are worth keeping.

Every rejection returns a reason and the caller records it. That matters: if the
corpus turns out to be dull, we need to be able to tell whether the generator
never produced anything better or whether the filter threw it away.

Deliberately not filtered: short or easy results. A one-step lemma can still be
the hub of a cluster, and §5 of the brief warns against discarding them.
"""

from ..canon import normalize as N
from ..kernel import formula as F


def _split(stmt):
    body = stmt["body"] if stmt["kind"] == "forall" else stmt
    return F.premises(body)


def conclusion_core(stmt):
    """The conclusion, with any leading ∃ block stripped."""
    _, concl = _split(stmt)
    return concl["body"] if concl["kind"] == "exists" else concl


def _rebuild(stmt, premises, concl):
    out = concl
    for p in reversed(premises):
        out = F.Imp(p, out)
    return F.Forall(stmt["vars"], out) if stmt["kind"] == "forall" else out


def weakening_of_known(stmt, known):
    """True if some hypothesis can be dropped and the result is already proved.

    This is the filter that earns its keep. Forward chaining produces the same
    core fact over and over with a different irrelevant disequality bolted on
    each time; canonical dedup cannot see through that, because the statements
    really are different. Comparing against the stronger version can.

    Callers must feed statements in order of increasing hypothesis count, or
    the stronger form will not have been recorded yet.
    """
    premises, concl = _split(stmt)
    if not premises:
        return False
    for i in range(len(premises)):
        reduced = premises[:i] + premises[i + 1 :]
        if N.key(_rebuild(stmt, reduced, concl)) in known:
            return True
    return False


def irrelevant_hypothesis(stmt):
    """A hypothesis sharing no variable with the conclusion or any other
    hypothesis is not participating in the theorem."""
    premises, concl = _split(stmt)
    if len(premises) < 1:
        return False
    concl_vars = F.free_vars(concl)
    for i, p in enumerate(premises):
        others = set()
        for j, q in enumerate(premises):
            if j != i:
                others |= F.free_vars(q)
        if not (F.free_vars(p) & (concl_vars | others)):
            return True
    return False


def refuted_premises(theory):
    """Atoms the axioms forbid outright, as matchable patterns.

    Only the shape `∀x⃗. ¬A(x⃗)` counts. That is the whole check: a general test
    for whether a premise set is satisfiable is not available here, but the case
    where a single premise instantiates a flatly forbidden atom is one
    comparison and covers the failure actually observed.
    """
    out = []
    for stmt in theory.env.values():
        body = stmt["body"] if stmt["kind"] == "forall" else stmt
        premises, concl = F.premises(body)
        if premises or concl["kind"] != "not":
            continue
        inner = concl["arg"]
        if inner["kind"] == "atom":
            out.append(inner)
    return out


def _instantiates(pattern, atom):
    """Does `atom` match `pattern`, treating the pattern's variables as holes?

    A hole may repeat, and then the argument it stands for must repeat too:
    `¬Lt a a` forbids `Lt x x` for any x, but says nothing about `Lt x y`.
    """
    if atom["kind"] != "atom" or atom["rel"] != pattern["rel"]:
        return False
    if len(atom["args"]) != len(pattern["args"]):
        return False
    bound = {}
    for hole, arg in zip(pattern["args"], atom["args"]):
        if hole["kind"] != "var":
            return False
        key = hole["name"]
        seen = bound.setdefault(key, arg)
        if F.key(seen) != F.key(arg):
            return False
    return True


def vacuous_premise(stmt, refuted):
    """True when a premise is an instance of something the axioms forbid.

    Such a statement is true because its hypotheses can never hold. The kernel
    accepts it, it is perfectly correct, and it says nothing. An earlier version
    of this defect -- assumed atoms contradicting each other -- was caught at
    seed time; this is the derived case, which nothing checked.
    """
    if not refuted:
        return False
    premises, _ = _split(stmt)
    for p in premises:
        core = p["arg"] if p["kind"] == "not" else p
        if any(_instantiates(pat, core) for pat in refuted):
            return True
    return False


def assess(stmt, axiom_keys, seen_keys, refuted=()):
    """Returns (keep, reason). `reason` explains the verdict either way."""
    ck = N.key(stmt)

    if ck in seen_keys:
        return False, "duplicate"

    if ck in axiom_keys:
        return False, "axiom-restated"

    if vacuous_premise(stmt, refuted):
        return False, "vacuous-premise"

    premises, concl = _split(stmt)
    prem_keys = {F.key(p) for p in premises}

    if F.key(concl) in prem_keys:
        return False, "assumption-restated"

    core = concl["body"] if concl["kind"] == "exists" else concl
    if core["kind"] == "eq" and F.key(core["lhs"]) == F.key(core["rhs"]):
        return False, "trivial-equation"

    if concl["kind"] == "exists":
        bound = set(concl["vars"])
        mentioned = F.free_vars(core) | {c for c in F.constants(core)}
        # nothing but the freshly bound witnesses appears in the conclusion, so
        # the hypotheses are along for the ride rather than doing any work
        if premises and mentioned <= bound:
            return False, "unanchored-existential"

    if irrelevant_hypothesis(stmt):
        return False, "irrelevant-hypothesis"

    if weakening_of_known(stmt, seen_keys) or weakening_of_known(stmt, axiom_keys):
        return False, "weaker-than-known"

    if concl["kind"] == "or":
        parts = []
        g = concl
        while g["kind"] == "or":
            parts.append(F.key(g["lhs"]))
            g = g["rhs"]
        parts.append(F.key(g))
        if any(p in prem_keys for p in parts):
            return False, "disjunction-weakening"

    return True, "kept"


def axiom_key_set(theory):
    return {N.key(s) for s in theory.env.values()}
