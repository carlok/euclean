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

The default is base seed 0 and the theory recorded as the subject in
`runs/ensemble/roles.json`. That is the grid every published number was computed
from, so the default keeps those numbers reproducible — but it is read from disk
rather than hardcoded, because which theory is the subject is a choice and with
several theories it stops being obvious.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENS = ROOT / "runs" / "ens"
ROLES = ROOT / "runs" / "ensemble" / "roles.json"

# The base seed every published figure comes from. Unlike the theory, this is a
# sampling parameter rather than an identity, so a constant is the right shape.
REFERENCE_BASE_SEED = 0

# "every theory" / "every base seed", distinct from None, which means "the
# recorded default". Keeping them separate is not pedantry: when they were the
# same value, asking for the reference grid returned every grid on disk.
ANY = object()


def roles():
    """Which theory plays which part, read from disk rather than hardcoded.

    There used to be a `REFERENCE_THEORY = "incumbent"` constant doing two jobs:
    naming a theory and naming its side of the comparison. With more than two
    theories those come apart — any theory can be subject or control depending
    on the question — and a constant silently picks one.

    Recording the choice in `runs/ensemble/roles.json` keeps the convenience of
    a default while making it a decision someone made and can see.
    """
    if not ROLES.exists():
        raise FileNotFoundError(
            f"no {ROLES.relative_to(ROOT)}. Which theory is the subject is a choice, "
            f"not a constant — write it there, or pass a theory explicitly."
        )
    return json.loads(ROLES.read_text())


def subject():
    """The theory published figures are about."""
    return roles()["subject"]


def identity(summary):
    """`(theory, base_seed)` for a member.

    A member with no `theory` field predates the field, and every such member
    belongs to the subject theory — nothing else existed when they were written.
    """
    return (
        summary.get("theory") or subject(),
        summary.get("base_seed", REFERENCE_BASE_SEED),
    )


def matches(summary, theory=None, base_seed=REFERENCE_BASE_SEED):
    """Does this member belong to the grid being asked for?

    `theory=None` means the recorded subject. Wanting *every* theory is a
    different request and says so with `ANY` — the two were the same value for
    one commit, and the reference grid quietly became 90 members instead of 45,
    which is the exact failure this module exists to prevent.

    `base_seed=ANY` likewise, for tools that partition the members themselves.
    """
    t, b = identity(summary)
    if theory is None:
        theory = subject()
    if theory is not ANY and t != theory:
        return False
    if base_seed is not ANY and base_seed is not None and b != base_seed:
        return False
    return True


def member_dirs(ens=None, theory=None, base_seed=REFERENCE_BASE_SEED):
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


def summaries(ens=None, theory=None, base_seed=REFERENCE_BASE_SEED):
    """The summary dicts of exactly one grid."""
    return [json.loads((d / "summary.json").read_text()) for d in member_dirs(ens, theory, base_seed)]


def total(field, ens=None, theory=None, base_seed=REFERENCE_BASE_SEED):
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
