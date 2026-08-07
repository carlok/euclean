"""The proof calculus, and a checker for it.

Every derived statement carries a proof term built from these nodes. Two things
fall out of that choice, and they are the reason for it:

  * the proof DAG is exact and free — dependencies, size and depth are read off
    the term rather than recovered by parsing Lean's output;
  * emission to Lean is a pure function, so Lean's role reduces to refutation.
    If the kernel rejects a batch, the bug is here, and we fix it here.

`infer` is a local sanity check, not a substitute for Lean. It catches malformed
terms early and cheaply. Lean remains the source of truth.
"""

from . import formula as F

# --- constructors ---------------------------------------------------------


def Hyp(name):
    return {"t": "hyp", "name": name}


def Ax(name, args):
    return {"t": "ax", "name": name, "args": list(args)}


def MP(fn, arg):
    return {"t": "mp", "fn": fn, "arg": arg}


def Lam(hyp, prop, body):
    return {"t": "lam", "hyp": hyp, "prop": prop, "body": body}


def AndI(lhs, rhs):
    return {"t": "andI", "lhs": lhs, "rhs": rhs}


def AndL(p):
    return {"t": "andL", "p": p}


def AndR(p):
    return {"t": "andR", "p": p}


def OrL(p, other):
    return {"t": "orL", "p": p, "other": other}


def OrR(p, other):
    return {"t": "orR", "p": p, "other": other}


def OrE(src, hyp0, body0, hyp1, body1, goal):
    """Case analysis. `src : A ∨ B`, and both branches must reach the same goal.

    Without this the calculus can build disjunctions and never use one, which is
    not a cosmetic gap: any concept that is definitionally a disjunction is then
    unreachable no matter how much is generated.
    """
    return {
        "t": "orE",
        "src": src,
        "hyp0": hyp0,
        "body0": body0,
        "hyp1": hyp1,
        "body1": body1,
        "goal": goal,
    }


def ExI(goal, witnesses, body):
    return {"t": "exI", "goal": goal, "witnesses": list(witnesses), "body": body}


def ExE(src, consts, hyp, goal, body):
    return {"t": "exE", "src": src, "consts": list(consts), "hyp": hyp, "goal": goal, "body": body}


def Gen(consts, body):
    """Generalize local constants into a leading ∀ block."""
    return {"t": "gen", "consts": list(consts), "body": body}


def EqRefl(term):
    return {"t": "eqRefl", "term": term}


def EqSymm(p):
    return {"t": "eqSymm", "p": p}


def EqSubst(eq, motive_var, motive_body, p):
    return {"t": "eqSubst", "eq": eq, "mvar": motive_var, "mbody": motive_body, "p": p}


def Absurd(p, np, goal):
    return {"t": "absurd", "p": p, "np": np, "goal": goal}


# --- checking -------------------------------------------------------------


class ProofError(Exception):
    pass


