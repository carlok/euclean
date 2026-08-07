"""The configuration grid.

Sprint 1 ran one seed context and reported what came out of it. The top-scoring
concepts turned out to be conjunctions of the assumptions that context happened
to make, which a single control run caught only by luck. The grid exists so that
"is this structure intrinsic or is it an echo of the setup" becomes a measurement
instead of a hunch.

Note what is *not* varied here: the theory identifier seed. Re-permuting the
opaque names means regenerating the Lean theory, and the generator that does
that necessarily knows the interpretation, so it lives outside the pipeline and
is driven from `tools/`. This module only ever sees whatever theory is currently
in place, and records its seed alongside the results.
"""

import itertools

PARAMS = (4, 6, 8)
DISTINCT = (False, "subset", "all")
LAYOUTS = ("random", "fixed")

# An ensemble member is not a scaled-down main run; it is one observation. The
# comparison across the grid needs many corpora built the same way, not a few
# deep ones, and the budget has to be identical everywhere or differences in
# what survives would just be differences in how long each member searched.
#
# The single-run defaults do not work here. Promotion multiplies the rule count
# each generation, and a per-rule derivation budget then multiplies with it —
# the first attempt at this grid ran one member for over ten minutes before
# being killed. These caps hold a member to roughly a minute.
BUDGET = {
    "rounds": 5,
    "derivations_per_rule_per_round": 60,
    "match_attempts": 5000,
    "generative_samples": 10,
    "max_facts": 2500,
    "max_scopes": 30,
    "max_case_splits": 6,
    "branch_rounds": 2,
    "time_budget": 20,
    "rewrites_per_equation": 25,
    "max_case_proof_size": 400,
    "case_split_depth": 2,
    "param_bias": 0.85,
}
PROMOTE_MAX = 25

# Two methods, one per view that the stability analysis actually consumes.
CLUSTER_METHODS = ("kmeans_numeric", "linkage_dependency")


def grid(repeats=1, base_seed=0, layouts=LAYOUTS):
    """Every combination, plus repetitions under different chainer seeds."""
    out = []
    n = 0
    for rep in range(repeats):
        for params, distinct, layout in itertools.product(PARAMS, DISTINCT, layouts):
            if layout == "fixed" and distinct == "subset":
                # the fixed layout is only kept as the sprint-1 reference point;
                # pairing it with every distinctness mode adds cost, not signal
                continue
            cfg = {
                **BUDGET,
                "params": params,
                "assume_distinct": distinct,
                "atom_layout": layout,
                "atoms_per_relation": 3 if layout == "fixed" else 5,
                "allow_repeats": True,
            }
            out.append(
                {
                    "id": f"p{params}-d{distinct}-{layout}-r{rep}",
                    "chainer_seed": base_seed + 100 * rep + n,
                    "config": cfg,
                }
            )
            n += 1
    return out


def describe(entry):
    c = entry["config"]
    return (
        f"{entry['id']:26s} params={c['params']} "
        f"distinct={str(c['assume_distinct']):6s} layout={c['atom_layout']}"
    )
