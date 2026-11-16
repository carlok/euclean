"""Statement length, description length, proof difficulty and interestingness.

The metric is Patel et al.'s (arXiv:2609.28603); equation numbers are theirs:

    L(T|P) = S(T) + sum over d in C(T) \\ C(P) of S(d)     (Eq. 5)
    I(T|P) = 100 * V(T|P) / L(T|P)                        (Eq. 6)
    U0(T)  = |D(T)| * V(T|empty)                          (Eq. 7)
    R(T,P) = 0.25 + log(1 + I(T|P) / 100)                 (Eq. 8)

`S` counts characters of a statement. `C(X)` is the set of definitions needed to
state `X`; here that is the sort and the relations a statement mentions, since
the corpora audited carry no invented definitions. `V` is proof difficulty, and
euclean can compute it exactly because its proof terms are built in Python and
only checked by Lean.

Three measures of a single proof step (the proof of T citing its direct
premises as given):

    term   `proof.size` of the proof term, every cited axiom or lemma one leaf
    lines  lines of the emitted Lean proof under one fixed layout (`proof_lines`)
    tac    one line if a fixed tactic ladder closes the statement, else `lines`
           (the ladder runs in Lean; see `tactics`)

and two ways of conditioning on a premise set P, both "premise expansion" in
the paper's sense (Sec. 2.1, App. B.1.1), which replaces a cited lemma by its
own premises and adds its proof's length:

    dag    the paper's set semantics: P <- (P \\ {L}) | P(L). Each lemma in the
           closure is paid for once, however often it is cited.
    tree   the proof tree fully unrolled: a lemma cited k times is paid for k
           times. Exact integers; it grows exponentially with depth, so it is
           only ever compared by rank and reported as a logarithm.

Axioms are never expanded: they have no proof, and V(T|empty) means "from the
axioms".
"""

import math
import re
import sys
from fractions import Fraction

from ..kernel import emit, formula as F, proof as P

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_']*")

# The layout every proof is measured under. Fixed before any score was computed.
WIDTH = 100
INDENT = 2

sys.setrecursionlimit(max(sys.getrecursionlimit(), 100000))


# --- statement length -----------------------------------------------------


def s_raw(text):
    """Characters of the statement as emitted, which is what Lean checked."""
    return len(text)


def s_canon(text):
    """Characters with every identifier replaced by one fixed-width symbol.

    Anonymized names (`R0`, `v3`) are shorter than real ones, which inflates any
    ratio over characters. Collapsing every identifier to one symbol removes the
    name lengths and keeps the structure.
    """
    return len(IDENT.sub("#", text))


MEASURES = {"raw": s_raw, "canon": s_canon}


def declarations(theory):
    """name -> the statement of each primitive, as the Lean base module states it."""
    out = {theory.sort: "Type"}
    for rel, n in theory.relations.items():
        out[rel] = " → ".join([theory.sort] * n + ["Prop"])
    return out


def vocabulary(stmt, sort):
    """C(X): the definitions needed to state X, recursively.

    A relation's declaration mentions the sort, and the sort's mentions nothing,
    so the recursion closes after one step.
    """
    return {sort} | {r for r in F.relations(stmt) if r != "="}


def premise_vocabulary(stmts, sort):
    out = set()
    for s in stmts:
        out |= vocabulary(s, sort)
    return out


def description_length(text, voc_t, voc_p, decls, measure=s_raw):
    """Eq. 5. `voc_p` is C(P); pass an empty set for P = empty."""
    return measure(text) + sum(measure(decls[d]) for d in sorted(voc_t - voc_p))


# --- one proof step -------------------------------------------------------


def _flat_len(pf, memo):
    """len(emit.proof(pf)), computed without building the string.

    Mirrors `kernel/emit.py` node for node. A test checks the two agree on every
    node kind, and `proof_lines` checks the root of every term it measures.
    """
    k = id(pf)
    hit = memo.get(k)
    if hit is not None:
        return hit

    def L(c):
        return _flat_len(c, memo)

    t = pf["t"]
    if t == "hyp":
        n = len(pf["name"])
    elif t == "ax":
        args = pf["args"]
        n = len(pf["name"]) if not args else (
            len(pf["name"]) + sum(len(emit.term(a)) for a in args) + len(args) + 2
        )
    elif t == "mp":
        n = L(pf["fn"]) + L(pf["arg"]) + 3
    elif t == "lam":
        n = len(f"(fun ({pf['hyp']} : {emit.formula(pf['prop'], top=True)}) => ") + L(pf["body"]) + 1
    elif t == "andI":
        n = len("(And.intro ") + L(pf["lhs"]) + 1 + L(pf["rhs"]) + 1
    elif t == "andL":
        n = len("(And.left ") + L(pf["p"]) + 1
    elif t == "andR":
        n = len("(And.right ") + L(pf["p"]) + 1
    elif t == "orL":
        n = len("(Or.inl ") + L(pf["p"]) + 1
    elif t == "orR":
        n = len("(Or.inr ") + L(pf["p"]) + 1
    elif t == "orE":
        n = (
            len("(Or.elim ") + L(pf["src"]) + len(f" (fun {pf['hyp0']} => ") + L(pf["body0"])
            + len(f") (fun {pf['hyp1']} => ") + L(pf["body1"]) + len("))")
        )
    elif t == "exI":
        ws = pf["witnesses"]
        n = 2 + sum(len(emit.term(w)) for w in ws) + L(pf["body"]) + 2 * len(ws)
    elif t == "exE":
        consts, h = pf["consts"], pf["hyp"]
        m = len(consts)
        binders = [f"{h}_{i}" for i in range(m - 1)] + [h]
        total = L(pf["body"])
        for i in range(m - 1, -1, -1):
            src = L(pf["src"]) if i == 0 else len(f"{h}_{i - 1}")
            total = (
                len("(Exists.elim ") + src + len(f" (fun {consts[i]} {binders[i]} => ")
                + total + len("))")
            )
        n = total
    elif t == "gen":
        binds = " ".join(f"({c} : {emit.SORT})" for c in pf["consts"])
        n = len(f"(fun {binds} => ") + L(pf["body"]) + 1
    elif t == "eqRefl":
        n = 3
    elif t == "eqSymm":
        n = len("(Eq.symm ") + L(pf["p"]) + 1
    elif t == "eqSubst":
        motive = f"(fun ({pf['mvar']} : {emit.SORT}) => {emit.formula(pf['mbody'], top=True)})"
        n = len(f"(Eq.subst (motive := {motive}) ") + L(pf["eq"]) + 1 + L(pf["p"]) + 1
    elif t == "absurd":
        n = len("(absurd ") + L(pf["p"]) + 1 + L(pf["np"]) + 1
    else:
        raise ValueError(f"unknown proof node {t!r}")
    memo[k] = n
    return n