def infer(pf, env, hyps=None):
    """Return the formula this proof term establishes, or raise ProofError.

    env  : name -> statement, for axioms and already-proved lemmas
    hyps : name -> formula, the local hypothesis context
    """
    hyps = hyps or {}
    t = pf["t"]

    if t == "hyp":
        if pf["name"] not in hyps:
            raise ProofError(f"unbound hypothesis {pf['name']!r}")
        return hyps[pf["name"]]

    if t == "ax":
        if pf["name"] not in env:
            raise ProofError(f"unknown reference {pf['name']!r}")
        stmt = env[pf["name"]]
        if not pf["args"]:
            return stmt
        if stmt["kind"] != "forall":
            raise ProofError(f"{pf['name']!r} takes no arguments")
        return F.instantiate(stmt, pf["args"])

    if t == "mp":
        fn = infer(pf["fn"], env, hyps)
        arg = infer(pf["arg"], env, hyps)
        if fn["kind"] != "imp":
            raise ProofError(f"modus ponens on a non-implication ({fn['kind']})")
        if not F.same(fn["lhs"], arg):
            raise ProofError("modus ponens: argument does not match the premise")
        return fn["rhs"]

    if t == "lam":
        inner = dict(hyps)
        inner[pf["hyp"]] = pf["prop"]
        return F.Imp(pf["prop"], infer(pf["body"], env, inner))

    if t == "andI":
        return F.And(infer(pf["lhs"], env, hyps), infer(pf["rhs"], env, hyps))

    if t in ("andL", "andR"):
        g = infer(pf["p"], env, hyps)
        if g["kind"] != "and":
            raise ProofError(f"conjunction elimination on a {g['kind']}")
        return g["lhs"] if t == "andL" else g["rhs"]

    if t == "orL":
        return F.Or(infer(pf["p"], env, hyps), pf["other"])
    if t == "orR":
        return F.Or(pf["other"], infer(pf["p"], env, hyps))

    if t == "orE":
        src = infer(pf["src"], env, hyps)
        if src["kind"] != "or":
            raise ProofError(f"case analysis on a {src['kind']}")
        for side, hyp_field, body_field in (("lhs", "hyp0", "body0"), ("rhs", "hyp1", "body1")):
            inner = dict(hyps)
            inner[pf[hyp_field]] = src[side]
            got = infer(pf[body_field], env, inner)
            if not F.same(got, pf["goal"]):
                raise ProofError(f"case analysis: {body_field} does not prove the stated goal")
        return pf["goal"]

    if t == "exI":
        goal = pf["goal"]
        if goal["kind"] != "exists":
            raise ProofError("existential introduction against a non-∃ goal")
        want = F.instantiate({**goal, "kind": "forall"}, pf["witnesses"])
        got = infer(pf["body"], env, hyps)
        if not F.same(want, got):
            raise ProofError("existential introduction: witness body mismatch")
        return goal

    if t == "exE":
        src = infer(pf["src"], env, hyps)
        if src["kind"] != "exists":
            raise ProofError(f"existential elimination on a {src['kind']}")
        opened = F.open_exists(src, pf["consts"])
        inner = dict(hyps)
        inner[pf["hyp"]] = opened
        got = infer(pf["body"], env, inner)
        if not F.same(got, pf["goal"]):
            raise ProofError("existential elimination: body does not prove the stated goal")
        escaped = F.constants(pf["goal"]) & set(pf["consts"])
        if escaped:
            raise ProofError(f"opened constants escape their scope: {sorted(escaped)}")
        return pf["goal"]

    if t == "gen":
        body = infer(pf["body"], env, hyps)
        for name, h in hyps.items():
            leaked = F.constants(h) & set(pf["consts"])
            if leaked:
                raise ProofError(
                    f"cannot generalize {sorted(leaked)}: still assumed in hypothesis {name!r}"
                )
        taken = F.all_var_names(body)
        names, i = [], 0
        while len(names) < len(pf["consts"]):
            cand = f"v{i}"
            i += 1
            if cand not in taken:
                names.append(cand)
        return F.Forall(names, F.subst_consts(body, dict(zip(pf["consts"], map(F.Var, names)))))

    if t == "eqRefl":
        return F.Eq(pf["term"], pf["term"])

    if t == "eqSymm":
        g = infer(pf["p"], env, hyps)
        if g["kind"] != "eq":
            raise ProofError("symmetry applied to a non-equation")
        return F.Eq(g["rhs"], g["lhs"])

    if t == "eqSubst":
        eq = infer(pf["eq"], env, hyps)
        if eq["kind"] != "eq":
            raise ProofError("rewriting along a non-equation")
        want = F.subst(pf["mbody"], {pf["mvar"]: eq["lhs"]})
        got = infer(pf["p"], env, hyps)
        if not F.same(want, got):
            raise ProofError("rewriting: motive does not match the rewritten proof")
        return F.subst(pf["mbody"], {pf["mvar"]: eq["rhs"]})

    if t == "absurd":
        g = infer(pf["p"], env, hyps)
        ng = infer(pf["np"], env, hyps)
        if ng["kind"] != "not" or not F.same(ng["arg"], g):
            raise ProofError("absurdity: the two proofs are not contradictory")
        return pf["goal"]

    raise ProofError(f"unknown proof node {t!r}")


# --- structure ------------------------------------------------------------

