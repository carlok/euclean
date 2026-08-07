"""Gate for the admissibility probe.

The load-bearing test is the first one. A probe that condemns the theory the
project has been using for four sprints is a broken probe, and everything it
says about a candidate would be worthless. Running it against the incumbent is
therefore not a smoke test — it is the calibration, and it already earned its
keep: the incumbent has one axiom that is not a rule but *is* deliberately
seeded, and an earlier reading of the rule would have called that inert and
failed the incumbent.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.admissibility import probe as probe_mod, verdict as verdict_mod  # noqa: E402
from pipeline.kernel import theory  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "admissibility"


def _report(label):
    p = OUT / f"probe-{label}.json"
    return json.loads(p.read_text()) if p.exists() else None


def test_probe_does_not_condemn_the_incumbent():
    """The calibration. If this fails, no candidate result means anything."""
    rep = _report("incumbent")
    if rep is None:
        print("  (no incumbent probe; skipping)")
        return
    assert not rep["inert_axioms"], (
        f"the probe calls the incumbent's axioms {rep['inert_axioms']} inert. The "
        "incumbent works; the probe is wrong."
    )
    assert rep["axes"]["concept_candidates"]["min"] > 0
    assert rep["axes"]["distinct_statements"]["min"] > 0


def test_seeded_axiom_is_not_reported_inert():
    """A bare existential opened at startup is intended, not broken."""
    T = theory.load()
    rows = probe_mod.axiom_liveness(T, seed=0)
    seeded = [r for r in rows if r["deliberately_seeded"]]
    assert seeded, "the incumbent has a deliberately seeded axiom; none was detected"
    for r in seeded:
        assert not r["inert"], f"{r['axiom']} is seeded but was reported inert"


def test_idle_is_distinguished_from_inert():
    """Contributing nothing at a short budget is not the same as being unusable."""
    rep = _report("incumbent")
    if rep is None:
        print("  (no incumbent probe; skipping)")
        return
    assert set(rep["idle_at_this_budget"]).isdisjoint(rep["inert_axioms"])


def test_a_win_requires_disjoint_ranges():
    """Means alone would let seed variance decide admissibility."""
    better_mean_overlapping = {"min": 5, "max": 40, "mean": 25.0}
    baseline = {"min": 1, "max": 30, "mean": 12.0}
    assert not verdict_mod.wins(better_mean_overlapping, baseline)
    assert verdict_mod.wins({"min": 31, "max": 60, "mean": 45.0}, baseline)


def test_unevaluated_condition_is_not_a_pass():
    """A condition nobody checked must not read as satisfied."""
    rep = _report("incumbent")
    if rep is None:
        print("  (no incumbent probe; skipping)")
        return
    v = verdict_mod.evaluate(rep, rep, calibrated=None)
    assert not v["admissible"], "a verdict was declared with a condition unevaluated"
    assert "target calibration succeeds" in v["unevaluated_conditions"]


def test_verdict_names_its_failing_condition():
    rep = _report("incumbent")
    if rep is None:
        print("  (no incumbent probe; skipping)")
        return
    # a theory compared against itself cannot win any axis
    v = verdict_mod.evaluate(rep, rep, calibrated=True)
    assert not v["admissible"]
    assert v["first_failing_condition"] == "richer on a majority of axes"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
