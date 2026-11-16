"""The growth loop of Patel et al., Sec. 3.4 and App. D, with the corpus as conjecturer.

There, each round a conjecturer proposes candidates from the premises P_{n-1},
the verified ones are ranked, and the top ten are promoted into P_n. Here no
model proposes anything: the candidates of round n are the corpus statements
not yet promoted whose direct premises (every axiom and lemma their stored
proof cites) all lie in P_{n-1}. P_0 is the axioms.

Every candidate therefore cites only premises in P_{n-1}, so V(T|P_{n-1}) is
the length of its own proof, and L(T|P_{n-1}) = S(T) whenever P_{n-1} already
mentions every relation T does; `description_length` computes it either way.

Promotion rules, as in the paper's ablation (Sec. 3.4, App. D.1), plus the one
this audit adds:

    interestingness   top 10 by I(T|P_{n-1})
    proof_size        top 10 by V(T|P_{n-1})
    importance        top 10 by euclean's structural importance
    random            10 uniformly at random, repeated under many seeds
    retain_all        every candidate

Ties at the cut are broken by a seeded shuffle, never by derivation order.
"""

import numpy as np

from . import metric
from .stats import rng

ROUNDS = 6
PROMOTE = 10
RANDOM_REPEATS = 1000


def direct_premises(record):
    return set(record["axiom_dependencies"]) | set(record["proof_dependencies"])


def run(records, axiom_names, score_fn, trivial, rounds=ROUNDS, promote=PROMOTE,
        tie_seed=(0,), restatement_filter=None):
    """One trajectory.

    score_fn(record, premises) -> a sortable score (higher promotes first), or
    None for retain-all. `trivial` is the set of ids the triviality filter
    removes. `restatement_filter(record, premises) -> bool` optionally removes
    more. Returns the list of rounds, each the ids promoted in it.
    """
    P = set(axiom_names)
    promoted = set()
    by_id = {r["id"]: r for r in records}
    deps = {r["id"]: direct_premises(r) for r in records}
    g = rng(*tie_seed)
    history = []
    for n in range(1, rounds + 1):
        cands = [
            rid for rid in by_id
            if rid not in promoted and rid not in trivial and deps[rid] <= P
        ]
        if restatement_filter is not None:
            cands = [c for c in cands if not restatement_filter(by_id[c], P)]
        if score_fn is None:
            chosen = list(cands)
        else:
            shuffled = [cands[i] for i in g.permutation(len(cands))]
            scored = [(score_fn(by_id[c], P), c) for c in shuffled]
            # stable sort on the score alone keeps the shuffle as the tie-break
            scored.sort(key=lambda sc: sc[0], reverse=True)
            chosen = [c for _, c in scored[:promote]]
        history.append({"round": n, "candidates": len(cands), "promoted": chosen})
        promoted.update(chosen)
        P.update(chosen)
    return history


def random_run(records, axiom_names, trivial, seed, rounds=ROUNDS, promote=PROMOTE):
    """Promote uniformly at random: a score drawn fresh for every candidate."""
    g = rng(1, seed)
    return run(records, axiom_names, lambda r, P: g.random(), trivial, rounds, promote,
               tie_seed=(2, seed))


def promoted_ids(history):
    return [rid for h in history for rid in h["promoted"]]


def share(ids, flag):
    ids = list(ids)
    return sum(1 for i in ids if flag[i]) / len(ids) if ids else None


def interestingness_score(v_local, measure_name, decls, sort, statements_by_id):
    """I(T|P) for a candidate whose premises all lie in P."""
    measure = metric.MEASURES[measure_name]
    vocab_cache = {}

    def voc_of(name):
        if name not in vocab_cache:
            vocab_cache[name] = metric.vocabulary(statements_by_id[name], sort)
        return vocab_cache[name]

    def score(record, P):
        voc_p = set()
        for name in P:
            voc_p |= voc_of(name)
        length = metric.description_length(
            record["statement"], metric.vocabulary(record["statement_ast"], sort), voc_p, decls, measure
        )
        return metric.interestingness(v_local[record["id"]], length)

    return score


def summarise_random(records, axiom_names, trivial, flag, repeats=RANDOM_REPEATS):
    shares = []
    for s in range(repeats):
        h = random_run(records, axiom_names, trivial, s)
        shares.append(share(promoted_ids(h), flag))
    arr = np.asarray([x for x in shares if x is not None], dtype=float)
    return {
        "repeats": repeats,
        "mean": float(arr.mean()),
        "p2.5": float(np.percentile(arr, 2.5)),
        "p97.5": float(np.percentile(arr, 97.5)),
        "shares": [round(float(x), 6) for x in arr],
    }