def _layout_children(pf):
    """What goes on the lines below a node that does not fit on one.

    An application spine `(((f a) b) c)` is laid out as a head with its
    arguments beneath it, the way a person would write it; every other node puts
    its sub-proofs beneath it.
    """
    if pf["t"] == "mp":
        args, spine = [], pf
        while spine["t"] == "mp":
            args.append(spine["arg"])
            spine = spine["fn"]
        args.reverse()
        return args if spine["t"] in ("ax", "hyp") else [spine] + args
    return P.children(pf)


def proof_lines(pf, width=WIDTH, indent=INDENT, check=True):
    """Lines of the emitted proof under one fixed layout.

    A node that fits in the remaining width stays on one line; otherwise its
    head takes a line and its children are laid out beneath it, one indent
    deeper. The proof body starts one indent in, as `emit.theorem` writes it.
    No line is blank, so this is also the non-blank physical line count the
    paper measures (App. B.1.1).
    """
    memo = {}
    if check:
        got, want = _flat_len(pf, memo), len(emit.proof(pf))
        if got != want:
            raise AssertionError(f"flat size {got} disagrees with the emitter's {want}")

    def go(node, col):
        if _flat_len(node, memo) <= width - col:
            return 1
        return 1 + sum(go(c, col + indent) for c in _layout_children(node))

    return go(pf, indent)


def term_size(pf):
    return P.size(pf)


# --- premise expansion ----------------------------------------------------


def lemma_references(records):
    """id -> {cited corpus lemma: multiplicity in the proof term}."""
    ids = {r["id"] for r in records}
    return {
        r["id"]: {n: m for n, m in P.references(r["proof_ast"]).items() if n in ids}
        for r in records
    }


def expand_dag(order, refs, local, given=frozenset()):
    """V(T|P) under the paper's set semantics, for every id in `order`.

    `given` is P restricted to corpus lemmas: such a lemma costs nothing and is
    not expanded. Axioms are never in `refs`, so they are always free.
    `order` must list every lemma after the lemmas it cites.
    """
    closure = {}
    out = {}
    for t in order:
        anc = set()
        for lem in refs[t]:
            if lem in given:
                continue
            anc.add(lem)
            anc |= closure[lem]
        closure[t] = frozenset(anc)
        out[t] = local[t] + sum(local[x] for x in anc)
    return out


def expand_tree(order, refs, local, given=frozenset()):
    """V(T|P) with the proof tree fully unrolled: exact, and possibly enormous."""
    out = {}
    for t in order:
        total = local[t]
        for lem, mult in refs[t].items():
            if lem in given:
                continue
            total += mult * out[lem]
        out[t] = total
    return out


EXPANSIONS = {"dag": expand_dag, "tree": expand_tree}


# --- the scores -----------------------------------------------------------


def interestingness(v, length):
    """Eq. 6, exactly. V can be far too large for a float."""
    return Fraction(100 * v, length)


def utility(direct_users, v_empty):
    """Eq. 7."""
    return direct_users * v_empty


def reward(v, length):
    """Eq. 8 for a valid, relevant, nontrivial statement: 0.25 + ln(1 + V/L).

    The paper does not state the base; natural log is assumed and recorded in
    the pre-registration. Computed from integer logs so huge V stays exact
    enough.
    """
    return 0.25 + math.log(length + v) - math.log(length)


def log10_int(n):
    return math.log10(n) if n > 0 else float("-inf")


def log10_fraction(x):
    return log10_int(x.numerator) - log10_int(x.denominator)


# Eq. 8's penalties (Sec. 3.3, App. C.1.2), for the reward column only.
PENALTY_PARSE = -0.5
PENALTY_IRRELEVANT = -0.25
REWARD_TRIVIAL = 0.0
