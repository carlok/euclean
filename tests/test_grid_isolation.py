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


def test_legacy_members_are_the_reference_grid():
    """Artifacts written before these fields existed must stay readable.

    They are all incumbent, base seed 0. If the defaults changed, the stored
    grid would vanish from every selector at once.
    """
    assert grids.identity({}) == (grids.subject(), grids.REFERENCE_BASE_SEED)
    assert grids.matches({}) is True


def test_a_replicate_is_not_the_reference_grid():
    assert grids.matches({"base_seed": 100}) is False
    assert grids.matches({"base_seed": 100}, base_seed=100) is True


def test_a_second_theory_is_not_the_reference_grid():
    """The property the whole control comparison depends on."""
    other = grids.roles()["control"]
    assert grids.matches({"theory": other}) is False
    assert grids.matches({"theory": other}, theory=other) is True


def test_selecting_one_grid_excludes_the_others():
    if not ENS.exists() or not _has_several_grids():
        print("  (fewer than two grids on disk; skipping)")
        return
    dirs = grids.member_dirs()
    seen = {grids.identity(json.loads((d / "summary.json").read_text())) for d in dirs}
    assert seen == {(grids.subject(), grids.REFERENCE_BASE_SEED)}, seen
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


def test_lean_and_python_must_agree_on_the_axioms():
    """The mismatch that becomes possible as soon as there are two theories.

    "Which axioms Python reasons about" and "which axioms Lean checks against"
    used to be the same thing, because both were whatever sat in `theory/`. The
    generator rewrites that directory in place, so they are now independent, and
    the symptom of a mismatch is every batch rejected — which reads as a theory
    that derives nothing rather than as a configuration error.
    """
    from pipeline.kernel import theory as theory_mod, verify

    # Whichever theory is in place must match its own Lean module. The generator
    # rewrites theory/ as it cycles, so the test must not assume which one it is.
    T = theory_mod.load()
    verify.assert_theory_matches(T)

    # A signature that cannot match anything: same relations, wrong arities.
    mismatched = theory_mod.Theory(
        {
            "sort": T.sort,
            "relations": {r: a + 1 for r, a in T.relations.items()},
            "axioms": [],
        }
    )
    try:
        verify.assert_theory_matches(mismatched)
    except verify.VerificationError:
        return
    raise AssertionError(
        "a theory whose relation arities differ from the Lean base module was "
        "accepted; Python and Lean can now silently disagree about the axioms"
    )


def test_the_spec_hash_separates_labellings_not_just_theories():
    """The hash must move when the identifiers move.

    An earlier version of this test changed only the `seed` field and concluded
    the hash was relabelling-invariant. It is not, and it must not be: the
    failure it exists to catch is a corpus built under one identifier
    permutation being measured against another, and a relabelling-invariant hash
    would call those two identical.

    Uses the candidate spec, which has two relations of equal arity, so a
    permutation genuinely changes the formulas.
    """
    from pipeline.kernel import theory as theory_mod

    cand = ROOT / "runs" / "admissibility" / "candidate-spec.json"
    if not cand.exists():
        print("  (no candidate spec; skipping)")
        return
    spec = json.loads(cand.read_text())
    base = theory_mod.spec_hash(spec)

    # metadata does not change the content
    assert theory_mod.spec_hash(dict(spec, seed=(spec.get("seed") or 0) + 7)) == base, (
        "the hash moved on a seed field change alone, which is metadata"
    )

    # relabelling does
    perm = {"R0": "R1", "R1": "R0", "R2": "R2"}
    moved = _relabel(json.loads(json.dumps(spec)), perm)
    moved["relations"] = {perm[k]: v for k, v in spec["relations"].items()}
    assert theory_mod.spec_hash(moved) != base, (
        "the hash survived a relabelling, so it cannot detect a corpus measured "
        "against a differently permuted theory — the bug it exists to catch"
    )

    # Deliberately not compared against theory/spec.json: the generator rewrites
    # that file in place, so a test reading it depends on whatever ran last.


def test_wanting_every_theory_is_not_the_same_as_not_saying():
    """These were the same value for one commit, and it cost the reference grid.

    `theory=None` means the recorded subject; wanting every theory is a
    different request and must say so. When both were `None`, asking for the
    reference grid returned 90 members instead of 45 — plausible, silent, and
    exactly the failure this module exists to prevent.
    """
    if not ENS.exists() or not _has_several_grids():
        print("  (fewer than two grids on disk; skipping)")
        return
    one = len(grids.member_dirs())
    every = len(grids.member_dirs(theory=grids.ANY))
    assert one < every, (
        f"asking for the default grid returned {one} and asking for every theory "
        f"returned {every}; the two requests are not distinguished"
    )


def test_no_domain_name_reaches_the_public_tree():
    """Theory identities are opaque codes, everywhere a reader can see them.

    Names chosen to be useful to us are names that describe the domain, so a
    directory listing of the grid would otherwise give away what the
    anonymization protects.
    """
    import re

    pattern = re.compile(r"^t[0-9a-f]{7}$")
    seen = {t for t, _ in grids.present()}
    if not seen:
        print("  (no members; skipping)")
        return
    bad = sorted(t for t in seen if not pattern.match(t))
    assert not bad, f"theory labels that are not codes: {bad}"

    for name in ("roles.json",):
        p = ROOT / "runs" / "ensemble" / name
        if p.exists():
            for key, value in json.loads(p.read_text()).items():
                if key == "note":
                    continue
                assert pattern.match(value), f"{name}: {key} is {value!r}, not a code"


def test_a_missing_grid_is_empty_rather_than_everything():
    """Asking for a grid that is not there must not fall back to all of them."""
    assert grids.member_dirs(theory="no-such-theory") == []
    assert grids.total("kept", theory="no-such-theory") == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
