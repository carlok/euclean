"""Gate for the canonical relation map.

This function defines cross-run identity. Every survival number the project
publishes is a count of how many runs agreed on a canonical key, so if the map
is unstable, all of them are wrong — and wrong in the direction of the headline
result, because instability looks exactly like "structure does not survive
re-anonymization".

It had no tests at all until this file, and it was broken. Its ordering
fingerprint could not separate two relations of the same arity that occur in the
same syntactic roles, `sorted` is stable, so the order fell through to the
iteration order of the `relations` dict — JSON key order, which the anonymizer
permutes per seed.

`test_map_is_invariant_under_relabelling` is the test that would have caught it.
"""

import itertools
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.canon import relations as R  # noqa: E402
from pipeline.kernel import theory  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "runs" / "admissibility" / "candidate-spec.json"


def _load(spec):
    return theory.Theory(spec)


def _relabel(obj, perm):
    """Rename relation symbols throughout a spec, as the anonymizer does."""
    if isinstance(obj, dict):
        out = {k: _relabel(v, perm) for k, v in obj.items()}
        if out.get("kind") == "atom" and out["rel"] in perm:
            out["rel"] = perm[out["rel"]]
        return out
    if isinstance(obj, list):
        return [_relabel(x, perm) for x in obj]
    return obj


def _specs():
    """Every spec available, so the properties are checked on real theories."""
    out = [("incumbent", json.loads((ROOT / "theory" / "spec.json").read_text()))]
    if CANDIDATE.exists():
        out.append(("candidate", json.loads(CANDIDATE.read_text())))
    return out


def test_map_is_invariant_under_relabelling():
    """The canonical name must follow the relation, not its identifier.

    This is the whole contract. A grid re-permutes identifiers across theory
    seeds, so if the name follows the label instead, keys from different seeds
    never coincide and survival collapses toward chance on its own.
    """
    for name, spec in _specs():
        rels = sorted(spec["relations"])
        base = R.canonical_map(_load(spec))
        for p in itertools.permutations(rels):
            perm = dict(zip(rels, p))
            moved = _relabel(json.loads(json.dumps(spec)), perm)
            moved["relations"] = {perm[k]: v for k, v in spec["relations"].items()}
            got = R.canonical_map(_load(moved))
            for r in rels:
                assert got[perm[r]] == base[r], (
                    f"{name}: relabelling {perm} moved {r} from {base[r]} to "
                    f"{got[perm[r]]}; the canonical name is following the identifier "
                    "rather than the relation"
                )


def test_map_ignores_declaration_order():
    """Reordering the `relations` object must change nothing.

    The narrower statement of the bug: nothing but JSON key order changed, and
    two relations swapped canonical names.
    """
    for name, spec in _specs():
        base = R.canonical_map(_load(spec))
        for order in itertools.permutations(spec["relations"]):
            shuffled = dict(spec)
            shuffled["relations"] = {k: spec["relations"][k] for k in order}
            assert R.canonical_map(_load(shuffled)) == base, (
                f"{name}: declaration order {order} produced a different map"
            )


def test_incumbent_map_is_unchanged():
    """Pinned, because every stored artifact is keyed by it.

    A change here would silently invalidate the existing 45-member grid against
    anything measured after it.
    """
    spec = json.loads((ROOT / "theory" / "spec.json").read_text())
    got = R.canonical_map(_load(spec))
    assert got == {"R0": "Rel3_0", "R1": "Rel4_0"}, got


def test_same_arity_relations_are_separated():
    """The candidate is the first theory with two relations of equal arity.

    Before refinement these tied on every component of the fingerprint. They are
    genuinely distinguishable — the swap is not an automorphism of the axiom set
    — so the map must separate them rather than fall back on declaration order.
    """
    if not CANDIDATE.exists():
        print("  (no candidate spec; skipping)")
        return
    spec = json.loads(CANDIDATE.read_text())
    got = R.canonical_map(_load(spec))
    assert len(set(got.values())) == len(got), f"two relations share a canonical name: {got}"

    by_arity = {}
    for rel, arity in spec["relations"].items():
        by_arity.setdefault(arity, []).append(rel)
    assert any(len(v) > 1 for v in by_arity.values()), (
        "this test is vacuous unless the candidate really has two relations of "
        "the same arity; the spec appears to have changed"
    )


def test_a_genuine_symmetry_raises_instead_of_guessing():
    """Two relations that really are interchangeable have no canonical order.

    Refinement cannot separate them because there is nothing to separate. The
    honest response is to fail, not to return an order taken from dict layout —
    that order would be seed-dependent and every downstream number silently
    wrong.
    """
    spec = {
        "sort": "Obj",
        "relations": {"S0": 2, "S1": 2},
        "axioms": [
            {
                "name": "b0",
                "formula": {
                    "kind": "forall",
                    "vars": ["x", "y"],
                    "body": {
                        "kind": "imp",
                        "lhs": {"kind": "atom", "rel": "S0", "args": [
                            {"kind": "var", "name": "x"}, {"kind": "var", "name": "y"}]},
                        "rhs": {"kind": "atom", "rel": "S0", "args": [
                            {"kind": "var", "name": "y"}, {"kind": "var", "name": "x"}]},
                    },
                },
            },
            {
                "name": "b1",
                "formula": {
                    "kind": "forall",
                    "vars": ["x", "y"],
                    "body": {
                        "kind": "imp",
                        "lhs": {"kind": "atom", "rel": "S1", "args": [
                            {"kind": "var", "name": "x"}, {"kind": "var", "name": "y"}]},
                        "rhs": {"kind": "atom", "rel": "S1", "args": [
                            {"kind": "var", "name": "y"}, {"kind": "var", "name": "x"}]},
                    },
                },
            },
        ],
    }
    try:
        got = R.canonical_map(_load(spec))
    except ValueError:
        return
    raise AssertionError(
        f"an interchangeable pair was given an order anyway: {got}. That order comes "
        "from declaration order and would change with the seed."
    )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
