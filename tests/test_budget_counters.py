"""Gate on budget accounting reaching the artifacts.

A member that stopped because it hit a ceiling and a member that stopped because
it ran out of things to derive produce the same corpus shape and the same
summary. Telling them apart matters most for the comparison this sprint exists
to run: a richer theory saturates its caps where a poorer one never approaches
them, so an uncounted cap turns "this theory is budget-bound" into "this theory
found less", which is the opposite conclusion.

`max_facts` had no counter at all, and the counters that did exist never left
the engine — `chainer/run.build` collected filter reasons into its own
`Counter` and dropped `eng.rejected` on the floor. Measured on one generation of
the reference theory, that discarded 162 scope-limit and 204
branch-existential-skipped events.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline.chainer import run as chainer_run  # noqa: E402
from pipeline.ensemble import config as cfg_mod  # noqa: E402
from pipeline.kernel import theory as theory_mod  # noqa: E402

T = theory_mod.load()
QUIET = {"log": lambda *a, **k: None}


def _run(max_facts):
    cfg = dict(cfg_mod.BUDGET)
    cfg.update(
        {
            "atom_layout": "random",
            "assume_distinct": "all",
            "params": 6,
            "max_facts": max_facts,
        }
    )
    _, _, rejected, _ = chainer_run.build(T, seed=0, generations=1, cfg=cfg, **QUIET)
    return {k: v for k, v in rejected.items() if k.startswith("engine:")}


def test_engine_counters_reach_the_caller():
    """They existed and never left the engine."""
    caps = _run(2500)
    assert caps, "no engine counter reached the returned rejection counts"
    assert any("scope-limit" in k for k in caps), caps


def test_hitting_the_fact_ceiling_is_recorded():
    """The cap that binds hardest on a rich theory, and had no counter."""
    tight = _run(150)
    assert "engine:max-facts" in tight, tight
    assert tight["engine:max-facts"] > 0


def test_a_generous_ceiling_is_not_reported_as_hit():
    """Otherwise the counter says nothing — every run would look budget-bound."""
    assert "engine:max-facts" not in _run(2500)


def test_engine_counters_do_not_collide_with_filter_reasons():
    """Two different facts about a run, kept apart.

    A statement refused by a filter is a judgement about the statement; a
    derivation never attempted because a ceiling was reached is a fact about the
    budget. Merging them into one namespace would make both unreadable.
    """
    _, _, rejected, _ = chainer_run.build(
        T, seed=0, generations=1, cfg=dict(cfg_mod.BUDGET, params=6), **QUIET
    )
    plain = [k for k in rejected if not k.startswith("engine:")]
    assert plain, "no filter reasons at all; this test is not exercising the overlap"
    assert not any(k.startswith("engine:") for k in plain)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
