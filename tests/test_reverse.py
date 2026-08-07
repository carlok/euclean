"""Gate for the transitive footprint and the subset search.

The footprint is the one computation here with no independent check on it. A
closure that silently under-reports would shrink every footprint, make every
minimisation look more impressive, and produce no error anywhere — so it is
tested against a hand-traced DAG whose answer is worked out by eye rather than
by the code under test.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.reverse import footprint as fp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
AXIOMS = ["a0", "a1", "a2", "a3"]


def _rec(rid, gen, axioms, lemmas):
    return {
        "id": rid,
        "generation": gen,
        "axiom_dependencies": axioms,
        "proof_dependencies": lemmas,
    }


def test_footprint_against_a_hand_traced_dag():
    """Worked out by eye:

        L0 cites a0            -> {a0}
        L1 cites a1            -> {a1}
        L2 cites a2 and L0     -> {a0, a2}
        T  cites a3, L1, L2    -> {a0, a1, a2, a3}

    T names one axiom and rests on four. That gap is the entire point of the
    computation, so it is the thing asserted.
    """
    records = [
        _rec("L0", 0, ["a0"], []),
        _rec("L1", 0, ["a1"], []),
        _rec("L2", 1, ["a2"], ["L0"]),
        _rec("T", 2, ["a3"], ["L1", "L2"]),
    ]
    foot, missing = fp.footprints(records, AXIOMS)
    assert not missing
    assert foot["L0"] == ["a0"]
    assert foot["L1"] == ["a1"]
    assert foot["L2"] == ["a0", "a2"]
    assert foot["T"] == ["a0", "a1", "a2", "a3"], foot["T"]
    assert len(records[-1]["axiom_dependencies"]) == 1, "the direct count should be 1"


def test_shared_dependency_is_not_double_counted():
    records = [
        _rec("L0", 0, ["a0"], []),
        _rec("L1", 1, ["a1"], ["L0"]),
        _rec("T", 2, [], ["L0", "L1"]),
    ]
    foot, _ = fp.footprints(records, AXIOMS)
    assert foot["T"] == ["a0", "a1"]


def test_missing_dependency_is_reported_not_swallowed():
    """A cited lemma that is not in the corpus must not quietly contribute zero."""
    records = [_rec("T", 0, ["a0"], ["nowhere"])]
    foot, missing = fp.footprints(records, AXIOMS)
    assert foot["T"] == ["a0"]
    assert "nowhere" in missing, "an absent dependency was silently treated as empty"


def test_a_cycle_is_an_error_not_an_empty_set():
    records = [
        _rec("A", 0, [], ["B"]),
        _rec("B", 0, [], ["A"]),
    ]
    try:
        fp.footprints(records, AXIOMS)
    except ValueError:
        return
    raise AssertionError("a dependency cycle was swallowed instead of raised")


def test_real_corpus_footprints_dominate_direct_citation():
    path = ROOT / "runs" / "main" / "footprints.json"
    if not path.exists():
        print("  (no footprints.json; skipping)")
        return
    data = json.loads(path.read_text())
    s = data["summary"]
    assert s["mean_transitive"] > s["mean_direct"], (
        "the transitive footprint is not larger than direct citation, which would "
        "mean the closure is not closing"
    )
    assert not data["missing_dependencies"], data["missing_dependencies"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
