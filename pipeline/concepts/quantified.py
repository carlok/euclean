"""Concept candidates that can say `there exists`.

Sprint 3 asked where candidates come *from* — statement syntax, or recurring
proof roles — and got a null both ways. It never asked what a candidate can
*say*. `invent.candidates` builds conjunctions of hypotheses over individuals
and nothing else, while every notion withheld from the system needs a
quantifier to state at all. So the language, not the source, is the last
untested explanation for why concept invention fails here.

A candidate is `∃z. φ(x⃗, z)`: a recurring conjunction in which one variable is
local to the pattern and the rest are parameters.

## The bridges, which is where this can silently fail

Elimination is `C x⃗ → ∃z. φ`, and the engine consumes that through `ExE` the
same way it consumes any derived existential.

Introduction must **not** be written `∃z. φ → C x⃗`. That rule has an
existential premise; `chainer/matching.py` files facts under `('atom', rel)` and
an existential premise looks in `('exists',)`, a bucket nothing is ever filed
under. The rule would sit in the environment, match nothing, contribute nothing,
and report nothing — which is exactly how the rejected control's identity axiom
died, discovered only after a sprint had been spent on it.

Curried over the witness instead — `∀ x⃗ z, φ(x⃗, z) → C x⃗` — the premises are
atomic and therefore matchable, and the proof is `fun … h => ⟨z, h⟩`.

`liveness` exists so this is checked rather than trusted.
"""

import itertools
from collections import Counter, defaultdict

from ..canon import normalize as N
from ..kernel import emit, formula as F
from .invent import abstract, conjuncts


def _premises(stmt):
    body = stmt["body"] if stmt["kind"] == "forall" else stmt
    return F.premises(body)[0]


def candidates(records, min_support=8, max_params=5, max_conjuncts=3):
    """Recurring conjunctions with one variable abstracted existentially.

    The abstracted variable is chosen, not guessed: it is the one appearing in
    more than one conjunct but in no other hypothesis of the theorem — local to
    the pattern and nowhere else, which is what makes it a witness rather than a
    parameter. A pattern with no such variable is not a quantified concept and
    is left to the ordinary miner.
    """
    support = Counter()
    holders = defaultdict(set)
    shapes = {}

    for r in records:
        ps = _premises(r["statement_ast"])
        if len(ps) < 2:
            continue
        for width in range(2, min(max_conjuncts, len(ps)) + 1):
            for combo in itertools.combinations(ps, width):
                inside = set()
                for c in combo:
                    inside |= F.free_vars(c)
                outside = set()
                for q in ps:
                    if all(F.key(q) != F.key(c) for c in combo):
                        outside |= F.free_vars(q)
                concl = F.premises(
                    r["statement_ast"]["body"]
                    if r["statement_ast"]["kind"] == "forall"
                    else r["statement_ast"]
                )[1]
                outside |= F.free_vars(concl)

                local = [
                    v
                    for v in sorted(inside - outside)
                    if sum(1 for c in combo if v in F.free_vars(c)) > 1
                ]
                if len(local) != 1:
                    continue
                witness = local[0]

                conj = combo[-1]
                for c in reversed(combo[:-1]):
                    conj = F.And(c, conj)

                body, params = abstract(N.canonical(conj))
                # `abstract` renamed everything positionally; find where the
                # witness landed by re-deriving the same first-occurrence order
                order = _first_occurrence_order(N.canonical(conj))
                if witness not in order:
                    continue
                wparam = f"x{order.index(witness)}"
                params = [p for p in params if p != wparam]
                if not params or len(params) > max_params:
                    continue

                quantified = F.Exists([wparam], body)
                key = repr(F.key(quantified))
                support[key] += 1
                holders[key].add(r["id"])
                shapes[key] = (quantified, params, wparam)

    return [
        {
            "key": k,
            "body": shapes[k][0],
            "params": shapes[k][1],
            "witness": shapes[k][2],
            "support": v,
            "theorems": sorted(holders[k]),
            "source": "quantified",
        }
        for k, v in support.items()
        if v >= min_support
    ]


def _first_occurrence_order(formula):
    order = []

    def walk(f):
        k = f["kind"]
        if k == "var":
            if f["name"] not in order:
                order.append(f["name"])
        elif k == "atom":
            for a in f["args"]:
                walk(a)
        elif k == "eq":
            walk(f["lhs"])
            walk(f["rhs"])
        elif k == "not":
            walk(f["arg"])
        elif k in F.BINARY:
            walk(f["lhs"])
            walk(f["rhs"])
        elif k in F.QUANT:
            walk(f["body"])

    walk(formula)
    return order


def emit_definition(name, quantified, params, sort="Obj"):
    binders = " ".join(f"({p} : {sort})" for p in params)
    return f"def {name} {binders} : Prop :=\n  {emit.formula(quantified, top=True)}\n"


def emit_bridges(name, quantified, params, witness, sort="Obj"):
    """Elimination as stated; introduction curried over the witness."""
    args = " ".join(params)
    all_binders = " ".join(f"({p} : {sort})" for p in params)
    parts = conjuncts(quantified["body"])

    elim = (
        f"theorem {name}_elim {all_binders} : {name} {args} → "
        f"{emit.formula(quantified, top=True)} :=\n  fun h => h\n"
    )

    # ∀ x⃗ z, φ₁ → … → φₖ → C x⃗ — atomic premises, so the engine can match them
    intro_binders = " ".join(f"({p} : {sort})" for p in params + [witness])
    chain = "".join(f"{emit.formula(p)} → " for p in parts)
    lam = "".join(f"fun h{i} => " for i in range(len(parts)))
    wit = f"h{len(parts) - 1}"
    for i in range(len(parts) - 2, -1, -1):
        wit = f"(And.intro h{i} {wit})"
    intro = (
        f"theorem {name}_intro {intro_binders} : {chain}{name} {args} :=\n"
        f"  {lam}⟨{witness}, {wit}⟩\n"
    )
    return intro, [elim]


def bridge_statements(concepts):
    """The bridges as formulas the chainer can use as rules."""
    env, relations = {}, {}
    for c in concepts:
        params, witness = c["params"], c["witness"]
        relations[c["name"]] = len(params)
        head = F.Atom(c["name"], [F.Var(p) for p in params])

        intro = head
        for part in reversed(conjuncts(c["body"]["body"])):
            intro = F.Imp(part, intro)
        env[f"{c['name']}_intro"] = F.Forall(params + [witness], intro)
        env[f"{c['name']}_elim"] = F.Forall(params, F.Imp(head, c["body"]))
    return env, relations


def liveness(theory, concepts, seed=0, cfg=None):
    """Do the bridges actually fire?

    An inert rule produces a slightly smaller corpus and no error, which is
    indistinguishable from ordinary seed variance. The whole design above exists
    to avoid it, so it is measured rather than assumed.
    """
    from ..chainer.engine import Engine
    from ..loop.run import Augmented

    env, rels = bridge_statements(concepts)
    th = Augmented(theory, rels)
    th.env.update(theory.env)

    eng = Engine(th, cfg or {"atom_layout": "fixed", "assume_distinct": True}, seed=seed,
                 extra_env=env)
    rules = {r.name for r in eng.rules}
    eng.saturate()

    used = Counter()
    for fact in eng.facts.values():
        if ":" in fact.origin:
            used[fact.origin.split(":", 1)[1]] += 1

    return [
        {
            "bridge": name,
            "is_rule": name in rules,
            "derivations": used.get(name, 0),
            "inert": name not in rules,
        }
        for name in sorted(env)
    ]
