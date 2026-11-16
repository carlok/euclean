"""The private Lean package and the tactic ladder of the interestingness audit
(Patel et al., arXiv:2609.28603). The package test runs Lean on a toy theory."""

import json
import shutil

import pytest

from pipeline.interest import lean, tactics
from pipeline.kernel.theory import ROOT

from tests import test_interest_fixtures as fx


def test_base_module_reproduces_the_committed_one():
    spec = json.loads((ROOT / "theory" / "spec.json").read_text())
    want = (ROOT / "theory" / "Theory" / "Anonymous.lean").read_text()
    assert lean.base_module(spec) == want


def test_error_lines_are_parsed():
    log = "Theory/Xtriv0000.lean:4:120: error: unsolved goals\nTheory/Xtriv0000.lean:7:3: warning: x\n"
    assert lean.failing_lines(log) == {4}


@pytest.mark.skipif(shutil.which("lean") is None, reason="needs the Lean toolchain")
def test_package_checks_a_corpus_and_runs_the_ladder(tmp_path):
    recs = fx.corpus()
    pkg = lean.Package(tmp_path / "lean", fx.SPEC).create()
    items = [[(r["id"], r["statement_ast"], r["proof_ast"]) for r in recs if r["generation"] == g]
             for g in (0, 1)]
    failures, modules = pkg.verify_corpus(items, log=lambda *a: None)
    assert failures == [] and modules == ["B0000", "B0001"]

    # a broken proof must be rejected, or acceptance means nothing
    bad = dict(recs[0])
    bad["proof_ast"] = recs[3]["proof_ast"]
    pkg2 = lean.Package(tmp_path / "lean2", fx.SPEC).create()
    failures, _ = pkg2.verify_corpus([[(bad["id"], bad["statement_ast"], bad["proof_ast"])]],
                                     log=lambda *a: None)
    assert failures

    results, meta = tactics.run_ladder(pkg, recs, modules, log=lambda *a: None)
    assert meta["incomplete_files"] == []
    # nothing here holds without an axiom, so the triviality rung closes nothing
    assert not any(results[r["id"]]["triv"] for r in recs)
    # given the premises its own proof cites, grind closes the single-step instance
    assert results["t0_00000"]["grind"] is True


@pytest.mark.skipif(shutil.which("lean") is None, reason="needs the Lean toolchain")
def test_a_file_with_many_failures_is_checked_to_the_end(tmp_path):
    """Lean gives up after 100 errors unless told otherwise; a tactic file is
    mostly expected failures, so the last declaration must still be reached."""
    pkg = lean.Package(tmp_path / "lean", fx.SPEC).create()
    body = ["import Theory.Anonymous", ""]
    body += [f"theorem bad{i} : ∀ (x : Obj), R0 x x := by simp" for i in range(150)]
    body += [f'#eval IO.println "{lean.SENTINEL}"']
    (pkg.src / "Many.lean").write_text("\n".join(body) + "\n")
    code, out = pkg.run("Many")
    assert code is not None and lean.SENTINEL in out
    assert len(lean.failing_lines(out)) == 150
