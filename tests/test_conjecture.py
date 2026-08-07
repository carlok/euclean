"""Gate for conjecture generation.

The assertions here are mostly about honesty rather than function. A bounded
proof attempt is a semi-decision: reaching a statement proves it, failing to
reach one proves nothing. Two ways of quietly forgetting that would each have
produced a confident wrong answer in this sprint, and both are pinned down here.

  * Nothing may ever be labelled refuted. This pipeline has no counter-model
    machinery, so an unreached conjecture is unresolved and nothing more.
  * A yield must never be reported without the recall that bounds it. A source
    scoring 0% against a prover that recovers 18% of statements already known
    true has told you about the prover, not the source.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.canon import normalize as N  # noqa: E402
from pipeline.conjecture import attempt as attempt_mod, propose as propose_mod  # noqa: E402
from pipeline.kernel import theory  # noqa: E402

T = theory.load()
ROOT = pathlib.Path(__file__).resolve().parents[1]


def _corpus():
    p = ROOT / "runs" / "main" / "corpus.json"
    return json.loads(p.read_text()) if p.exists() else None


def test_proposals_are_new_statements():
    records = _corpus()
    if not records:
        print("  (no corpus at runs/main; skipping)")
        return
    known = {N.key(r["statement_ast"]) for r in records}
    for c in propose_mod.propose(records, per_source=10):
        if c["source"] in ("positive-control", "symmetry-control"):
            continue
        assert N.key(c["statement_ast"]) not in known, (
            f"{c['source']} proposed a statement already in the corpus"
        )


def test_symmetry_view_is_structurally_consistent():
    """A permutation the view calls a symmetry must canonicalize back."""
    records = _corpus()
    if not records:
        print("  (no corpus at runs/main; skipping)")
        return
    checked = 0
    for c in propose_mod.propose(records, per_source=10):
        if c["source"] != "symmetry-control":
            continue
        checked += 1
        assert c["structurally_identical"], (
            "views/symmetry reported a permutation as a symmetry, but applying it "
            "changes the canonical form"
        )
    assert checked > 0, "no symmetry controls were generated, so the view went unchecked"


def test_positive_controls_are_present_so_yields_can_be_read():
    records = _corpus()
    if not records:
        print("  (no corpus at runs/main; skipping)")
        return
    sources = {c["source"] for c in propose_mod.propose(records, per_source=10)}
    assert "positive-control" in sources, (
        "without known-true statements in the mix, a 0% yield cannot be told apart "
        "from a prover that reaches nothing"
    )


def test_nothing_is_ever_reported_as_refuted():
    path = ROOT / "runs" / "main" / "conjectures.json"
    if not path.exists():
        print("  (no conjectures.json; skipping)")
        return
    report = json.loads(path.read_text())
    allowed = {"proved", "unresolved", "consistent", "INCONSISTENT"}
    for r in report["results"]:
        assert r["outcome"] in allowed, f"unexpected outcome {r['outcome']!r}"
        assert "refut" not in r["outcome"].lower(), (
            "a bounded search cannot refute anything; this label claims otherwise"
        )
    assert report["attempt_recall"]["recall"] is not None, "yields reported without a ceiling"


def test_summarize_handles_a_source_with_no_successes():
    """Counter lookups must not blow up on a source that proved nothing."""
    results = [
        {"source": "symmetry", "outcome": "unresolved"},
        {"source": "symmetry", "outcome": "unresolved"},
    ]
    summary = attempt_mod.summarize(results)
    assert summary["by_source"]["symmetry"]["proved"] == 0
    assert summary["by_source"]["symmetry"]["yield"] == 0.0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