_SUBPROOFS = {
    "hyp": (),
    "ax": (),
    "mp": ("fn", "arg"),
    "lam": ("body",),
    "andI": ("lhs", "rhs"),
    "andL": ("p",),
    "andR": ("p",),
    "orL": ("p",),
    "orR": ("p",),
    "orE": ("src", "body0", "body1"),
    "exI": ("body",),
    "exE": ("src", "body"),
    "gen": ("body",),
    "eqRefl": (),
    "eqSymm": ("p",),
    "eqSubst": ("eq", "p"),
    "absurd": ("p", "np"),
}


def children(pf):
    return [pf[f] for f in _SUBPROOFS[pf["t"]]]


def size(pf):
    return 1 + sum(size(c) for c in children(pf))


def depth(pf):
    kids = children(pf)
    return 1 + (max(depth(c) for c in kids) if kids else 0)


def references(pf):
    """Every axiom or lemma name the term appeals to, with multiplicity."""
    counts = {}

    def go(p):
        if p["t"] == "ax":
            counts[p["name"]] = counts.get(p["name"], 0) + 1
        for c in children(p):
            go(c)

    go(pf)
    return counts


def node_counts(pf):
    counts = {}

    def go(p):
        counts[p["t"]] = counts.get(p["t"], 0) + 1
        for c in children(p):
            go(c)

    go(pf)
    return counts


def term_constants(pf):
    """Constants occurring free anywhere in a proof term.

    A term routinely mentions constants its conclusion does not — an axiom
    instantiated at four points can conclude something about two of them. Those
    occurrences still have to be bound when the theorem is closed, so they have
    to be visible here.
    """
    out = set()

    def go(p, bound):
        t = p["t"]
        if t == "ax":
            for a in p["args"]:
                if a["kind"] == "const" and a["name"] not in bound:
                    out.add(a["name"])
        elif t == "lam":
            out.update(F.constants(p["prop"]) - bound)
        elif t == "exI":
            out.update(F.constants(p["goal"]) - bound)
            for w in p["witnesses"]:
                if w["kind"] == "const" and w["name"] not in bound:
                    out.add(w["name"])
        elif t == "exE":
            out.update(F.constants(p["goal"]) - bound)
            go(p["src"], bound)
            go(p["body"], bound | set(p["consts"]))
            return
        elif t == "gen":
            go(p["body"], bound | set(p["consts"]))
            return
        elif t == "eqRefl":
            if p["term"]["kind"] == "const" and p["term"]["name"] not in bound:
                out.add(p["term"]["name"])
        elif t == "eqSubst":
            out.update(F.constants(p["mbody"]) - bound)
        elif t in ("absurd", "orE"):
            out.update(F.constants(p["goal"]) - bound)
        elif t in ("orL", "orR"):
            out.update(F.constants(p["other"]) - bound)
        for c in children(p):
            go(c, bound)

    go(pf, frozenset())
    return out


def subst_constants(pf, mapping):
    """Rename free constants throughout a proof term, formulas included."""
    if not mapping:
        return pf

    def sf(f):
        return F.subst_consts(f, mapping)

    def st(term):
        if term["kind"] == "const" and term["name"] in mapping:
            return dict(mapping[term["name"]])
        return dict(term)

    def go(p):
        t = p["t"]
        out = dict(p)
        if t == "ax":
            out["args"] = [st(a) for a in p["args"]]
        elif t == "lam":
            out["prop"] = sf(p["prop"])
        elif t == "exI":
            out["goal"] = sf(p["goal"])
            out["witnesses"] = [st(w) for w in p["witnesses"]]
        elif t == "exE":
            out["goal"] = sf(p["goal"])
        elif t == "eqRefl":
            out["term"] = st(p["term"])
        elif t == "eqSubst":
            out["mbody"] = sf(p["mbody"])
        elif t in ("absurd", "orE"):
            out["goal"] = sf(p["goal"])
        elif t in ("orL", "orR"):
            out["other"] = sf(p["other"])
        for field in _SUBPROOFS[t]:
            out[field] = go(p[field])
        return out

    return go(pf)


def branching(pf):
    """Out-degree profile of the proof DAG, as a sorted list of (degree, count)."""
    counts = {}

    def go(p):
        d = len(children(p))
        counts[d] = counts.get(d, 0) + 1
        for c in children(p):
            go(c)

    go(pf)
    return sorted(counts.items())
