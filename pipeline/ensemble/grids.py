"""Choosing exactly one grid out of a directory that holds several.

`runs/ens/` was written when there was only ever one grid in it. There are now
three replicates at different base seeds, and a second theory is coming, so
every reader that walks the directory and sums what it finds is now wrong —
silently, and in a direction that looks like a real result.

The concrete failures this prevents:

- `report/importance.aggregate_over_grid` runs automatically inside
  `importance.main()`, and its `coverage` field is `len(items) / n_runs`.
  Pooling three replicates triples the denominator while any given key is
  reachable in at most one of them, so every coverage figure falls by two
  thirds and reads as a genuine loss of breadth.
- `report/build.py` summed grid totals in three separate places with three
  copies of the same glob. Three copies is how the drift happened; there is one
  selector now and they all call it.
- `ensemble/stability.concept_survival` divides by the member count, so pooling
  replicates halves or thirds every survival rate.

The default is the reference grid: base seed 0, the incumbent theory. That is
the grid every published number was computed from, and picking it by default
keeps those numbers reproducible rather than quietly re-derived from whatever
happens to be on disk.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENS = ROOT / "runs" / "ens"

# The grid every published figure comes from.
REFERENCE_BASE_SEED = 0
REFERENCE_THEORY = "incumbent"


def identity(summary):
    """`(theory, base_seed)` for a member, defaulted for artifacts predating them.

    Members written before these fields existed are all incumbent, base seed 0,
    so the defaults make the stored grid readable without rewriting it.
    """
    return (
        summary.get("theory", REFERENCE_THEORY),
        summary.get("base_seed", REFERENCE_BASE_SEED),
    )


def matches(summary, theory=REFERENCE_THEORY, base_seed=REFERENCE_BASE_SEED):
    """Does this member belong to the grid being asked for?

    `None` for either field means "do not filter on it" — used by tools that
    genuinely want everything, such as the noise floor, which then partitions
    the members itself.
    """
    t, b = identity(summary)
    if theory is not None and t != theory:
        return False
    if base_seed is not None and b != base_seed:
        return False
    return True


def member_dirs(ens=None, theory=REFERENCE_THEORY, base_seed=REFERENCE_BASE_SEED):
    """Directories of exactly one grid, in a stable order."""
    ens = ens or ENS
    if not ens.exists():
        return []
    out = []
    for d in sorted(ens.iterdir()):
        p = d / "summary.json"
        if d.is_dir() and p.is_file() and matches(json.loads(p.read_text()), theory, base_seed):
            out.append(d)
    return out


def summaries(ens=None, theory=REFERENCE_THEORY, base_seed=REFERENCE_BASE_SEED):
    """The summary dicts of exactly one grid."""
    return [json.loads((d / "summary.json").read_text()) for d in member_dirs(ens, theory, base_seed)]


def total(field, ens=None, theory=REFERENCE_THEORY, base_seed=REFERENCE_BASE_SEED):
    """Sum one summary field over exactly one grid."""
    return sum(s.get(field, 0) for s in summaries(ens, theory, base_seed))


def present(ens=None):
    """Every `(theory, base_seed)` pair on disk, with member counts.

    Reported so that a run against a directory holding more than one grid says
    so, rather than picking the default and leaving the reader to assume that
    was all there was.
    """
    ens = ens or ENS
    counts = {}
    if not ens.exists():
        return counts
    for d in sorted(ens.iterdir()):
        p = d / "summary.json"
        if d.is_dir() and p.is_file():
            key = identity(json.loads(p.read_text()))
            counts[key] = counts.get(key, 0) + 1
    return counts
