"""Patel et al.'s metric (arXiv:2609.28603) as mapped onto euclean: unit tests.

Synthetic fixtures only; no real corpus is scored here.
"""

import math
from fractions import Fraction

from pipeline.interest import metric
from pipeline.kernel import emit, formula as F, proof as P

from tests import test_interest_fixtures as fx


def test_statement_lengths():
    text = "∀ (v0 : Obj) (v12 : Obj), R0 v0 v12 → R0 v12 v0"
    assert metric.s_raw(text) == len(text)
    # every identifier becomes one symbol
    assert metric.s_canon(text) == len("∀ (# : #) (# : #), # # # → # # #")


def test_description_length_eq5():
    T = fx.theory()
    decls = metric.declarations(T)
    assert decls == {"Obj": "Type", "R0": "Obj → Obj → Prop"}
    stmt = T.env["a1"]
    text = emit.formula(stmt, top=True)
    voc = metric.vocabulary(stmt, T.sort)
    assert voc == {"Obj", "R0"}
    # P = empty: the statement pays for its whole vocabulary
    assert metric.description_length(text, voc, set(), decls) == len(text) + 4 + len("Obj → Obj → Prop")
    # premises that already state R0 make it free
    assert metric.description_length(text, voc, {"Obj", "R0"}, decls) == len(text)


def _every_node_kind():
    """A closed-enough proof term touching every node kind the emitter knows."""
    a, b = F.Const("p0"), F.Const("p1")
    atom = F.Atom("R0", [a, b])
    terms = [
        P.Hyp("h0"),
        P.Ax("a1", []),
        P.Ax("a1", [a, b]),
        P.MP(P.Ax("a1", [a, b]), P.Hyp("h0")),
        P.Lam("h0", atom, P.Hyp("h0")),
        P.AndI(P.Hyp("h0"), P.Hyp("h1")),
        P.AndL(P.Hyp("h0")),
        P.AndR(P.Hyp("h0")),
        P.OrL(P.Hyp("h0"), atom),
        P.OrR(P.Hyp("h0"), atom),
        P.OrE(P.Hyp("h2"), "h3", P.Hyp("h3"), "h4", P.Hyp("h4"), atom),
        P.ExI(F.Exists(["v9"], atom), [a], P.Hyp("h0")),
        P.ExE(P.Hyp("h5"), ["s0"], "e0", atom, P.Hyp("e0")),
        P.ExE(P.Hyp("h5"), ["s0", "s1", "s2"], "e0", atom, P.Hyp("e0")),
        P.Gen(["p0", "p1"], P.Hyp("h0")),
        P.EqRefl(a),
        P.EqSymm(P.Hyp("h0")),
        P.EqSubst(P.Hyp("h0"), "v0", F.Atom("R0", [F.Var("v0"), b]), P.Hyp("h1")),
        P.Absurd(P.Hyp("h0"), P.Hyp("h1"), atom),
    ]
    nested = terms[0]
    for t in terms[1:]:
        nested = P.AndI(nested, t)
    return terms + [nested]


def test_flat_length_mirrors_the_emitter():
    for t in _every_node_kind():
        assert metric._flat_len(t, {}) == len(emit.proof(t)), t["t"]


def test_proof_lines_layout():
    short = P.MP(P.Ax("a1", [F.Const("p0"), F.Const("p1")]), P.Hyp("h0"))
    assert metric.proof_lines(short) == 1
    big = _every_node_kind()[-1]
    wide = metric.proof_lines(big, width=10_000)
    narrow = metric.proof_lines(big, width=40)
    assert wide == 1 and narrow > 1
    # narrower never means fewer lines
    assert metric.proof_lines(big, width=20) >= narrow


def test_proof_lines_on_fixture_corpus():
    for r in fx.corpus():
        assert metric.proof_lines(r["proof_ast"]) >= 1


def test_expansion_dag_counts_each_lemma_once_tree_per_use():
    order = ["M", "L", "T"]
    refs = {"M": {}, "L": {"M": 1}, "T": {"L": 2, "M": 1}}
    local = {"M": 1, "L": 2, "T": 3}
    dag = metric.expand_dag(order, refs, local)
    tree = metric.expand_tree(order, refs, local)
    assert dag == {"M": 1, "L": 3, "T": 6}
    # tree: L = 2 + 1; T = 3 + 2*3 + 1*1
    assert tree == {"M": 1, "L": 3, "T": 10}
    # a given premise is free and not expanded
    assert metric.expand_dag(order, refs, local, given={"L"})["T"] == 3 + 1
    assert metric.expand_tree(order, refs, local, given={"L"})["T"] == 3 + 1


def test_tree_stays_exact_when_huge():
    order = [f"x{i}" for i in range(200)]
    refs = {"x0": {}}
    for i in range(1, 200):
        refs[f"x{i}"] = {f"x{i - 1}": 2}
    local = {o: 1 for o in order}
    tree = metric.expand_tree(order, refs, local)
    assert tree["x199"] == 2 ** 200 - 1
    assert math.isclose(metric.log10_int(tree["x199"]), 200 * math.log10(2), rel_tol=1e-12)
    dag = metric.expand_dag(order, refs, local)
    assert dag["x199"] == 200


def test_interestingness_and_reward():
    assert metric.interestingness(7, 20) == Fraction(35)
    huge = 10 ** 400
    i = metric.interestingness(huge, 3)
    assert isinstance(i, Fraction)
    assert math.isclose(metric.log10_fraction(i), 402 - math.log10(3))
    assert math.isclose(metric.reward(5, 20), 0.25 + math.log(1 + 5 / 20))
    assert metric.utility(4, 9) == 36


def test_lemma_references_only_count_corpus_lemmas():
    recs = fx.corpus()
    refs = metric.lemma_references(recs)
    assert refs["t0_00001"] == {}
    assert refs["t1_00001"] == {"t0_00000": 1}
