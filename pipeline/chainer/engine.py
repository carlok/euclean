"""Bounded forward saturation over the anonymous theory.

The engine keeps one long-lived derivation context: a pool of constants, a set
of optional assumptions, and a stack of scopes opened by eliminating derived
existentials. Facts accumulate in that context. A fact only becomes a *theorem*
when it is extracted, which closes every scope it depends on, discharges just
the assumptions its proof actually used, and generalizes the parameters it
actually mentions.

That last part matters more than it looks: because hypothesis use is read off
the proof term, weakest-hypothesis statements come out for free rather than
having to be searched for.
"""

import itertools
import random
import time
from collections import defaultdict

from ..kernel import formula as F, proof as P
from . import matching as M


class Scope:
    __slots__ = ("consts", "src_proof", "hyp_name", "opened")

    def __init__(self, consts, src_proof, hyp_name, opened):
        self.consts = consts
        self.src_proof = src_proof
        self.hyp_name = hyp_name
        self.opened = opened


class Fact:
    __slots__ = ("formula", "proof", "depth", "origin", "round")

    def __init__(self, formula, pf, depth, origin, rnd):
        self.formula = formula
        self.proof = pf
        self.depth = depth
        self.origin = origin
        self.round = rnd


class Rule:
    __slots__ = ("name", "vars", "premises", "conclusion")

    def __init__(self, name, stmt):
        self.name = name
        if stmt["kind"] == "forall":
            self.vars = list(stmt["vars"])
            body = stmt["body"]
        else:
            self.vars = []
            body = stmt
        self.premises, self.conclusion = F.premises(body)

    @property
    def generative(self):
        return not self.premises


DEFAULTS = {
    "params": 8,
    "assume_distinct": True,       # True/"all" | "subset" | False
    "distinct_fraction": 0.4,
    "assume_atoms": True,
    "atom_layout": "fixed",        # "fixed" reproduces sprint 1 | "random"
    "atoms_per_relation": 3,
    "allow_repeats": True,
    "rounds": 8,
    "max_facts": 6000,
    "max_scopes": 40,
    "derivations_per_rule_per_round": 200,
    "generative_samples": 12,
    "param_bias": 0.85,
    "rewrites_per_equation": 25,
    "match_attempts": 20000,
    "max_case_splits": 12,
    "branch_rounds": 3,
    "case_split_depth": 2,
    "max_case_proof_size": 400,
    # A wall-clock bound belongs in the defaults, not only in the grid budget.
    # Without it the primary single-run command has no bound at all, and a
    # theory whose closure behaves differently can run indefinitely.
    "time_budget": 900,
}


