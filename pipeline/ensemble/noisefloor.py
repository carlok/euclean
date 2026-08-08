"""How much a survival figure moves when nothing about the theory changes.

The project's own rule, applied to the ablation study and to the admissibility
probe, is that a difference is only a difference once it clears a measured
floor. Concept survival has never had one. Every number the grid has produced —
`best 15/45`, `mean 1.66`, `once-only 131` — comes from a single run, and there
has been nothing to say whether re-running would give 15 or 9 or 21.

## Why the existing grid does not already contain replicates

It looks like it does: 45 members, three theory seeds. But a theory seed only
*relabels* the same axioms, which tests permutation invariance and is a
different property. And `ensemble/run.py` called `config.grid(repeats=...)`
without `base_seed`, so all three theory seeds reused chainer seeds 0–14. The
three passes are therefore the same 15 configurations run against the same 15
random contexts, three times over.

`--repeats` does not fix it either: it produces one larger grid rather than a
second grid, so `n` changes and every rate is computed against a new
denominator.

A replicate is the whole grid re-run at a different `base_seed`. This module
compares such grids and reports the spread.

## Reading the output

The floor is the observed range across replicates. Following
`admissibility/verdict.py`, two quantities differ only when their ranges are
disjoint — a mean difference smaller than the spread within either condition is
not a finding. `separated` reports exactly that, so a later comparison between
two theories has a stated bar rather than an eyeballed one.

Usage:  python3 -m pipeline.ensemble.noisefloor --base-seeds 0 100 200
"""

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def by_base_seed(ens=None, seeds=None):
    """Load each replicate grid separately. Never pooled."""
    from . import stability

    grids = {}
    for seed in seeds:
        members = stability.load_members(
            ens=ens, select=lambda s, want=seed: s.get("base_seed", 0) == want
        )
        if members:
            grids[seed] = members
    return grids


def availability(ens=None, seeds=(), min_support=8):
    """Best availability rate per source, per replicate.

    This is the statistic `controlverdict` decides on, so it needs a floor of
    its own — the survival statistics below do not stand in for it. Pools are
    re-mined per replicate, never pooled across them.
    """
    from . import nullmodel

    out = {}
    for seed in seeds:
        census = nullmodel.pool_presence(
            ens=ens,
            min_support=min_support,
            select=lambda s, want=seed: s.get("base_seed", 0) == want,
            log=lambda *a: None,
        )
        if census["members"]:
            out[seed] = nullmodel.presence_summary(census)
    return out


def spread(grids, avail=None):
    """Per source, the range of each survival statistic across replicates."""
    from . import stability

    per_seed = {}
    for seed, members in grids.items():
        rows = stability.concept_survival(members)
        per_seed[seed] = stability.survival_by_source(rows, members)

    # availability is carried in the same shape so one table covers both
    if avail:
        for seed, summary in avail.items():
            if seed not in per_seed:
                continue
            for source, s in summary.items():
                per_seed[seed].setdefault(source, {})["best_availability_rate"] = s[
                    "best_presence_rate"
                ]

    sources = sorted({s for v in per_seed.values() for s in v})
    fields = (
        "best_availability_rate",
        "best_rate",
        "mean_survival",
        "surviving_over_half",
        "appearing_once_only",
    )

    out = {}
    for source in sources:
        stats = {}
        for field in fields:
            vals = [
                v[source][field]
                for v in per_seed.values()
                if source in v and v[source].get(field) is not None
            ]
            if not vals:
                continue
            stats[field] = {
                "values": vals,
                "min": min(vals),
                "max": max(vals),
                "range": round(max(vals) - min(vals), 4),
            }
        out[source] = stats
    return {"replicates": sorted(grids), "members": {k: len(v) for k, v in grids.items()},
            "by_source": out}


def separated(a, b):
    """Do two measured ranges fail to overlap?

    The same rule `admissibility/verdict.wins` applies: overlapping ranges are
    not a difference, however far apart their means sit.
    """
    return a["min"] > b["max"] or b["min"] > a["max"]


def report(result):
    lines = [
        f"Noise floor over {len(result['replicates'])} replicate grids "
        f"(base seeds {result['replicates']})",
        "",
    ]
    for seed, n in sorted(result["members"].items()):
        lines.append(f"  base seed {seed:<5d} {n} members")
    lines.append("")

    if len(result["replicates"]) < 2:
        lines.append("  Only one grid present, so there is no floor to report. Run the")
        lines.append("  grid again at a different --base-seed before quoting any")
        lines.append("  survival figure as a difference.")
        return "\n".join(lines)

    lines.append(f"  {'source':22s} {'statistic':22s} {'min':>8s} {'max':>8s} {'range':>8s}")
    for source, stats in result["by_source"].items():
        for field, s in stats.items():
            lines.append(
                f"  {source:22s} {field:22s} {s['min']:8.3f} {s['max']:8.3f} {s['range']:8.3f}"
            )
    lines.append("")
    lines.append("  A difference smaller than the range above is not a difference. Two")
    lines.append("  conditions are separated only when their ranges do not overlap.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ens", default=None)
    ap.add_argument("--base-seeds", type=int, nargs="+", default=[0, 100, 200])
    ap.add_argument("--out", default=str(ROOT / "runs" / "ensemble" / "noisefloor.json"))
    args = ap.parse_args()

    ens = pathlib.Path(args.ens) if args.ens else None
    grids = by_base_seed(ens=ens, seeds=args.base_seeds)
    if not grids:
        raise SystemExit("no grids found for those base seeds")

    result = spread(grids, avail=availability(ens=ens, seeds=sorted(grids)))
    print(report(result))

    p = pathlib.Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=1) + "\n")
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
