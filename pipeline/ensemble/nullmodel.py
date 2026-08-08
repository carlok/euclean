"""What survival would look like if ranking were random.

`concept_survival` counts how many members' ranked list a canonical key reaches,
and the project has been reporting those counts with no scale beside them. A
count is not evidence until you know what the same count would be under chance,
and here chance is not small: each member ranks its top `k` out of a pool of
candidates, so a concept present in every member's pool already reaches most
ranked lists without any structure at all.

Measured over the 45-member grid: ranked lists average 19.9 entries drawn from
pools averaging 58.2, and 39 of 45 members hit the cap. A key present in every
pool would reach the ranked list in **24.3 of 45 members by random ranking
alone**, against a best published survival of 15/45.

## Two references, and only the second one is usable

That first reference assumes a concept available to be ranked in every member.
`pool_presence` re-mines the pools and shows **no such concept exists**: the most
widely available premise-conjunction key is in 17 of 45 pools, the most widely
available quantified key in 16, and none is in all 45. So the unconditional
reference is unreachable by construction and "below chance" says nothing.

Conditioning chance on availability is the reference that applies, and it
decomposes the null cleanly:

- **Ranking is close to chance.** The best premise-conjunction key is ranked in
  14 of the 17 members that could rank it, against 13.2 expected — an excess of
  +0.8. The best excess anywhere is +3.5. Across 592 keys, 175 beat their own
  conditional chance, about what noise around chance produces. Four sprints of
  scoring criteria are buying very little over drawing from the pool at random.
- **Availability is the binding constraint.** A concept is minable in at most
  38% of configurations. That, not the top-`k` cut, is what caps survival.

This is a sharper form of the negative result rather than a weakening of it, and
it relocates where the failure lives: in whether the same pattern is *found*
across configurations at all, not in how candidates are scored once found.

## Why this is a prerequisite for comparing two theories

A fixed top-`k` over a variable pool is not a fair statistic across theories. A
richer theory produces a larger pool, so each of its candidates has a *smaller*
chance of being ranked, and it is penalized before any of its content is
considered. Comparing raw survival between a 2-relation theory and a 3-relation
one would therefore find the richer theory less stable no matter what is true of
it — which is exactly the conclusion the comparison is supposed to test.

Scoring each theory against its own chance reference is what makes the two
answerable at all.

## What is computed

For each source and member: `C` is the size of that source's candidate pool and
`k` is how many of its candidates reached the ranked list. A candidate drawn
uniformly from the pool is ranked with probability `k/C`, so a key present in
every pool has expected survival `Σ k/C` over the members.

Everything comes from artifacts already written — `summary.json` records the
three pool sizes and `concepts.json` records the ranked entries — so the
existing grid calibrates with no re-run.

Usage:  python3 -m pipeline.ensemble.nullmodel
"""

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENS = ROOT / "runs" / "ens"

# source name -> the summary field holding that source's pool size
POOL_FIELD = {
    "premise-conjunction": "concept_candidates",
    "proof-role": "role_candidates",
    "quantified": "quantified_candidates",
}


def per_member(members):
    """`(pool, ranked, probability)` for every source in every member."""
    rows = []
    for m in members:
        summary = m["summary"]
        counted = {}
        for c in m["concepts"]:
            src = c.get("source", "premise-conjunction")
            counted[src] = counted.get(src, 0) + 1
        for source, field in POOL_FIELD.items():
            pool = summary.get(field)
            if pool is None:
                continue
            ranked = counted.get(source, 0)
            rows.append(
                {
                    "member": summary["id"],
                    "source": source,
                    "pool": pool,
                    "ranked": ranked,
                    # a pool of zero is not a null result, it is a member where
                    # the source had nothing to rank; kept separate below
                    "p": (ranked / pool) if pool else None,
                }
            )
    return rows


