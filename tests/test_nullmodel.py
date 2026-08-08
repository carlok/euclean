"""Gate for the chance reference on concept survival.

Survival counts were published for four sprints with no scale beside them. This
module supplies the scale, so its own arithmetic needs to be pinned — a wrong
reference is worse than none, because it would license a claim rather than
withhold one.

The property that matters most is `test_no_key_is_ranked_where_it_was_absent`.
The census re-mines each member's pool, and if it re-mines with parameters the
grid did not use, every conditional figure is computed against the wrong
denominator while still looking entirely reasonable.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.ensemble import nullmodel as NM  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENS = ROOT / "runs" / "ens"


def _member(mid, pool, ranked_keys, source="premise-conjunction"):
    field = NM.POOL_FIELD[source]
    return {
        "summary": {"id": mid, field: pool},
        "concepts": [{"canonical_key": k, "source": source} for k in ranked_keys],
    }


def test_chance_is_the_ranked_fraction_of_the_pool():
    """Ten ranked out of forty is a one-in-four shot, per member."""
    members = [_member(f"m{i}", 40, [f"k{j}" for j in range(10)]) for i in range(4)]
    ref = NM.chance_reference(members)["premise-conjunction"]
    assert ref["expected_survival"] == 1.0, ref
    assert ref["members"] == 4


def test_a_pool_smaller_than_the_cut_is_certain():
    """When every candidate is ranked, presence in the pool guarantees survival."""
    members = [_member(f"m{i}", 3, ["a", "b", "c"]) for i in range(5)]
    ref = NM.chance_reference(members)["premise-conjunction"]
    assert ref["expected_survival"] == 5.0, ref


def test_an_empty_pool_is_vacuous_not_zero():
    """A source with nothing to rank is not evidence that nothing survived.

    Counting it as a zero would quietly drag the reference down and make a null
    result look better calibrated than it is.
    """
    members = [_member("m0", 0, []), _member("m1", 10, ["a", "b"])]
    ref = NM.chance_reference(members)["premise-conjunction"]
    assert ref["vacuous_members"] == 1, ref
    assert ref["members_with_a_pool"] == 1
    assert ref["expected_survival"] == 0.2, ref


def test_the_reference_scales_against_pool_size():
    """The reason raw survival cannot be compared across two theories.

    A richer theory produces a larger pool, so a fixed cut ranks a smaller
    fraction of it and every one of its concepts is less likely to survive
    before any content is considered.
    """
    small = [_member(f"m{i}", 20, [f"k{j}" for j in range(10)]) for i in range(10)]
    large = [_member(f"m{i}", 60, [f"k{j}" for j in range(10)]) for i in range(10)]
    a = NM.chance_reference(small)["premise-conjunction"]["expected_survival"]
    b = NM.chance_reference(large)["premise-conjunction"]["expected_survival"]
    assert a > b, (a, b)
    assert round(a, 1) == 5.0 and round(b, 1) == 1.7, (a, b)


def test_no_key_is_ranked_where_it_was_absent():
    """The census must reproduce the grid's own pools.

    Runs against the stored grid rather than a fixture, because the failure this
    catches is a drift between the mining parameters used here and the ones the
    grid ran with. `pool_presence` raises on violation; this pins that it does
    not raise on the real artifacts.
    """
    if not ENS.exists() or not any(ENS.glob("*/corpus.json")):
        print("  (no stored grid; skipping)")
        return
    census = NM.pool_presence(log=lambda *a: None)
    assert census["members"] > 0
    for r in census["rows"]:
        assert r["ranked_in"] <= r["in_pool_of"], r


def test_the_census_finds_the_availability_ceiling():
    """The finding this module exists to state, pinned against the stored grid.

    Concept survival is capped by whether a concept is minable at all across
    configurations, not by the ranking cut. If a key ever does appear in every
    member's pool, the unconditional reference becomes reachable and this test
    should be revisited rather than silently kept passing.
    """
    if not ENS.exists() or not any(ENS.glob("*/corpus.json")):
        print("  (no stored grid; skipping)")
        return
    summary = NM.presence_summary(NM.pool_presence(log=lambda *a: None))
    for source, s in summary.items():
        assert s["best_presence"] < s["members"], (
            f"{source}: a concept is now available in every member, so the "
            f"unconditional chance reference applies and the reading of "
            f"'below chance' has to be redone"
        )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
