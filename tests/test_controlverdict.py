"""Gate for the pre-registered control rule.

The rule decides whether the project's headline negative result is a fact about
the method or only about one theory. It was written before either grid ran, and
these tests exist so that it cannot be quietly loosened afterwards — the failure
mode is not a crash but a bar that drifts until the data clears it.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.ensemble import controlverdict as CV  # noqa: E402

SRC = "premise-conjunction"


def _bundle(label, rates, budget="B", vacuous=0.0, bound=False):
    """`rates` maps base seed -> best availability rate for one source."""
    return {
        "label": label,
        "budget": budget,
        "vacuous_fraction": vacuous,
        "budget_bound": bound,
        "availability": {
            str(seed): {SRC: {"best_presence_rate": r}} for seed, r in rates.items()
        },
    }


def test_overlapping_ranges_are_not_a_difference():
    """The rule the project already applies everywhere else.

    A control that is higher on average but whose range overlaps the
    incumbent's has not shown anything. This project has read sampling noise as
    an effect once already.
    """
    control = _bundle("candidate", {0: 0.50, 100: 0.30})
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["sources"][0]["disjoint_and_higher"] is False
    assert v["shows_survival"] is False


def test_disjoint_and_higher_passes():
    control = _bundle("candidate", {0: 0.72, 100: 0.68})
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["sources"][0]["disjoint_and_higher"] is True
    assert v["shows_survival"] is True, v["first_failing_condition"]


def test_higher_but_below_is_not_a_pass():
    """Disjointness alone is not enough; direction matters."""
    control = _bundle("candidate", {0: 0.10, 100: 0.12})
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["sources"][0]["disjoint_and_higher"] is False
    assert v["shows_survival"] is False


def test_a_single_grid_withholds_the_verdict():
    """One run is not a measurement. Without replicates there is no scale."""
    control = _bundle("candidate", {0: 0.72})
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["shows_survival"] is False
    names = [c["condition"] for c in v["conditions"] if c["passed"] is False]
    assert any("noise floor" in n for n in names), v["conditions"]


def test_a_budget_difference_blocks_the_comparison():
    """Otherwise a budget difference and a theory difference look identical."""
    control = _bundle("candidate", {0: 0.72, 100: 0.68}, budget="reduced")
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34}, budget="full")
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["shows_survival"] is False
    assert "budget" in v["first_failing_condition"]


def test_a_vacuous_control_grid_blocks_the_comparison():
    """A null from members that could not produce a candidate is not a null."""
    control = _bundle("candidate", {0: 0.72, 100: 0.68}, vacuous=0.8)
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["shows_survival"] is False
    assert "vacuous" in v["first_failing_condition"]


def test_an_unmeasured_condition_withholds_rather_than_passes():
    """A condition that was not checked is not a condition that passed."""
    control = _bundle("candidate", {0: 0.72, 100: 0.68})
    control["vacuous_fraction"] = None
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["shows_survival"] is False
    assert v["unevaluated_conditions"], v["conditions"]


def test_a_zero_width_band_still_requires_one_member_of_separation():
    """The incumbent's quantified band is exactly [0.356, 0.356] on real data.

    All three replicates gave 16/45. Availability is a count over members, so it
    moves in steps of 1/45; three samples landing on the same quantized value is
    not evidence of zero variance, and reading that band literally would let a
    single member decide the whole comparison.
    """
    incumbent = _bundle("incumbent", {0: 0.356, 100: 0.356, 200: 0.356})
    incumbent["members"] = 135

    just_above = _bundle("candidate", {0: 0.370, 100: 0.370})
    just_above["members"] = 90
    v = CV.evaluate(just_above, incumbent, sources=(SRC,))
    assert v["sources"][0]["disjoint_and_higher"] is False, (
        "a difference smaller than one member was counted as a separation"
    )

    clear = _bundle("candidate", {0: 0.400, 100: 0.400})
    clear["members"] = 90
    v = CV.evaluate(clear, incumbent, sources=(SRC,))
    assert v["sources"][0]["disjoint_and_higher"] is True
    assert v["sources"][0]["margin_required"] > 0


def test_the_margin_comes_from_the_smaller_grid():
    """So the bar is never easier than the coarser of the two instruments."""
    incumbent = _bundle("incumbent", {0: 0.3, 100: 0.3})
    incumbent["members"] = 40  # 20 per replicate, resolution 1/20
    control = _bundle("candidate", {0: 0.34, 100: 0.34})
    control["members"] = 180  # 90 per replicate, resolution 1/90
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["sources"][0]["margin_required"] == 0.05, v["sources"][0]
    assert v["sources"][0]["disjoint_and_higher"] is False


def test_a_truncated_control_that_clears_the_bar_still_counts():
    """Truncation biases availability downward, so clearing it anyway is safe.

    A smaller corpus carries fewer distinct premise patterns, so fewer concepts
    recur across members. That pushes the control's availability down, never up
    — a control that clears the bar while truncated would only have cleared it
    by more without the ceiling.
    """
    control = _bundle("candidate", {0: 0.72, 100: 0.68}, bound=True)
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["shows_survival"] is True, v["first_failing_condition"] or v[
        "unevaluated_conditions"
    ]


def test_a_truncated_control_that_fails_withholds_rather_than_concludes():
    """The asymmetry that decides how much compute this comparison needs.

    A downward-biased failure cannot distinguish "this theory has no recurring
    concepts" from "this theory ran out of fact budget". Reporting it as a null
    would be the strongest possible claim resting on the weakest evidence.
    """
    control = _bundle("candidate", {0: 0.20, 100: 0.22}, bound=True)
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["shows_survival"] is False
    assert any("truncated" in c for c in v["unevaluated_conditions"]), v["conditions"]


def test_an_untruncated_failure_is_a_real_null():
    """Without the ceiling, a failure is evidence and must not be withheld."""
    control = _bundle("candidate", {0: 0.20, 100: 0.22}, bound=False)
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["shows_survival"] is False
    assert not any("truncated" in c for c in v["unevaluated_conditions"]), v["conditions"]
    assert "disjoint" in v["first_failing_condition"]


def test_selection_quality_cannot_decide_the_verdict():
    """It is reported, never decisive; on the incumbent it is noise.

    Pinned because it is the most tempting thing to promote into the rule after
    seeing a table.
    """
    control = _bundle("candidate", {0: 0.10, 100: 0.12})
    control["selection_excess"] = 99.0
    incumbent = _bundle("incumbent", {0: 0.38, 200: 0.34})
    v = CV.evaluate(control, incumbent, sources=(SRC,))
    assert v["shows_survival"] is False, "selection quality moved the verdict"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