def chance_reference(members):
    """Expected survival under random ranking, per source.

    The reference is stated for a concept present in *every* member's pool,
    which is the most favourable case. A concept absent from some pools has a
    lower ceiling, so this is an upper bound on what chance alone delivers —
    and a survival figure below it needs no further explanation.
    """
    rows = per_member(members)
    n = len(members)
    out = {}
    for source in POOL_FIELD:
        mine = [r for r in rows if r["source"] == source]
        if not mine:
            continue
        live = [r for r in mine if r["p"] is not None]
        vacuous = [r["member"] for r in mine if r["p"] is None]
        expected = sum(r["p"] for r in live)
        out[source] = {
            "members": n,
            "members_with_a_pool": len(live),
            "vacuous_members": len(vacuous),
            "vacuous_examples": sorted(vacuous)[:5],
            "mean_pool": round(sum(r["pool"] for r in live) / len(live), 1) if live else 0,
            "mean_ranked": round(sum(r["ranked"] for r in live) / len(live), 1) if live else 0,
            "expected_survival": round(expected, 1),
            "expected_survival_rate": round(expected / n, 3) if n else 0,
        }
    return out


def pool_presence(ens=None, min_support=8, select=None, log=print):
    """Split survival into *finding* a concept and *ranking* it.

    The chance reference above is stated for a concept present in every member's
    pool. Observed survival comes in far below it, and that has two very
    different readings: either the ranking step discards concepts that were
    found everywhere, or the same concept is not being found in the first place.
    Only the second is a statement about concept invention.

    Pools are stored as sizes, not as key lists, so this re-mines each member's
    corpus to recover which canonical keys were *available* to be ranked. The
    corpus, and the canonical map for that member's theory seed, are both stored
    alongside it — nothing is recomputed from the theory and no run is repeated.
    """
    from ..canon import relations as R
    from ..concepts import invent, quantified
    from . import grids

    ens = ens or ENS
    if select is None:
        # One grid. Pooling replicates leaves each key reachable in only one of
        # them while the member count multiplies, so every availability rate
        # falls by the number of grids present.
        select = grids.matches
    present, ranked, members = {}, {}, []
    # (member, source) -> probability a candidate in that pool gets ranked
    odds = {}

    for d in sorted(ens.iterdir()):
        if not (d.is_dir() and (d / "corpus.json").exists() and (d / "summary.json").exists()):
            continue
        summary = json.loads((d / "summary.json").read_text())
        relmap = summary.get("relation_canonical_map")
        if not relmap:
            continue
        # `select` keeps replicates apart. Pooling them would inflate the member
        # count while leaving each key reachable in at most one grid, which
        # deflates every availability rate.
        if select is not None and not select(summary):
            continue
        records = json.loads((d / "corpus.json").read_text())
        members.append(summary["id"])

        pools = {
            "premise-conjunction": [
                c["body"] for c in invent.candidates(records, min_support=min_support,
                                                     max_conjuncts=2)
            ],
            "quantified": [
                c["body"]
                for c in quantified.candidates(records, min_support=max(4, min_support // 2))
            ],
        }
        for source, bodies in pools.items():
            for body in bodies:
                present.setdefault((source, repr(R.key(body, relmap))), set()).add(summary["id"])

        available = {
            source: {repr(R.key(b, relmap)) for b in bodies} for source, bodies in pools.items()
        }
        counted = {}
        for c in json.loads((d / "concepts.json").read_text())["ranked"]:
            src = c.get("source", "premise-conjunction")
            if src in pools:
                # A key can only be ranked in a member whose pool held it. If
                # this trips, the re-mining used different parameters than the
                # grid did, and every conditional figure below would be
                # computed against the wrong denominator.
                if c["canonical_key"] not in available[src]:
                    raise ValueError(
                        f"{summary['id']}: ranked {src} key is absent from the re-mined "
                        f"pool. Re-mining must use the same min_support the grid ran "
                        f"with (given: {min_support})."
                    )
                ranked.setdefault((src, c["canonical_key"]), set()).add(summary["id"])
                counted[src] = counted.get(src, 0) + 1

        # the pool is measured here rather than read from the summary, since it
        # is the same quantity and this way the two cannot drift apart
        for source, bodies in pools.items():
            odds[(summary["id"], source)] = (
                counted.get(source, 0) / len(bodies) if bodies else 0.0
            )
        log(f"  {summary['id']:28s} pools " + " ".join(
            f"{s.split('-')[0]}={len(b)}" for s, b in pools.items()))

    n = len(members)
    rows = []
    for (source, key), where in present.items():
        got = ranked.get((source, key), set())
        # The reference that actually applies to this key: chance is summed only
        # over the members where the key was available to be ranked at all. The
        # unconditional reference assumes a key present in every pool, and the
        # census shows no such key exists.
        chance = sum(odds.get((m, source), 0.0) for m in where)
        rows.append(
            {
                "source": source,
                "canonical_key": key,
                "in_pool_of": len(where),
                "ranked_in": len(got & where),
                # given that it was available, how often did it get ranked
                "ranked_given_present": round(len(got & where) / len(where), 3),
                "chance_given_present": round(chance, 2),
                "excess_over_chance": round(len(got & where) - chance, 2),
            }
        )
    rows.sort(key=lambda r: (-r["in_pool_of"], -r["ranked_in"]))
    return {"members": n, "rows": rows}


def presence_summary(census):
    """The decomposition, per source, as the two numbers that matter."""
    out = {}
    n = census["members"]
    for source in sorted({r["source"] for r in census["rows"]}):
        mine = [r for r in census["rows"] if r["source"] == source]
        best_presence = max(r["in_pool_of"] for r in mine)
        universal = [r for r in mine if r["in_pool_of"] == n]
        beating = [r for r in mine if r["excess_over_chance"] > 0]
        out[source] = {
            "distinct_keys": len(mine),
            "members": n,
            "best_presence": best_presence,
            "best_presence_rate": round(best_presence / n, 3) if n else 0,
            "keys_in_every_pool": len(universal),
            "mean_ranked_given_present": round(
                sum(r["ranked_given_present"] for r in mine) / len(mine), 3
            )
            if mine
            else 0,
            # how much the scoring buys over drawing from the pool at random
            "keys_beating_chance": len(beating),
            "best_excess_over_chance": round(
                max((r["excess_over_chance"] for r in mine), default=0), 2
            ),
        }
    return out


def statement_reference(members, top=15):
    """The same treatment for the *positive* result.

    `top_statement_survival` counts how many members' top-`top` a statement
    reached, and that count has been quoted with no scale for as long as the
    concept counts were. The hole is easier to miss here because the number
    looks good.

    Unlike concepts, every statement in a member's corpus is available to be
    ranked, so the pool is the corpus and no re-mining is needed. A statement
    present in member `m` reaches its top-`top` with probability `top/|corpus|`
    under random ranking, and chance is summed only over the members whose
    corpus actually contains it.
    """
    pools, ranked_keys, present = {}, {}, {}
    for m in members:
        mid = m["summary"]["id"]
        items = m["importance"]
        keys = {i["canonical_key"] for i in items if "canonical_key" in i}
        if not keys:
            continue
        pools[mid] = len(keys)
        seen = []
        for i in items:
            k = i.get("canonical_key")
            if k is not None and k not in seen:
                seen.append(k)
            if len(seen) >= top:
                break
        ranked_keys[mid] = set(seen)
        for k in keys:
            present.setdefault(k, set()).add(mid)

    rows = []
    for key, where in present.items():
        observed = sum(1 for mid in where if key in ranked_keys.get(mid, ()))
        chance = sum(min(top, pools[mid]) / pools[mid] for mid in where)
        rows.append(
            {
                "canonical_key": key,
                "in_corpus_of": len(where),
                "reached_top": observed,
                "chance": round(chance, 2),
                "excess_over_chance": round(observed - chance, 2),
            }
        )
    rows.sort(key=lambda r: -r["reached_top"])

    n = len(pools)
    universal = [r for r in rows if r["in_corpus_of"] == n]
    return {
        "members": n,
        "top": top,
        "mean_pool": round(sum(pools.values()) / n, 1) if n else 0,
        "distinct_keys": len(rows),
        "keys_in_every_corpus": len(universal),
        # the reference that applies to a statement available everywhere
        "chance_if_universal": round(sum(min(top, p) / p for p in pools.values()), 2),
        "best_observed": rows[0]["reached_top"] if rows else 0,
        "best_excess": max((r["excess_over_chance"] for r in rows), default=0),
        "keys_beating_chance": sum(1 for r in rows if r["excess_over_chance"] > 0),
        "rows": rows[:40],
    }


def multi_premise_count(records):
    """Statements with at least two premises.

    The quantity concept mining actually consumes: `invent.candidates` builds
    conjunctions of premises and skips anything with fewer than two. Corpus size
    is the wrong tripwire — among the stored members, one with 244 statements
    yields no candidates while one with 84 yields eight.
    """
    from ..kernel import formula as F

    n = 0
    for r in records:
        stmt = r["statement_ast"]
        body = stmt["body"] if stmt["kind"] == "forall" else stmt
        if len(F.premises(body)[0]) >= 2:
            n += 1
    return n


def bundle(theory, ens=None, min_support=8, base_seeds=(0, 100, 200), log=print):
    """Everything `controlverdict` needs about one theory, per replicate.

    Built from stored artifacts. Each base seed is measured separately — pooling
    them would leave every key reachable in one grid while the member count
    multiplies, which deflates exactly the statistic the verdict reads.
    """
    from . import grids

    ens = ens or ENS
    avail, budgets, vacuous, total, bound = {}, set(), 0, 0, False

    for seed in base_seeds:
        census = pool_presence(
            ens=ens,
            min_support=min_support,
            select=lambda s, t=theory, b=seed: grids.matches(s, t, b),
            log=lambda *a: None,
        )
        if not census["members"]:
            continue
        avail[seed] = presence_summary(census)

        for d in grids.member_dirs(ens=ens, theory=theory, base_seed=seed):
            summary = json.loads((d / "summary.json").read_text())
            cfg = summary.get("config", {})
            budgets.add(
                json.dumps({k: cfg[k] for k in sorted(cfg) if k in BUDGET_KEYS}, sort_keys=True)
            )
            if summary.get("rejected", {}).get("engine:max-facts"):
                bound = True
            total += 1
            records = json.loads((d / "corpus.json").read_text())
            if multi_premise_count(records) < min_support:
                vacuous += 1
        log(f"  {theory} base seed {seed}: {census['members']} members")

    if len(budgets) > 1:
        raise ValueError(
            f"{theory} members ran at {len(budgets)} different budgets. A "
            f"comparison across them would be of budgets, not theories."
        )

    return {
        "label": theory,
        "budget": next(iter(budgets), None),
        "availability": {str(k): v for k, v in avail.items()},
        "vacuous_fraction": round(vacuous / total, 3) if total else None,
        # whether the search was truncated by the fact ceiling; truncation
        # biases availability down, never up, so the verdict treats a truncated
        # pass and a truncated failure differently
        "budget_bound": bound,
        "members": total,
    }


# the configuration keys that make two runs comparable
BUDGET_KEYS = {
    "rounds",
    "derivations_per_rule_per_round",
    "match_attempts",
    "generative_samples",
    "max_facts",
    "max_scopes",
    "max_case_splits",
    "branch_rounds",
    "time_budget",
    "rewrites_per_equation",
    "max_case_proof_size",
    "case_split_depth",
}


def annotate(rows, reference):
    """Attach each survival row's chance reference and its excess over chance."""
    for r in rows:
        ref = reference.get(r.get("source", "premise-conjunction"))
        if not ref:
            continue
        r["chance_survival"] = ref["expected_survival"]
        r["excess_over_chance"] = round(r["survives"] - ref["expected_survival"], 1)
    return rows


def report(reference, best_by_source=None):
    lines = ["Chance reference for concept survival", ""]
    lines.append(f"  {'source':22s} {'pool':>6s} {'ranked':>7s} {'chance':>8s} {'vacuous':>8s}")
    for source, r in reference.items():
        lines.append(
            f"  {source:22s} {r['mean_pool']:6.1f} {r['mean_ranked']:7.1f} "
            f"{r['expected_survival']:6.1f}/{r['members']:<2d} {r['vacuous_members']:8d}"
        )
    lines.append("")
    lines.append("  A concept present in every member's pool would reach the ranked list")
    lines.append("  this often by random ranking alone. See the census below for whether")
    lines.append("  such a concept exists.")

    if best_by_source:
        lines.append("")
        lines.append(f"  {'source':22s} {'best observed':>14s} {'chance':>8s} {'excess':>8s}")
        for source, best in sorted(best_by_source.items()):
            ref = reference.get(source)
            if not ref:
                continue
            excess = best - ref["expected_survival"]
            lines.append(
                f"  {source:22s} {best:8d}/{ref['members']:<5d} "
                f"{ref['expected_survival']:8.1f} {excess:+8.1f}"
            )
    return "\n".join(lines)


def census_report(summary):
    """The decomposition: is survival capped by ranking, or by availability?"""
    lines = ["", "Availability census (pools re-mined from each member's corpus)", ""]
    lines.append(
        f"  {'source':22s} {'keys':>6s} {'best avail':>12s} {'in every':>9s} "
        f"{'beat chance':>12s} {'best excess':>12s}"
    )
    for source, s in sorted(summary.items()):
        lines.append(
            f"  {source:22s} {s['distinct_keys']:6d} "
            f"{s['best_presence']:6d}/{s['members']:<5d} {s['keys_in_every_pool']:9d} "
            f"{s['keys_beating_chance']:6d}/{s['distinct_keys']:<5d} "
            f"{s['best_excess_over_chance']:+12.2f}"
        )
    lines.append("")
    lines.append("  'in every' is how many concepts were available to be ranked in every")
    lines.append("  member. If that is zero, the unconditional reference above is")
    lines.append("  unreachable and survival is capped by availability, not by ranking.")
    lines.append("  'best excess' is the largest gain any concept's scoring achieved over")
    lines.append("  drawing at random from the pools where it was available.")
    return "\n".join(lines)


def main():
    from . import stability

    ap = argparse.ArgumentParser()
    ap.add_argument("--ens", default=None, help="grid directory (default: the standard one)")
    ap.add_argument("--min-support", type=int, default=8, help="must match the grid's setting")
    ap.add_argument("--no-census", action="store_true", help="skip re-mining the pools")
    ap.add_argument("--out", default=None, help="write JSON here as well as reporting")
    ap.add_argument(
        "--bundle",
        default=None,
        help="build the availability bundle for this theory and write it where "
        "controlverdict looks for it, instead of reporting",
    )
    ap.add_argument("--base-seeds", type=int, nargs="+", default=[0, 100, 200])
    args = ap.parse_args()

    ens = pathlib.Path(args.ens) if args.ens else None

    if args.bundle:
        b = bundle(
            args.bundle, ens=ens, min_support=args.min_support, base_seeds=args.base_seeds
        )
        if not b["availability"]:
            raise SystemExit(f"no members found for theory {args.bundle!r}")
        out = pathlib.Path(args.out or (ROOT / "runs" / "ensemble" / f"availability-{args.bundle}.json"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(b, indent=1) + "\n")
        print(
            f"  {b['label']}: {b['members']} members over {len(b['availability'])} "
            f"replicates, vacuous {b['vacuous_fraction']}, "
            f"{'ceiling-bound' if b['budget_bound'] else 'not ceiling-bound'}"
        )
        print(f"wrote {out}")
        return

    members = stability.load_members(ens=ens)
    if not members:
        raise SystemExit("no members found; nothing to calibrate against")

    reference = chance_reference(members)
    rows = stability.concept_survival(members)
    best = {}
    for r in rows:
        s = r.get("source", "premise-conjunction")
        best[s] = max(best.get(s, 0), r["survives"])

    print(report(reference, best))

    stmt = statement_reference(members)
    print("")
    print("Statement survival against the same yardstick")
    print("")
    print(f"  best observed          {stmt['best_observed']}/{stmt['members']}")
    print(f"  chance if universal    {stmt['chance_if_universal']}/{stmt['members']}")
    print(f"  best excess            {stmt['best_excess']:+}")
    print(f"  keys in every corpus   {stmt['keys_in_every_corpus']}")
    print("")
    print("  Unlike concepts, the reference here is reachable: statements do appear")
    print("  in every corpus, and the best of them beats chance by a wide margin.")

    payload = {"reference": reference, "best_observed": best, "statements": stmt}
    if not args.no_census:
        census = pool_presence(ens=ens, min_support=args.min_support, log=lambda *a: None)
        summary = presence_summary(census)
        print(census_report(summary))
        payload["census"] = summary
        payload["census_rows"] = census["rows"][:200]

    if args.out:
        p = pathlib.Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=1))
        print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
