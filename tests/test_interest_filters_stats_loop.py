"""Filters, statistics and the growth loop of the interestingness audit
(Patel et al., arXiv:2609.28603). Synthetic fixtures only."""

from fractions import Fraction

import numpy as np
import pytest

from pipeline.interest import filters, loop, stats

from tests import test_interest_fixtures as fx


# --- filters --------------------------------------------------------------


def test_tokens_and_jaccard():
    a = "∀ (v0 : Obj), R0 v0 v0"
    assert filters.tokens(a) == ["∀", "(", "v0", ":", "Obj", ")", ",", "R0", "v0", "v0"]
    assert filters.jaccard(filters.unigrams(a), filters.unigrams(a)) == 1.0
    b = "∀ (v0 : Obj), R1 v0 v0"
    j = filters.jaccard(filters.unigrams(a), filters.unigrams(b))
    assert j == 7 / 9
    assert filters.max_similarity(a, []) == 0.0
    assert filters.max_similarity(a, [b, a]) == 1.0
    # bigrams see argument order, unigrams do not
    c = "R0 v1 v0"
    d = "R0 v0 v1"
    assert filters.jaccard(filters.unigrams(c), filters.unigrams(d)) == 1.0
    assert filters.jaccard(filters.bigrams(c), filters.bigrams(d)) < 1.0


def test_relevance_needs_a_shared_non_generic_identifier():
    T = fx.theory()
    r = fx.corpus()[0]
    assert filters.relevant(r["statement"], r["statement_ast"], [], {"R0", "Obj"}, T.sort)
    assert not filters.relevant(r["statement"], r["statement_ast"], ["∀ (v0 : Obj), v0 = v0"], {"Obj"}, T.sort)


def test_library_replicates_chainer_promotion():
    recs = fx.corpus()
    lib = filters.library(recs, ["a0", "a1"], promote_max=2)
    assert lib["t0_00000"] == ("a0", "a1")
    # generation 1 may cite the first two universal statements of generation 0
    assert lib["t1_00001"] == ("a0", "a1", "t0_00000", "t0_00001")
    for r in recs:
        assert set(r["proof_dependencies"]) <= set(lib[r["id"]])


# --- statistics -----------------------------------------------------------


def test_exact_ranks_handle_ties_and_huge_values():
    vals = [Fraction(10 ** 500, 3), Fraction(1, 2), Fraction(1, 2), Fraction(10 ** 500, 7)]
    assert list(stats.exact_ranks(vals)) == [4.0, 1.5, 1.5, 3.0]


def test_topk_ties_share_the_boundary():
    scores = [5, 4, 3, 3, 3, 1]
    w = stats.topk_weights(scores, 3)
    assert w.sum() == pytest.approx(3)
    assert list(w) == pytest.approx([1, 1, 1 / 3, 1 / 3, 1 / 3, 0])
    flags = [1, 0, 1, 0, 0, 0]
    assert abs(stats.topk_share(scores, flags, 3) - (1 + 1 / 3) / 3) < 1e-12


def test_bootstrap_is_seeded():
    g = np.random.default_rng(0)
    s = g.random(300)
    f = g.random(300) < 0.3
    a = stats.bootstrap_topk(s, f, 20, (1, 2, 3), b=200)
    b = stats.bootstrap_topk(s, f, 20, (1, 2, 3), b=200)
    assert a == b and a[0] <= a[1]


def test_wilson_and_spearman():
    p, lo, hi = stats.wilson(5, 10)
    assert p == 0.5 and 0.18 < lo < 0.24 and 0.76 < hi < 0.82
    assert stats.wilson(0, 0) == (None, None, None)
    x = np.arange(50)
    rho, lo, hi, n = stats.spearman_ci(x, x * 2, (0,), b=100)
    assert rho == pytest.approx(1.0) and n == 50


def test_youden():
    j, lo, hi = stats.bootstrap_youden([1, 1, 0, 0], [1, 1, 0, 0], (0,), b=100)
    assert j == 1.0


# --- the loop -------------------------------------------------------------


def _toy():
    def rec(rid, axd, prd):
        return {"id": rid, "axiom_dependencies": axd, "proof_dependencies": prd}

    return [
        rec("A", ["a0"], []),
        rec("B", ["a1"], []),
        rec("C", [], ["A"]),
        rec("D", [], ["A", "B"]),
        rec("E", ["a0"], ["C"]),
    ]


def test_loop_gates_on_premises():
    recs = _toy()
    score = {"A": 3, "B": 1, "C": 5, "D": 4, "E": 2}
    h = loop.run(recs, ["a0", "a1"], lambda r, P: score[r["id"]], trivial=set(), rounds=3, promote=1)
    assert [x["promoted"] for x in h] == [["A"], ["C"], ["E"]]
    assert [x["candidates"] for x in h] == [2, 2, 2]


def test_loop_trivial_and_retain_all():
    recs = _toy()
    h = loop.run(recs, ["a0", "a1"], None, trivial={"B"}, rounds=2)
    assert h[0]["promoted"] == ["A"]
    assert sorted(h[1]["promoted"]) == ["C"]


def test_loop_ties_do_not_follow_derivation_order():
    recs = [{"id": f"x{i}", "axiom_dependencies": ["a0"], "proof_dependencies": []} for i in range(40)]
    firsts = {tuple(loop.run(recs, ["a0"], lambda r, P: 0, set(), rounds=1, promote=5,
                             tie_seed=(s,))[0]["promoted"]) for s in range(5)}
    assert len(firsts) > 1


def test_random_promotion_is_reproducible():
    recs = _toy()
    a = loop.promoted_ids(loop.random_run(recs, ["a0", "a1"], set(), 3, rounds=3, promote=1))
    b = loop.promoted_ids(loop.random_run(recs, ["a0", "a1"], set(), 3, rounds=3, promote=1))
    assert a == b
