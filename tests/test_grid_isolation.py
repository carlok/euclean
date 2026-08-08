"""Gate against pooling grids that must not be pooled.

`runs/ens/` now holds several grids: three replicates at different base seeds,
and a second theory to come. Every reader that walks the directory and sums what
it finds is wrong once that is true, and wrong in a way that produces plausible
numbers rather than an error.

The arithmetic, measured on the real tree: summing `kept` over every directory
gives 76,646 across 135 members, against 17,154 for the reference grid's 45. A
report built from the first number would show grid totals inflated 4.5x, and
every `coverage` figure — `len(items) / n_runs` — deflated by the same factor,
which reads as a genuine loss of breadth.

Three separate copies of that glob existed in `report/build.py`, which is how it
drifted in the first place. There is one selector now.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.ensemble import grids, stability  # noqa: E402
from pipeline.report import importance as importance_mod  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENS = ROOT / "runs" / "ens"


def _has_several_grids():
    return len(grids.present()) > 1


def test_legacy_members_are_the_reference_grid():
    """Artifacts written before these fields existed must stay readable.

    They are all incumbent, base seed 0. If the defaults changed, the stored
    grid would vanish from every selector at once.
    """
    assert grids.identity({}) == (grids.REFERENCE_THEORY, grids.REFERENCE_BASE_SEED)
    assert grids.matches({}) is True


def test_a_replicate_is_not_the_reference_grid():
    assert grids.matches({"base_seed": 100}) is False
    assert grids.matches({"base_seed": 100}, base_seed=100) is True


def test_a_second_theory_is_not_the_reference_grid():
    """The property the whole control comparison depends on."""
    assert grids.matches({"theory": "candidate"}) is False
    assert grids.matches({"theory": "candidate"}, theory="candidate") is True


def test_selecting_one_grid_excludes_the_others():
    if not ENS.exists() or not _has_several_grids():
        print("  (fewer than two grids on disk; skipping)")
        return
    dirs = grids.member_dirs()
    seen = {grids.identity(json.loads((d / "summary.json").read_text())) for d in dirs}
    assert seen == {(grids.REFERENCE_THEORY, grids.REFERENCE_BASE_SEED)}, seen
    assert len(dirs) < sum(grids.present().values()), (
        "the selector returned every member on disk, so it is not selecting"
    )


def test_totals_are_not_pooled():
    """The three globs that used to live in report/build.py."""
    if not ENS.exists() or not _has_several_grids():
        print("  (fewer than two grids on disk; skipping)")
        return
    pooled = sum(
        json.loads((d / "summary.json").read_text()).get("kept", 0)
        for d in ENS.iterdir()
        if d.is_dir() and (d / "summary.json").is_file()
    )
    assert grids.total("kept") < pooled, (
        "grid totals still sum over every directory; a report built from this "
        "would inflate every grid figure"
    )


def test_load_members_returns_one_grid():
    if not ENS.exists():
        print("  (no grid; skipping)")
        return
    members = stability.load_members()
    seen = {grids.identity(m["summary"]) for m in members}
    assert len(seen) == 1, f"load_members pooled {seen}"


def test_importance_aggregation_is_not_pooled():
    """`aggregate_over_grid` runs automatically inside `importance.main()`.

    Nobody chooses to call it, so a pooled default would silently reach every
    published coverage figure.
    """
    if not ENS.exists() or not _has_several_grids():
        print("  (fewer than two grids on disk; skipping)")
        return
    per_run, _ = importance_mod.aggregate_over_grid()
    assert len(per_run) == len(grids.member_dirs()), (
        f"aggregated {len(per_run)} runs but the reference grid has "
        f"{len(grids.member_dirs())}"
    )


def test_a_missing_grid_is_empty_rather_than_everything():
    """Asking for a grid that is not there must not fall back to all of them."""
    assert grids.member_dirs(theory="no-such-theory") == []
    assert grids.total("kept", theory="no-such-theory") == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
