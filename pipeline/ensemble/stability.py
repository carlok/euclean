"""Which findings survive the grid, and which were echoes of one setup.

This is the question sprint 1 could not answer. It produced a ranked list of
invented concepts, and a single control run then showed most of them were
artifacts of the assumed disequalities. One control tells you that a result is
fragile; it does not tell you which results are not.

Everything is compared through the arity-canonical relation names, so members
built on re-permuted identifiers are directly comparable without anyone
consulting what the identifiers mean.

A note on reading the output: high survival across the grid is evidence a
structure is intrinsic, not proof. A structure could survive because every
member shares some other bias. What survival does establish is that the finding
does not depend on the axes actually varied, and those axes are recorded
alongside it.

Usage:  python3 -m pipeline.ensemble.stability
"""

import argparse
import json
import pathlib
from collections import Counter, defaultdict

from scipy.stats import spearmanr

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENS = ROOT / "runs" / "ens"


def load_members(ens=None):
    """Read whatever completed.

    Members are discovered by walking the directories rather than by trusting an
    index file. An index is only written when a whole theory seed finishes, so
    keying off it would silently discard every member of an interrupted sweep —
    and an interrupted sweep is the normal case when one configuration is slow.
    """
    members = []
    for d in sorted((ens or ENS).iterdir()):
        if d.is_dir() and (d / "summary.json").exists() and (d / "concepts.json").exists():
            summary = json.loads((d / "summary.json").read_text())
            members.append(
                {
                    "summary": summary,
                    "concepts": json.loads((d / "concepts.json").read_text())["ranked"],
                    "importance": json.loads((d / "importance.json").read_text()),
                    "clusters": json.loads((d / "clusters.json").read_text()),
                }
            )
    return members


