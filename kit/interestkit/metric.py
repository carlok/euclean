"""Patel et al.'s quantities, as the paper states them (arXiv:2609.28603).

    L(T|P) = S(T) + sum over d in C(T) \\ C(P) of S(d)        Eq. 5
    I(T|P) = 100 * V(T|P) / L(T|P)                           Eq. 6
    I0(T)  = I(T | empty)
    U0(T)  = |D(T)| * V(T | empty)                           Eq. 7
    R(T,P) = 0.25 + ln(1 + I(T|P) / 100)                     Eq. 8

V(T|P) is the cost of proving T when P is given. The paper obtains it by
"premise expansion" (Sec. 2.1, App. B.1.1): a cited lemma not in P is replaced
by its own premises, and its proof cost is added. That leaves one choice the
paper does not spell out, offered here as `mode`:

    "dag"   set semantics, P <- (P \\ {L}) | P(L): each lemma in the closure is
            paid for once. This is the reading of the paper's update rule.
    "tree"  the proof tree unrolled: a lemma cited k times is paid for k times.
            Exact integers; grows exponentially with depth.

Statement size S is pluggable: characters as written (`s_raw`, the paper's), or
with every identifier collapsed to one symbol (`s_canon`), which removes the
advantage short or anonymized names give.
"""

import math
import re
from fractions import Fraction

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_']*")


def s_raw(text):
    return len(text)


def s_canon(text):
    return len(IDENT.sub("#", text))


SIZES = {"raw": s_raw, "canon": s_canon}


def description_length(lib, decl, given=(), size=s_raw):
    """Eq. 5. `given` is the premise set P, as declaration names."""
    voc_p = set()
    for p in given:
        voc_p |= lib.vocabulary_of(p)
    voc_t = lib.vocabulary_of(decl)
    d = lib.by_name[decl] if isinstance(decl, str) else decl
    return size(d["statement"]) + sum(size(lib.definitions[u]["statement"]) for u in sorted(voc_t - voc_p))


def proof_cost(lib, cost="loc", mode="dag", given=()):
    """V(T|P) for every theorem. Axioms are free and never expanded.

    Returns name -> int. `given` lemmas cost nothing and are not expanded.
    """
    given = set(given)
    local = {d["name"]: (0 if d.get("axiom") else d["cost"][cost]) for d in lib.decls}
    axioms = {d["name"] for d in lib.decls if d.get("axiom")}
    out = {}
    if mode == "dag":
        closure = {}
        for d in lib.decls:
            n = d["name"]
            anc = set()
            for p in d.get("premises", {}):
                if p in given or p in axioms:
                    continue
                anc.add(p)
                anc |= closure[p]
            closure[n] = anc
            out[n] = local[n] + sum(local[x] for x in anc)
    elif mode == "tree":
        for d in lib.decls:
            n = d["name"]
            total = local[n]
            for p, mult in d.get("premises", {}).items():
                if p in given or p in axioms:
                    continue
                total += mult * out[p]
            out[n] = total
    else:
        raise ValueError(f"unknown mode {mode!r}")
    return out


def interestingness(v, length):
    """Eq. 6, exactly. V can be too large for a float."""
    return Fraction(100 * v, length)


def log10(x):
    """log10 of a positive Fraction or int, without overflowing a float."""
    if isinstance(x, Fraction):
        return log10(x.numerator) - log10(x.denominator) if x > 0 else float("-inf")
    if x <= 0:
        return float("-inf")
    digits = len(str(x))
    if digits < 300:
        return math.log10(x)
    return math.log10(int(str(x)[:17])) + digits - 17


def i0(lib, cost="loc", mode="dag", size=s_raw):
    """I0(T) = I(T | empty) for every theorem, as exact Fractions."""
    v = proof_cost(lib, cost, mode)
    return {d["name"]: interestingness(v[d["name"]], description_length(lib, d, (), size))
            for d in lib.theorems()}


def u0(lib, cost="loc", mode="dag"):
    """Eq. 7 for every theorem."""
    v = proof_cost(lib, cost, mode)
    users = lib.direct_users()
    return {d["name"]: users[d["name"]] * v[d["name"]] for d in lib.theorems()}


def reward(i_value=None, *, parse_failure=False, invalid=False, irrelevant=False, trivial=False):
    """Eq. 8 with the paper's penalties (Sec. 3.3, App. C.1.2).

    -0.5 parse failure; -0.25 invalid in Lean or unrelated to the premises;
    0 if simple automation closes it; otherwise 0.25 + ln(1 + I/100). The
    paper does not state the log's base; natural log is assumed.
    """
    if parse_failure:
        return -0.5
    if invalid or irrelevant:
        return -0.25
    if trivial:
        return 0.0
    # 1 + I/100 = (L + V) / L, kept exact: V can exceed any float
    return 0.25 + log10(1 + Fraction(i_value) / 100) * math.log(10)
