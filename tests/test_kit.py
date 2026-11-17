"""interestkit on hand-built libraries: every quantity checked against a value
worked out by hand."""

import json
import math
import pathlib
import sys
from fractions import Fraction

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit"))

from interestkit import Library, evaluate, filters, loop, metric  # noqa: E402

DEFS = {"Obj": {"statement": "Type", "uses": []},
        "R": {"statement": "Obj → Obj → Prop", "uses": ["Obj"]},
        "Q": {"statement": "Obj → Prop", "uses": ["Obj"]}}


def toy():
    """a0, a1 axioms; t1 cites a0; t2 cites t1 twice and a1; t3 cites t1 and t2."""
    return Library(DEFS, [
        {"name": "a0", "axiom": True, "statement": "∀ (x : Obj), R x x", "uses": ["Obj", "R"]},
        {"name": "a1", "axiom": True, "statement": "∀ (x : Obj), Q x", "uses": ["Obj", "Q"]},
        {"name": "t1", "statement": "∃ (x : Obj), R x x", "uses": ["Obj", "R"],
         "premises": {"a0": 1}, "cost": {"loc": 2}},
        {"name": "t2", "statement": "∃ (x : Obj), R x x ∧ Q x", "uses": ["Obj", "Q", "R"],
         "premises": {"t1": 2, "a1": 1}, "cost": {"loc": 3}},
        {"name": "t3", "statement": "∃ (y : Obj), Q y", "uses": ["Obj", "Q"],
         "premises": {"t1": 1, "t2": 1}, "cost": {"loc": 5}},
    ], costs=["loc"])


def test_premise_expansion_set_and_tree():
    lib = toy()
    dag = metric.proof_cost(lib, "loc", "dag")
    tree = metric.proof_cost(lib, "loc", "tree")
    assert dag == {"a0": 0, "a1": 0, "t1": 2, "t2": 5, "t3": 10}       # t3: 5 + t1 2 + t2 3
    assert tree == {"a0": 0, "a1": 0, "t1": 2, "t2": 7, "t3": 14}      # t2: 3 + 2*2; t3: 5 + 2 + 7


def test_given_lemmas_are_free_and_not_expanded():
    lib = toy()
    assert metric.proof_cost(lib, "loc", "dag", given={"t2"})["t3"] == 5 + 2   # t1 still paid
    assert metric.proof_cost(lib, "loc", "dag", given={"t1", "t2"})["t3"] == 5


def test_description_length_counts_definitions_not_in_the_premises():
    lib = toy()
    s = len("∃ (x : Obj), R x x ∧ Q x")
    defs = len("Type") + len("Obj → Obj → Prop") + len("Obj → Prop")
    assert metric.description_length(lib, "t2") == s + defs
    # P = {t1} supplies Obj and R, so only Q's declaration is still owed
    assert metric.description_length(lib, "t2", given={"t1"}) == s + len("Obj → Prop")


def test_i0_u0_and_reward():
    lib = toy()
    i0 = metric.i0(lib)
    L = metric.description_length(lib, "t3")
    assert i0["t3"] == Fraction(100 * 10, L)
    users = lib.direct_users()
    assert users["t1"] == 2 and users["t2"] == 1 and users["t3"] == 0
    assert metric.u0(lib)["t1"] == 2 * 2
    r = metric.reward(i0["t3"])
    assert math.isclose(r, 0.25 + math.log(1 + 10 / L))
    assert metric.reward(parse_failure=True) == -0.5
    assert metric.reward(irrelevant=True) == -0.25
    assert metric.reward(i0["t3"], trivial=True) == 0.0


def test_huge_costs_stay_exact():
    big = 10 ** 400
    assert math.isclose(metric.log10(Fraction(100 * big, 7)), 402 - math.log10(7))
    assert math.isclose(metric.reward(Fraction(100 * big, 7)), 0.25 + (400 - math.log10(7)) * math.log(10),
                        rel_tol=1e-9)


def test_library_rejects_bad_input(tmp_path):
    with pytest.raises(ValueError, match="not listed before"):
        Library(DEFS, [{"name": "t", "statement": "x", "uses": [], "premises": {"a": 1}, "cost": {"loc": 1}}])
    with pytest.raises(ValueError, match="undefined"):
        Library(DEFS, [{"name": "t", "statement": "x", "uses": ["Nope"], "cost": {"loc": 1}}])
    with pytest.raises(ValueError, match="axiom"):
        Library(DEFS, [{"name": "a", "axiom": True, "statement": "x", "uses": []},
                       {"name": "b", "axiom": True, "statement": "y", "uses": [], "premises": {"a": 1}}])
    lib = toy()
    p = tmp_path / "lib.jsonl"
    lib.save(p)
    again = Library.load(p)
    assert [d["name"] for d in again.decls] == [d["name"] for d in lib.decls]
    assert metric.proof_cost(again) == metric.proof_cost(lib)