class Engine:
    def __init__(self, theory, config=None, seed=0, extra_env=None):
        self.theory = theory
        self.cfg = {**DEFAULTS, **(config or {})}
        self.rng = random.Random(seed)

        self.env = {**theory.env, **(extra_env or {})}
        self.base_names = set(theory.env)
        self.rules = [Rule(n, s) for n, s in self.env.items()]
        self.rules = [r for r in self.rules if r.premises or r.conclusion["kind"] != "and"]

        self.facts = {}
        self.by_bucket = defaultdict(list)
        self.scopes = []
        self.hyps = []
        self.pending = []
        self.rejected = defaultdict(int)
        self._counter = itertools.count()
        self._round = 0
        self._in_branch = False

        self.params = [f"p{i}" for i in range(self.cfg["params"])]
        self.consts = list(self.params)
        self._seed_context()

    # --- setup ------------------------------------------------------------

    def _seed_context(self):
        ps = [F.Const(p) for p in self.params]

        # Sprint 1 assumed every pair of parameters distinct, and the concept
        # scorer then "discovered" conjunctions of exactly those assumptions.
        # Distinctness is a configuration axis now, not a fixed decision.
        mode = self.cfg["assume_distinct"]
        pairs = list(itertools.combinations(range(len(ps)), 2))
        if mode is True or mode == "all":
            chosen = pairs
        elif mode == "subset":
            k = max(1, int(len(pairs) * self.cfg["distinct_fraction"]))
            chosen = self.rng.sample(pairs, k)
        else:
            chosen = []
        for i, j in chosen:
            self._assume(F.Not(F.Eq(ps[i], ps[j])))

        # Assumed atoms are the whole parameter-only track. With a single atom
        # per relation the only thing two premises can match against is that
        # atom and itself, which yields reflexivity and then stops; two
        # overlapping atoms per relation is what lets composition laws appear.
        for rel, idxs in self._assumed_atom_layout():
            self._assume(F.Atom(rel, [ps[i] for i in idxs]))

        # axioms that are bare existentials are context, not rules: open them
        # once at the start so their witnesses join the constant pool
        for rule in list(self.rules):
            if rule.name not in self.base_names:
                continue
            if rule.generative and rule.conclusion["kind"] == "exists" and not rule.vars:
                self.rules.remove(rule)
                self._integrate(rule.conclusion, P.Ax(rule.name, []), f"seed:{rule.name}")

    def _assumed_atom_layout(self):
        """Which atoms over the parameters are assumed.

        `fixed` reproduces sprint 1: two overlapping tuples per relation, sharing
        a prefix so chaining rules have something to chain.

        `random` samples argument tuples instead, and — this is the part that
        matters — allows an argument to repeat within a tuple. A tuple like
        (0, 1, 0, 2) yields an atom of the form `R a b a c`, which the fixed
        layout can never produce and which is precisely what the axiom with the
        disjunctive conclusion needs as a premise. Sprint 1 produced zero
        disjunctions partly for this reason.
        """
        if self.cfg["assume_atoms"] is False:
            return []
        n = len(self.params)
        rels = [(r, a) for r, a in sorted(self.theory.relations.items()) if a <= n]

        if self.cfg["atom_layout"] == "fixed":
            out = []
            for rel, arity in rels:
                out.append((rel, list(range(arity))))
                shifted = [(i + arity) % n for i in range(arity)]
                if arity * 2 <= n:
                    second = list(range(arity - arity // 2, arity - arity // 2 + arity))
                    out.append((rel, [i % n for i in second]))
                elif shifted != list(range(arity)):
                    out.append((rel, shifted))
            return out

        out, seen = [], set()
        for rel, arity in rels:
            for _ in range(self.cfg["atoms_per_relation"]):
                for _attempt in range(12):
                    if self.cfg["allow_repeats"]:
                        tup = [self.rng.randrange(n) for _ in range(arity)]
                    else:
                        tup = self.rng.sample(range(n), arity)
                    key = (rel, tuple(tup))
                    if key not in seen:
                        seen.add(key)
                        out.append((rel, tup))
                        break
        return out

    def _contradicts_assumptions(self, atom):
        """Would assuming this atom make the assumption set unsatisfiable?

        The randomized layout samples argument tuples with repetition, which is
        what lets it reach shapes the fixed layout cannot. It also lets it draw
        an atom that an axiom turns straight into an equality the disequality
        assumptions deny. A context like `R0 p3 p2 p3` alongside `¬(p3 = p2)`
        is inconsistent, and inconsistent premises make every theorem derived
        under them vacuously true — valid, kernel-accepted, and empty.

        Sprint 2 shipped without this check. It cost 16% of the grid corpus.

        The test is deliberately syntactic and local: for each axiom of the form
        `R(...) → x = y`, see whether this atom is an instance whose conclusion
        is already denied. That catches the one-step case, which is the one the
        sampler actually produces. Deeper inconsistencies are not detected and
        this does not claim to make the context consistent.
        """
        denied = {
            tuple(sorted((f["arg"]["lhs"]["name"], f["arg"]["rhs"]["name"])))
            for _, f in self.hyps
            if f["kind"] == "not" and f["arg"]["kind"] == "eq"
        }
        if not denied:
            return None

        for name in self.base_names:
            stmt = self.theory.env[name]
            if stmt["kind"] != "forall":
                continue
            premises, concl = F.premises(stmt["body"])
            if concl["kind"] != "eq" or len(premises) != 1 or premises[0]["kind"] != "atom":
                continue
            sub = M.match_formula(premises[0], atom, {})
            if sub is None:
                continue
            lhs, rhs = concl["lhs"], concl["rhs"]
            if lhs["name"] not in sub or rhs["name"] not in sub:
                continue
            a, b = sub[lhs["name"]], sub[rhs["name"]]
            if a["kind"] != "const" or b["kind"] != "const":
                continue
            if tuple(sorted((a["name"], b["name"]))) in denied:
                return name
        return None

    def _assume(self, formula):
        if formula["kind"] == "atom":
            culprit = self._contradicts_assumptions(formula)
            if culprit is not None:
                self.rejected[f"inconsistent-assumption:{culprit}"] += 1
                return
        name = f"h{len(self.hyps)}"
        self.hyps.append((name, formula))
        self._add(formula, P.Hyp(name), "assumption")

    # --- facts ------------------------------------------------------------

    def _add(self, formula, pf, origin):
        key = F.key(formula)
        if key in self.facts:
            return None
        if len(self.facts) >= self.cfg["max_facts"]:
            # Counted, not silent. This is the cap that binds hardest on a
            # richer theory, and until it was recorded a member pinned at the
            # ceiling was indistinguishable in every artifact from one that had
            # simply run out of things to derive.
            self.rejected["max-facts"] += 1
            return None
        fact = Fact(formula, pf, len(self.scopes), origin, self._round)
        self.facts[key] = fact
        self.by_bucket[M.index_key(formula)].append(fact)
        self.pending.append(fact)
        if formula["kind"] == "eq":
            self._on_equation(fact)
        return fact

    def _integrate(self, formula, pf, origin):
        """Break a derived conclusion down into the facts it really contains."""
        k = formula["kind"]
        if k == "and":
            self._integrate(formula["lhs"], P.AndL(pf), origin)
            self._integrate(formula["rhs"], P.AndR(pf), origin)
            return
        if k == "exists":
            if self._in_branch:
                self.rejected["branch-existential-skipped"] += 1
                return
            if len(self.scopes) >= self.cfg["max_scopes"]:
                self.rejected["scope-limit"] += 1
                return
            n = next(self._counter)
            consts = [f"s{n}_{i}" for i in range(len(formula["vars"]))]
            hyp_name = f"e{n}"
            opened = F.open_exists(formula, consts)
            self.scopes.append(Scope(consts, pf, hyp_name, opened))
            self.consts.extend(consts)
            self._integrate(opened, P.Hyp(hyp_name), origin)
            return
        self._add(formula, pf, origin)

    def _on_equation(self, fact):
        """A derived equation collapses constants, so propagate it."""
        lhs, rhs = fact.formula["lhs"], fact.formula["rhs"]
        if lhs["kind"] != "const" or rhs["kind"] != "const":
            return
        if lhs["name"] == rhs["name"]:
            return
        self._add(F.Eq(rhs, lhs), P.EqSymm(fact.proof), "eq-symm")
        budget = self.cfg["rewrites_per_equation"]
        targets = [f for f in list(self.facts.values()) if rhs["name"] in F.constants(f.formula)]
        self.rng.shuffle(targets)
        for target in targets[:budget]:
            # Rewriting recurses back into itself and is the dominant cost for
            # any equational theory, so the round-boundary deadline is too
            # coarse to bound it.
            if self._past_deadline():
                break
            if target is fact:
                continue
            z = "z"
            motive = F.subst_consts(target.formula, {rhs["name"]: F.Var(z)})
            rewritten = F.subst_consts(target.formula, {rhs["name"]: lhs})
            if F.key(rewritten) in self.facts:
                continue
            self._add(
                rewritten,
                P.EqSubst(P.EqSymm(fact.proof), z, motive, target.proof),
                "rewrite",
            )

    # --- case analysis ----------------------------------------------------

    def _past_deadline(self):
        d = getattr(self, "_deadline", None)
        return d is not None and time.monotonic() > d

    def _snapshot(self):
        return (
            set(self.facts),
            {k: len(v) for k, v in self.by_bucket.items()},
            len(self.consts),
            list(self.pending),
        )

    def _restore(self, snap):
        keys, bucket_lens, nconsts, pending = snap
        for k in list(self.facts):
            if k not in keys:
                del self.facts[k]
        for k, v in list(self.by_bucket.items()):
            del v[bucket_lens.get(k, 0) :]
        del self.consts[nconsts:]
        self.pending = pending

    def _explore_branch(self, disjunct, hyp_name, rounds):
        """Saturate under an assumed disjunct, then roll the state back.

        Returns {fact key: (formula, proof)} for everything the branch derived
        that was not already known. Scope opening is disabled inside a branch:
        a witness introduced under a case hypothesis would carry that hypothesis
        into its scope, and untangling that is not worth what it would buy.
        """
        snap = self._snapshot()
        self._in_branch = True
        try:
            self._add(disjunct, P.Hyp(hyp_name), "case-hypothesis")
            before = set(self.facts)
            for _ in range(rounds):
                new_facts, self.pending = self.pending, []
                if not new_facts:
                    break
                for rule in self.rules:
                    if not rule.generative:
                        self._fire(rule, new_facts)
            derived = {
                k: (f.formula, f.proof)
                for k, f in self.facts.items()
                if k not in before or k == F.key(disjunct)
            }
            derived.pop(F.key(disjunct), None)
        finally:
            self._in_branch = False
            self._restore(snap)
        return derived

    def _case_split(self, fact, depth=0):
        """Derive what holds regardless of which side of a disjunction is true.

        Both branches have to reach the same statement for it to be exported.
        That is the whole point: a fact proved in only one branch is conditional
        on that branch, and only a fact proved in both is unconditional.
        """
        if depth >= self.cfg["case_split_depth"]:
            return 0
        formula = fact.formula
        if formula["kind"] != "or":
            return 0

        h0, h1 = f"c{next(self._counter)}", f"c{next(self._counter)}"
        left = self._explore_branch(formula["lhs"], h0, self.cfg["branch_rounds"])
        right = self._explore_branch(formula["rhs"], h1, self.cfg["branch_rounds"])

        # A case-analysis term carries both branch proofs whole, so nesting
        # splits multiplies term size rather than adding to it. Left unbounded
        # this does not merely slow saturation down — the cost lands later, in
        # extraction and emission, which walk the term repeatedly and are
        # outside any saturation deadline. Capping the combined size here is the
        # only place that actually bounds it.
        cap = self.cfg["max_case_proof_size"]
        exported = 0
        for key in set(left) & set(right):
            if key in self.facts:
                continue
            goal, p0 = left[key]
            _, p1 = right[key]
            if P.size(p0) + P.size(p1) > cap:
                self.rejected["case-proof-too-large"] += 1
                continue
            pf = P.OrE(fact.proof, h0, p0, h1, p1, goal)
            if self._add(goal, pf, "case-analysis"):
                exported += 1
        return exported

    def _run_case_splits(self):
        """Each split runs two nested branch saturations, so the round-boundary
        time check is too coarse to bound this: one round can spend minutes
        here. The deadline is therefore checked per split as well."""
        done = getattr(self, "_split_done", None)
        if done is None:
            done = self._split_done = set()
        budget = self.cfg["max_case_splits"]
        produced = 0
        for key, fact in list(self.facts.items()):
            if budget <= 0 or self._past_deadline():
                break
            if key in done or fact.formula["kind"] != "or":
                continue
            done.add(key)
            budget -= 1
            produced += self._case_split(fact)
        return produced

    # --- saturation -------------------------------------------------------

    def _candidates(self, pattern, pool):
        bucket = M.index_key(pattern)
        return pool.get(bucket, ())

    def _fire(self, rule, new_facts):
        """Try to apply `rule`, requiring at least one premise to hit a new fact."""
        all_pool = self.by_bucket
        new_pool = defaultdict(list)
        for f in new_facts:
            new_pool[M.index_key(f.formula)].append(f)

        derived = 0
        limit = self.cfg["derivations_per_rule_per_round"]
        attempts = [0]

        for pivot in range(len(rule.premises)):
            if derived >= limit:
                break
            for sub, proofs in self._search(rule, pivot, all_pool, new_pool, attempts):
                if self._emit(rule, sub, proofs):
                    derived += 1
                if derived >= limit or attempts[0] > self.cfg["match_attempts"]:
                    break
        return derived

    def _search(self, rule, pivot, all_pool, new_pool, attempts):
        """Bounded, randomized backtracking over premise matches."""

        def go(i, sub, proofs):
            if attempts[0] > self.cfg["match_attempts"]:
                return
            if i == len(rule.premises):
                yield sub, list(proofs)
                return
            pattern = F.subst(rule.premises[i], sub)
            pool = new_pool if i == pivot else all_pool
            cands = list(self._candidates(pattern, pool))
            self.rng.shuffle(cands)
            for cand in cands:
                attempts[0] += 1
                if attempts[0] > self.cfg["match_attempts"]:
                    return
                s = M.match_formula(rule.premises[i], cand.formula, sub)
                if s is None:
                    continue
                proofs.append(cand.proof)
                yield from go(i + 1, s, proofs)
                proofs.pop()

        yield from go(0, {}, [])

    def _emit(self, rule, sub, premise_proofs):
        unbound = [v for v in rule.vars if v not in sub]
        if unbound:
            if len(unbound) > 2:
                return False
            choice = {v: F.Const(self._sample_const()) for v in unbound}
            sub = {**sub, **choice}
        args = [sub[v] for v in rule.vars]
        pf = P.Ax(rule.name, args)
        for pp in premise_proofs:
            pf = P.MP(pf, pp)
        concl = F.premises(F.instantiate(self.env[rule.name], args))[1] if rule.vars else (
            F.premises(self.env[rule.name])[1]
        )
        before = len(self.facts)
        self._integrate(concl, pf, f"forward:{rule.name}")
        return len(self.facts) > before

    def _sample_const(self):
        """Prefer parameters. A fact over parameters closes into a universally
        quantified theorem; a fact over Skolem witnesses closes into an
        existential one, which is nearly always the weaker and duller statement."""
        if self.rng.random() < self.cfg["param_bias"] or not self.consts:
            return self.rng.choice(self.params)
        return self.rng.choice(self.consts)

    def _fire_generative(self, rule):
        derived = 0
        for _ in range(self.cfg["generative_samples"]):
            if len(self.facts) >= self.cfg["max_facts"]:
                self.rejected["max-facts-generative"] += 1
                break
            args = [F.Const(self._sample_const()) for _ in rule.vars]
            pf = P.Ax(rule.name, args)
            concl = F.instantiate(self.env[rule.name], args) if rule.vars else self.env[rule.name]
            before = len(self.facts)
            self._integrate(concl, pf, f"generative:{rule.name}")
            derived += len(self.facts) > before
        return derived

    def saturate(self, rounds=None):
        """Bounded by rounds and, if configured, by wall clock.

        The round budget alone does not bound the work: promotion multiplies the
        rule count each generation and the per-rule derivation budget multiplies
        with it, so cost per round grows without the configuration changing. One
        ensemble member ran for over ten minutes on the same settings that took
        others fifteen seconds. A time budget makes members comparable and stops
        a single configuration from holding up a grid.
        """
        rounds = rounds or self.cfg["rounds"]
        budget = self.cfg.get("time_budget")
        self._deadline = (time.monotonic() + budget) if budget else None
        trace = []
        for r in range(rounds):
            if self._past_deadline():
                trace.append({"round": r, "stopped": "time-budget", "facts": len(self.facts)})
                break
            self._round = r
            new_facts, self.pending = self.pending, []
            produced = 0
            for rule in self.rules:
                if self._past_deadline():
                    break
                if rule.generative:
                    produced += self._fire_generative(rule)
                elif new_facts:
                    produced += self._fire(rule, new_facts)
            produced += self._run_case_splits()
            trace.append(
                {
                    "round": r,
                    "produced": produced,
                    "facts": len(self.facts),
                    "scopes": len(self.scopes),
                    "constants": len(self.consts),
                }
            )
            if not self.pending:
                break
        return trace

    # --- extraction -------------------------------------------------------

    def needed_scopes(self, pf):
        """Which scopes a term genuinely rests on.

        Naively a fact would have to close every scope open when it was derived,
        which after a few hundred generative steps means wrapping each theorem in
        dozens of irrelevant eliminations. Following the hypothesis names the
        term actually mentions — transitively, since one scope's source proof can
        live inside another — keeps the closed proofs proportionate.
        """
        scope_of = {s.hyp_name: i for i, s in enumerate(self.scopes)}
        const_of = {c: i for i, s in enumerate(self.scopes) for c in s.consts}
        needed, frontier = set(), [pf]
        while frontier:
            term = frontier.pop()
            names = free_hyps(term) | P.term_constants(term)
            for n in names:
                i = scope_of.get(n, const_of.get(n))
                if i is not None and i not in needed:
                    needed.add(i)
                    frontier.append(self.scopes[i].src_proof)
        return sorted(needed)

    def extract(self, fact):
        """Close a fact into a self-contained theorem. Returns (statement, proof)."""
        goal, pf = fact.formula, fact.proof

        for i in reversed(self.needed_scopes(pf)):
            scope = self.scopes[i]
            live = [c for c in scope.consts if c in F.constants(goal)]
            if live:
                taken = F.all_var_names(goal)
                names, i = [], 0
                while len(names) < len(live):
                    cand = f"e{i}"
                    i += 1
                    if cand not in taken:
                        names.append(cand)
                new_goal = F.Exists(
                    names, F.subst_consts(goal, {c: F.Var(n) for c, n in zip(live, names)})
                )
                pf = P.ExI(new_goal, [F.Const(c) for c in live], pf)
                goal = new_goal
            pf = P.ExE(scope.src_proof, scope.consts, scope.hyp_name, goal, pf)

        # A parameter the proof mentions but the statement does not would come
        # out as a vacuous binder, littering the corpus with `∀ v2 v3, P(v0,v1)`
        # shapes that clustering would then have to see through. Collapsing them
        # onto one surviving parameter is sound — they were universally
        # instantiable to begin with — and leaves at most one such binder.
        used = free_hyps(pf)
        pinned = set(F.constants(goal))
        for name, form in self.hyps:
            if name in used:
                pinned |= F.constants(form)
        loose = [p for p in self.params if p in P.term_constants(pf) and p not in pinned]
        if loose:
            target = next((p for p in self.params if p in pinned), loose[0])
            pf = P.subst_constants(pf, {p: F.Const(target) for p in loose if p != target})

        for name, form in reversed(self.hyps):
            if name in used:
                pf = P.Lam(name, form, pf)
                goal = F.Imp(form, goal)

        live = set(F.constants(goal)) | P.term_constants(pf)
        live_params = [p for p in self.params if p in live]
        if live_params:
            pf = P.Gen(live_params, pf)
            goal = P.infer(pf, self.env)
        return goal, pf


def free_hyps(pf):
    """Hypothesis names the term uses without binding them itself."""
    out = set()

    def go(p, bound):
        t = p["t"]
        if t == "hyp":
            if p["name"] not in bound:
                out.add(p["name"])
            return
        if t == "lam":
            go(p["body"], bound | {p["hyp"]})
            return
        if t == "exE":
            go(p["src"], bound)
            go(p["body"], bound | {p["hyp"]})
            return
        if t == "orE":
            go(p["src"], bound)
            go(p["body0"], bound | {p["hyp0"]})
            go(p["body1"], bound | {p["hyp1"]})
            return
        for c in P.children(p):
            go(c, bound)

    go(pf, frozenset())
    return out
