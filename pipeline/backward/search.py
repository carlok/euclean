"""Goal-directed search: can this specific statement be derived?

Not a general prover, and the narrowness is the design. Every place this project
needs proving, it needs the same one-bit answer — is *this* statement reachable
within budget — and that is far cheaper than a prover that explores.

Forward saturation answers it badly. It explores outward from the axioms and
hopes to land on the goal; measured against statements already known true, it
recovers 18%. That number is what makes conjecture yield unreadable and the
negative half of the minimality tests weak, so it is the number this module has
to move. If it does not, this module should be deleted rather than kept.

Proof terms are built with the same `kernel/proof.py` constructors as everything
else, so anything found here is checkable by exactly the same path — no separate
trust story.
"""

import time

from ..kernel import formula as F, proof as P
from . import unify as U


class Budget:
    __slots__ = ("depth", "steps", "deadline", "used")

    def __init__(self, depth=6, steps=40000, seconds=10.0):
        self.depth = depth
        self.steps = steps
        self.deadline = time.monotonic() + seconds
        self.used = 0

    def spend(self):
        self.used += 1
        return self.used <= self.steps and time.monotonic() < self.deadline


def _rules(env):
    """(name, premises, conclusion, binder count) for each usable rule."""
    out = []
    for name, stmt in env.items():
        if stmt["kind"] == "forall":
            body, fresh = stmt["body"], stmt["vars"]
        else:
            body, fresh = stmt, []
        premises, concl = F.premises(body)
        out.append((name, premises, concl, fresh))
    return out


def prove(goal, env, facts=None, budget=None, tag=0):
    """Return a proof term for `goal`, or None.

    `facts` maps a formula key to a proof term for it — assumptions and anything
    already established. Depth-first with iterative deepening applied by the
    caller, which keeps the recursion honest about its own limit.
    """
    budget = budget or Budget()
    facts = facts or {}
    return _prove(goal, env, facts, budget, budget.depth, [tag])


def _prove(goal, env, facts, budget, depth, counter):
    if not budget.spend():
        return None

    key = F.key(goal)
    if key in facts:
        return facts[key]

    if depth <= 0:
        return None

    # conjunction and existential goals decompose without touching a rule
    if goal["kind"] == "and":
        left = _prove(goal["lhs"], env, facts, budget, depth - 1, counter)
        if left is None:
            return None
        right = _prove(goal["rhs"], env, facts, budget, depth - 1, counter)
        return P.AndI(left, right) if right is not None else None

    for name, premises, concl, binders in _rules(env):
        counter[0] += 1
        renamed_concl, fresh = concl, binders
        if binders:
            stmt = env[name]
            body, fresh = U.rename_apart(stmt, counter[0])
            premises_r, renamed_concl = F.premises(body)
        else:
            premises_r = premises

        sub = U.unify(renamed_concl, goal, {})
        if sub is None:
            continue

        # every binder must be pinned by the unification, or the instantiation
        # is not determined and the proof term cannot be written
        args, ok = [], True
        for v in fresh:
            bound = U.walk(F.Var(v), sub)
            if bound["kind"] == "var":
                ok = False
                break
            args.append(bound)
        if not ok:
            continue

        # A premise may still carry variables that unifying the conclusion did
        # not pin — every rule of the form `P(a,b,c,d) → P(a,b,e,f) → P(c,d,e,f)`
        # leaves its first pair free. Refusing those outright disabled the
        # transitivity-shaped axioms entirely, which are most of the useful
        # ones, and held recall exactly at the forward prover's 18%.
        #
        # Instead the free variables are instantiated from the constants already
        # in play. That is a bounded enumeration, not a general solution: it
        # finds proofs whose intermediate terms are drawn from the goal, and
        # misses any that need a term from nowhere.
        pool = sorted(F.constants(goal) | {c for c in F.constants(F.Forall([], goal))})
        if not pool:
            pool = ["g0"]

        subproofs = _discharge(premises_r, sub, env, facts, budget, depth, counter, pool)
        if subproofs is None:
            continue

        term = P.Ax(name, args) if fresh else P.Ax(name, [])
        for pf in subproofs:
            term = P.MP(term, pf)
        return term

    return None


def _discharge(premises, sub, env, facts, budget, depth, counter, pool, index=0):
    """Prove each premise, enumerating any variables the conclusion left free."""
    if index == len(premises):
        return []
    goal = U.apply(premises[index], sub)
    free = sorted(F.free_vars(goal))

    if not free:
        pf = _prove(goal, env, facts, budget, depth - 1, counter)
        if pf is None:
            return None
        rest = _discharge(premises, sub, env, facts, budget, depth, counter, pool, index + 1)
        return None if rest is None else [pf] + rest

    if len(free) > 2:
        return None  # the enumeration is bounded on purpose
    import itertools

    for choice in itertools.product(pool, repeat=len(free)):
        if not budget.spend():
            return None
        extended = dict(sub)
        for v, c in zip(free, choice):
            extended[v] = F.Const(c)
        ground = U.apply(premises[index], extended)
        if F.free_vars(ground):
            continue
        pf = _prove(ground, env, facts, budget, depth - 1, counter)
        if pf is None:
            continue
        rest = _discharge(premises, extended, env, facts, budget, depth, counter, pool, index + 1)
        if rest is not None:
            return [pf] + rest
    return None


def prove_closed(stmt, env, seconds=10.0, max_depth=7):
    """Prove a closed ∀-statement by fixing its binders and discharging premises.

    Iterative deepening: a shallow proof is found at a shallow limit, and the
    expensive depths are only paid for when nothing shallower works.
    """
    binders = stmt["vars"] if stmt["kind"] == "forall" else []
    body = stmt["body"] if stmt["kind"] == "forall" else stmt
    consts = [f"g{i}" for i in range(len(binders))]
    grounded = F.subst(body, {v: F.Const(c) for v, c in zip(binders, consts)})

    premises, goal = F.premises(grounded)
    facts = {}
    hyp_names = []
    for i, prem in enumerate(premises):
        h = f"bh{i}"
        hyp_names.append((h, prem))
        facts[F.key(prem)] = P.Hyp(h)

    started = time.monotonic()
    for depth in range(1, max_depth + 1):
        left = seconds - (time.monotonic() - started)
        if left <= 0:
            return None
        pf = prove(goal, env, facts, Budget(depth=depth, seconds=left))
        if pf is None:
            continue
        for h, prem in reversed(hyp_names):
            pf = P.Lam(h, prem, pf)
        if consts:
            pf = P.Gen(consts, pf)
        return pf
    return None
