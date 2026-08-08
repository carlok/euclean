"""What the importance measure is actually measuring.

The ranking is presented as six structural components. Two questions were never
asked of it, and both have uncomfortable answers.

**Are the six components six things?** Four of them turn out to be rank-identical
on the reference corpus, so the measure has three distinct signals with one of
them counted four times.

**Does the normalization preserve order?** It is a percentile rank, so it must.
It does not, because it assigns distinct percentiles to tied values and the
sort is stable — ties are therefore broken by position in the corpus list, which
is derivation order. Most of the corpus is tied on most components, so for those
statements the component is recording where the statement appeared rather than
anything about it.

That second finding is why this module exists as an artifact rather than as a
one-off measurement: the write-up quotes these numbers, and a number quoted from
a shell session is a number that will drift.

Nothing here is a fix. `report/importance.py` is where the fix goes.

Usage:  python3 -m pipeline.report.diagnostics --run main
"""

import argparse
import itertools
import json
import pathlib
from collections import Counter

from scipy.stats import spearmanr

ROOT = pathlib.Path(__file__).resolve().parents[2]

COMPONENTS = (
    "reuse",
    "downstream",
    "generality",
    "symmetry",
    "cluster_coverage",
    "proof_leverage",
)

# Above this, two components are carrying the same ordering and only one of them
# is contributing anything.
REDUNDANT_AT = 0.95
# The window `ensemble/stability.importance_stability` compares per member.
STABILITY_WINDOW = 200


def analyse(ranked):
    composite = [r["importance"] for r in ranked]

    redundancy = []
    for a, b in itertools.combinations(COMPONENTS, 2):
        rho, _ = spearmanr([r["raw"][a] for r in ranked], [r["raw"][b] for r in ranked])
        redundancy.append(
            {"a": a, "b": b, "spearman": round(float(rho), 4), "redundant": bool(abs(rho) >= REDUNDANT_AT)}
        )

    monotone, ties, drives = [], [], []
    for c in COMPONENTS:
        raw = [r["raw"][c] for r in ranked]
        norm = [r["components"][c] for r in ranked]
        rho, _ = spearmanr(raw, norm)
        monotone.append(
            {
                "component": c,
                # a percentile rank must be order-preserving; anything below 1
                # means the normalization is inventing an ordering
                "raw_vs_normalized": round(float(rho), 4),
                "order_preserving": bool(abs(rho) > 0.9999),
            }
        )
        counts = Counter(raw)
        tied = sum(v for v in counts.values() if v > 1)
        ties.append(
            {
                "component": c,
                "distinct_values": len(counts),
                "largest_tie_group": max(counts.values()),
                "in_a_tie": tied,
                "tied_fraction": round(tied / len(raw), 4) if raw else 0,
            }
        )
        rho2, _ = spearmanr(composite, norm)
        drives.append({"component": c, "composite_vs_component": round(float(rho2), 4)})

    # against the baseline the literature says centrality reduces to
    rho_indeg, _ = spearmanr(composite, [r["raw"]["reuse"] for r in ranked])
    by_comp = sorted(ranked, key=lambda r: -r["importance"])
    by_indeg = sorted(ranked, key=lambda r: -r["raw"]["reuse"])

    def overlap(k):
        return len({r["id"] for r in by_comp[:k]} & {r["id"] for r in by_indeg[:k]})

    # how much of the compared window carries a signal at all
    window = by_comp[:STABILITY_WINDOW]
    signal = sum(1 for r in window if r["raw"]["reuse"] > 0)

    return {
        "statements": len(ranked),
        "component_redundancy": redundancy,
        "redundant_pairs": sum(1 for r in redundancy if r["redundant"]),
        "normalization": monotone,
        "components_not_order_preserving": [
            m["component"] for m in monotone if not m["order_preserving"]
        ],
        "ties": ties,
        "composite_drivers": drives,
        "vs_in_degree": {
            "spearman": round(float(rho_indeg), 4),
            "top10_overlap": overlap(10),
            "top50_overlap": overlap(50),
        },
        "stability_window": {
            "window": STABILITY_WINDOW,
            "with_signal": signal,
            "by_tiebreak": STABILITY_WINDOW - signal,
            "signal_fraction": round(signal / STABILITY_WINDOW, 4),
        },
        "top_of_ranking": {
            k: sum(1 for r in by_comp[:k] if r["raw"]["reuse"] > 0) for k in (10, 50, 200)
        },
    }


def report(d):
    L = ["Importance diagnostics", ""]
    L.append(f"  statements: {d['statements']}")
    L.append("")
    L.append(f"  redundant component pairs (|rho| >= {REDUNDANT_AT}): {d['redundant_pairs']}")
    for r in d["component_redundancy"]:
        if r["redundant"]:
            L.append(f"    {r['a']:17s} = {r['b']:17s} {r['spearman']:+.4f}")
    L.append("")
    L.append("  normalization order-preserving?")
    for m in d["normalization"]:
        mark = "ok" if m["order_preserving"] else "REORDERS"
        L.append(f"    {m['component']:17s} raw vs normalized {m['raw_vs_normalized']:+.4f}  {mark}")
    L.append("")
    L.append("  ties (why it reorders):")
    for t in d["ties"]:
        L.append(
            f"    {t['component']:17s} {t['distinct_values']:4d} distinct, "
            f"largest group {t['largest_tie_group']:5d}, {t['tied_fraction']:.0%} tied"
        )
    L.append("")
    v = d["vs_in_degree"]
    L.append(f"  vs plain in-degree: spearman {v['spearman']:+.4f}, "
             f"top-10 overlap {v['top10_overlap']}/10, top-50 {v['top50_overlap']}/50")
    s = d["stability_window"]
    L.append(f"  stability window: {s['with_signal']}/{s['window']} carry a signal; "
             f"{s['by_tiebreak']} are ordered by tie-break")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    args = ap.parse_args()

    run_dir = ROOT / "runs" / args.run
    ranked = json.loads((run_dir / "importance.json").read_text())
    d = analyse(ranked)
    print(report(d))

    out = run_dir / "importance-diagnostics.json"
    out.write_text(json.dumps(d, indent=1) + "\n")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