def test_restatement_filter_and_sweep():
    assert filters.jaccard(frozenset("ab"), frozenset("ab")) == 1.0
    prem = ["∀ (x : Obj), R x x"]
    assert filters.is_restatement("∀ (y : Obj), R y y", prem, threshold=0.7)
    assert not filters.is_restatement("∃ (x : Obj), Q x", prem, threshold=0.7)
    rows = filters.sweep([("∀ (y : Obj), R y y", prem), ("∃ (x : Obj), Q x", prem)], [True, False])
    flagged = [r["flagged"] for r in rows]
    assert flagged == sorted(flagged, reverse=True)          # stricter threshold, fewer flagged
    assert rows[0]["recall"] == 1.0


def test_relevance_ignores_bound_variables_and_generic_names():
    assert filters.lean_bound_names("∀ (x y : Obj), ∃ (z : Obj), R x z") >= {"x", "y", "z"}
    assert filters.is_relevant("∀ (x : Obj), R x x", ["∀ (y : Obj), R y y"], generic={"Obj"})
    assert not filters.is_relevant("∀ (x : Obj), Q x", ["∀ (x : Obj), R x x"], generic={"Obj"})


def test_loop_respects_premises_and_is_seeded():
    lib = toy()
    h = loop.run(lib, loop.proof_size_rule(), rounds=3, promote=1)
    assert [x["promoted"] for x in h] == [["t1"], ["t2"], ["t3"]]
    everything = loop.run(lib, None, rounds=1)
    assert everything[0]["promoted"] == ["t1"]                # only t1's premises are axioms
    r1 = loop.run(lib, loop.random_rule(3), rounds=3, promote=1, seed=5)
    r2 = loop.run(lib, loop.random_rule(3), rounds=3, promote=1, seed=5)
    assert r1 == r2
    assert loop.share(["t1", "t2"], {"t1": True}) == Fraction(1, 2)


def test_spearman_and_enrichment():
    a = {"p": 1, "q": 2, "r": 3, "s": 4}
    assert math.isclose(evaluate.spearman(a, {"p": 10, "q": 20, "r": 30, "s": 40}), 1.0)
    assert math.isclose(evaluate.spearman(a, {"p": 4, "q": 3, "r": 2, "s": 1}), -1.0)
    scores = {f"n{i}": i for i in range(100)}
    flag = {f"n{i}": i >= 90 for i in range(100)}
    res = evaluate.topk_enrichment(scores, flag, k=10, resamples=200)
    assert res["share"] == 1.0 and res["enriched"] and not res["depleted"]
    q = evaluate.filter_quality({"n1", "n95"}, truth={"n95", "n96"}, negative={"n1", "n2", "n3", "n4"})
    assert q["recall"] == 0.5 and q["fpr"] == 0.25 and q["youden_j"] == 0.25


def test_near_duplicates_are_one_hypothesis_apart():
    a = "∀ (x : Obj) (y : Obj), (¬ (x = y)) → R x y → R y x"
    b = "∀ (x : Obj) (y : Obj), Q x → R x y → R y x"            # one hypothesis swapped
    c = "∀ (x : Obj) (y : Obj), R x y → R y x"                  # one dropped
    d = "∀ (x : Obj) (y : Obj), Q x → Q y → R y x"              # two changed
    e = "∀ (x : Obj) (y : Obj), (¬ (x = y)) → R x y → R x x"    # other conclusion
    assert evaluate.split_statement(a) == ("(x : Obj) (y : Obj)", ("(¬ (x = y))", "R x y"), "R y x")
    assert evaluate.one_hypothesis_apart(a, b)
    assert evaluate.one_hypothesis_apart(a, c)
    assert not evaluate.one_hypothesis_apart(a, d)
    assert not evaluate.one_hypothesis_apart(a, e)
    # d is two changes from a but one from b (Q x kept, R x y -> Q y), so a, b, d all
    # have a partner and only e is alone
    assert evaluate.near_duplicate_share([a, b, d, e]) == 0.75
