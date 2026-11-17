"""The paper's growth loop (Sec. 3.4, App. D), with a fixed candidate pool.

Start from P_0 = the axioms. In round n the candidates are the theorems not yet
promoted whose direct premises all lie in P_{n-1}; the top `promote` by a score
join P_n. In the paper a language model proposes candidates; here the pool is
the library itself, which isolates the promotion rule, the only place the
paper's score enters the loop.

Promotion rules from the paper's ablation (App. D.1) are provided:
`interestingness`, `proof_size`, `random`, `retain_all`. Any other rule is a
function `score(decl, P) -> sortable`.

Ties at the cut are broken by a seeded shuffle, never by listing order.
"""

import random
from fractions import Fraction

from . import metric

ROUNDS = 6
PROMOTE = 10


def run(lib, score, rounds=ROUNDS, promote=PROMOTE, exclude=(), seed=0):
    """One trajectory: a list of rounds, each {round, candidates, promoted}.

    `score(decl, P)` returns a sortable value (higher first), or pass
    `score=None` to promote every candidate. `exclude` removes ids up front,
    e.g. what a triviality filter rejected.
    """
    rnd = random.Random(seed)
    P = set(lib.axioms())
    exclude = set(exclude)
    promoted, history = set(), []
    pool = [d for d in lib.theorems() if d["name"] not in exclude]
    for n in range(1, rounds + 1):
        cands = [d for d in pool if d["name"] not in promoted and set(d.get("premises", {})) <= P]
        if score is None:
            chosen = [d["name"] for d in cands]
        else:
            rnd.shuffle(cands)
            ranked = sorted(cands, key=lambda d: score(d, P), reverse=True)
            chosen = [d["name"] for d in ranked[:promote]]
        history.append({"round": n, "candidates": len(cands), "promoted": chosen})
        promoted.update(chosen)
        P.update(chosen)
    return history


def interestingness_rule(lib, cost="loc", size=metric.s_raw):
    """I(T|P_{n-1}). Every candidate's premises lie in P, so V is its own step."""
    def score(d, P):
        return metric.interestingness(d["cost"][cost], metric.description_length(lib, d, P, size))
    return score


def proof_size_rule(cost="loc"):
    return lambda d, P: d["cost"][cost]


def random_rule(seed):
    rnd = random.Random(f"random-rule-{seed}")
    return lambda d, P: rnd.random()


def promoted(history):
    return [x for h in history for x in h["promoted"]]


def share(names, flag):
    names = list(names)
    return Fraction(sum(1 for x in names if flag.get(x)), len(names)) if names else None
