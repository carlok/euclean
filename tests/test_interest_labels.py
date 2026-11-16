"""Restatement labels for the interestingness audit (arXiv:2609.28603's metric).

The toy corpus in `test_interest_fixtures` is built so every label is known by hand.
"""

import pytest

from pipeline.interest import labels as L
from pipeline.kernel import formula as F

from tests import test_interest_fixtures as fx


def _labels():
    rows = L.label_corpus(fx.corpus(), fx.theory(), lean_accepted=True)
    return {r["id"]: r for r in rows}


def test_tiers_on_the_toy_corpus():
    got = {k: v["label"] for k, v in _labels().items()}
    assert got == {
        "t0_00000": "R1",  # an instance of a0
        "t0_00001": "R2",  # a0's conclusion, every holder cites a0
        "t0_00002": "R2",
        "t0_00003": "N",
        "t1_00000": "R0",  # duplicates an earlier statement
        "t1_00001": "R0",
    }


def test_rule_and_evidence_recorded():
    lab = _labels()
    assert lab["t0_00000"]["evidence"]["R1"]["axiom"] == "a0"
    assert lab["t0_00000"]["evidence"]["R1"]["sufficient"] is True
    assert lab["t0_00001"]["evidence"]["R2"]["axiom"] == "a0"
    assert lab["t1_00001"]["fired"] == ["R0", "R1"]  # precedence: R0 first
    assert lab["t1_00001"]["footprint"] == ["a0"]  # through the cited lemma
    assert lab["t0_00003"]["footprint"] == ["a0", "a1"]


def test_r1_requires_lean_acceptance():
    rows = L.label_corpus(fx.corpus(), fx.theory(), lean_accepted=False)
    lab = {r["id"]: r for r in rows}
    assert lab["t0_00000"]["label"] == "N"
    assert lab["t0_00000"]["R1fp"] is True


def test_instance_matching_ignores_binder_order():
    a0 = fx.theory().env["a0"]
    v = F.Var
    # a0 with v0 := v1, v1 := v2, v2 := v0, binders listed in a different order
    stmt = F.Forall(["v0", "v1", "v2"], F.Imp(fx.R(v("v1"), v("v2")),
                                              F.Imp(fx.R(v("v2"), v("v0")), fx.R(v("v1"), v("v0")))))
    subs = L.instance_substitutions(a0, stmt)
    assert subs == [{"v0": "v1", "v1": "v2", "v2": "v0"}]
    # dropping a premise is not instantiation
    weaker = F.Forall(["v0", "v1"], F.Imp(fx.R(v("v0"), v("v1")), fx.R(v("v0"), v("v1"))))
    assert L.instance_substitutions(a0, weaker) == []


def test_freeze_and_verify(tmp_path):
    rows = list(_labels().values())
    path = tmp_path / "labels.jsonl"
    sha = L.write_labels(rows, path)
    back, got = L.read_labels(path, expect_sha256=sha)
    assert got == sha and len(back) == len(rows)
    path.write_text(path.read_text().replace('"N"', '"R2"', 1))
    with pytest.raises(ValueError):
        L.read_labels(path, expect_sha256=sha)