def concept_survival(members):
    """How often each canonical concept body reaches a member's top list."""
    seen = defaultdict(list)
    for m in members:
        for c in m["concepts"]:
            seen[c["canonical_key"]].append(
                {
                    "member": m["summary"]["id"],
                    "distinct": str(m["summary"]["config"]["assume_distinct"]),
                    "layout": m["summary"]["config"]["atom_layout"],
                    "params": m["summary"]["config"]["params"],
                    "covers": c["scores"].get("theorems_covered", 0),
                    "dl": c["scores"].get("description_length_reduction"),
                    "source": c.get("source", "premise-conjunction"),
                    "render": c,
                }
            )

    n = len(members)
    rows = []
    for key, hits in seen.items():
        example = hits[0]["render"]
        distinct_modes = {h["distinct"] for h in hits}
        rows.append(
            {
                "canonical_key": key,
                "survives": len(hits),
                "of": n,
                "survival_rate": round(len(hits) / n, 3),
                "params_seen": sorted({h["params"] for h in hits}),
                "distinct_modes_seen": sorted(distinct_modes),
                "layouts_seen": sorted({h["layout"] for h in hits}),
                # a concept that only ever shows up when disequalities are
                # assumed is telling you about the assumption, not the theory
                "requires_assumed_distinctness": distinct_modes.isdisjoint({"False"}),
                "median_coverage": sorted(h["covers"] for h in hits)[len(hits) // 2],
                "source": hits[0]["source"],
                "arity": example["scores"].get("arity"),
                "params": example["params"],
                "body": example["body"],
            }
        )
    rows.sort(key=lambda r: (-r["survives"], -r["median_coverage"]))
    return rows


def survival_by_source(rows, members):
    """The sprint's central comparison: do role concepts outlast syntactic ones?

    Reported as a distribution rather than a single rate. If one source has ten
    candidates surviving once each and the other has one surviving ten times,
    their means coincide and their meanings do not.
    """
    from . import nullmodel

    n = len(members)
    # Every survival figure is reported beside what random ranking would give.
    # A count is not evidence until you know the count chance produces, and here
    # chance is large: members rank a fixed top-k out of a variable pool.
    reference = nullmodel.chance_reference(members)

    out = {}
    for source in sorted({r["source"] for r in rows}):
        group = [r for r in rows if r["source"] == source]
        rates = sorted((r["survives"] for r in group), reverse=True)
        ref = reference.get(source, {})
        chance = ref.get("expected_survival")
        out[source] = {
            "candidates": len(group),
            "best_survival": f"{rates[0]}/{n}" if rates else None,
            "best_rate": round(rates[0] / n, 3) if rates else None,
            "mean_survival": round(sum(rates) / len(rates), 2) if rates else None,
            "surviving_over_half": sum(1 for x in rates if x > n / 2),
            "appearing_once_only": sum(1 for x in rates if x == 1),
            # the scale. See nullmodel: this reference assumes a concept
            # available in every member's pool, which the census shows never
            # happens, so it is a ceiling rather than a like-for-like null.
            "chance_survival": chance,
            "best_excess_over_chance": (
                round(rates[0] - chance, 1) if rates and chance is not None else None
            ),
            "vacuous_members": ref.get("vacuous_members"),
        }
    return out


def importance_stability(members, min_members=3, top=200):
    """Rank correlation of the structural importance ordering across members.

    Only statements that several members actually derived can be compared, so
    the correlation is computed pairwise over each pair's shared statements.
    """
    ranks = []
    for m in members:
        order = {}
        for pos, item in enumerate(m["importance"][:top]):
            order.setdefault(item["canonical_key"], pos)
        ranks.append((m["summary"]["id"], order))

    pairs = []
    for i in range(len(ranks)):
        for j in range(i + 1, len(ranks)):
            a, b = ranks[i][1], ranks[j][1]
            shared = sorted(set(a) & set(b))
            if len(shared) < min_members * 2:
                continue
            rho, p = spearmanr([a[k] for k in shared], [b[k] for k in shared])
            pairs.append(
                {
                    "a": ranks[i][0],
                    "b": ranks[j][0],
                    "shared": len(shared),
                    "spearman": round(float(rho), 4),
                    "p": float(p),
                }
            )

    vals = [p["spearman"] for p in pairs]
    return {
        "pairs_compared": len(pairs),
        "mean_spearman": round(sum(vals) / len(vals), 4) if vals else None,
        "min_spearman": round(min(vals), 4) if vals else None,
        "max_spearman": round(max(vals), 4) if vals else None,
        "detail": sorted(pairs, key=lambda p: -p["spearman"])[:20],
    }


def top_statement_survival(members, top=15):
    """Which statements repeatedly reach the top of the importance ranking."""
    hits = Counter()
    example = {}
    for m in members:
        seen = set()
        for item in m["importance"][:top]:
            k = item["canonical_key"]
            if k in seen:
                continue
            seen.add(k)
            hits[k] += 1
            example.setdefault(k, item.get("canonical_statement", item["statement"]))
    n = len(members)
    return [
        {
            "canonical_key": k,
            "survives": c,
            "of": n,
            "survival_rate": round(c / n, 3),
            "statement": example[k],
        }
        for k, c in hits.most_common(40)
    ]


def corpus_spread(members):
    keys = (
        "kept",
        "existential_free",
        "disjunctive",
        "case_analysis_derived",
        "concept_candidates",
    )
    out = {}
    for k in keys:
        vals = [m["summary"].get(k, 0) for m in members]
        out[k] = {"min": min(vals), "max": max(vals), "mean": round(sum(vals) / len(vals), 1)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "runs" / "ensemble"))
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    members = load_members()
    if not members:
        raise SystemExit("no ensemble members found under runs/ens/")

    _survival = concept_survival(members)
    report = {
        "members": len(members),
        "member_ids": [m["summary"]["id"] for m in members],
        "theory_seeds": sorted({m["summary"]["theory_seed"] for m in members}),
        "corpus_spread": corpus_spread(members),
        "concept_survival": _survival,
        "survival_by_source": survival_by_source(_survival, members),
        "importance_stability": importance_stability(members),
        "top_statement_survival": top_statement_survival(members, args.top),
    }

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stability.json").write_text(json.dumps(report, indent=1, default=str) + "\n")

    print(f"{report['members']} members, theory seeds {report['theory_seeds']}")
    print(f"corpus spread: {json.dumps(report['corpus_spread'])}")
    imp = report["importance_stability"]
    print(
        f"importance rank correlation across {imp['pairs_compared']} member pairs: "
        f"mean {imp['mean_spearman']}, range [{imp['min_spearman']}, {imp['max_spearman']}]"
    )
    print("\nsurvival by candidate source:")
    for src, s in report["survival_by_source"].items():
        chance = s.get("chance_survival")
        scale = f"  chance {chance}  excess {s['best_excess_over_chance']:+}" if chance else ""
        print(f"  {src:20s} candidates {s['candidates']:4d}  best {s['best_survival']}  "
              f"mean {s['mean_survival']}  >half {s['surviving_over_half']}  "
              f"once-only {s['appearing_once_only']}{scale}")
    print("\nconcepts by survival:")
    for row in report["concept_survival"][:12]:
        flag = " (needs assumed distinctness)" if row["requires_assumed_distinctness"] else ""
        print(
            f"  {row['survives']:2d}/{row['of']:2d}  arity {row['arity']}  "
            f"median coverage {row['median_coverage']:5d}{flag}"
        )
    print("\nstatements repeatedly ranked most important:")
    for row in report["top_statement_survival"][:8]:
        print(f"  {row['survives']:2d}/{row['of']:2d}  {row['statement'][:110]}")
    print(f"\nwrote {out}/stability.json")


if __name__ == "__main__":
    main()
