"""Every number the write-up quotes, as LaTeX macros.

The prose is written by hand. The arithmetic is not, and this module is the
reason. `docs/EXECUTIVE_SUMMARY.md` was hand-typed once and its figures drifted
from the runs they described twice — six at once, then eleven — because the
narrative was updated after a re-run and the numbers were not. A `.tex` file is
a worse offender than a markdown one: it looks authoritative, and nobody diffs
it against `runs/`.

So the document contains no digits. It says `\\euBestSurvival` and this module
decides what that is.

Anything not yet measured becomes `\\euPending`, which renders visibly in the
output rather than silently as zero or as a stale value from last sprint. A
draft with `[pending]` in it is honest; a draft with a number that used to be
true is not.

Usage:  python3 -m pipeline.report.texmacros
"""

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tex" / "generated.tex"

PENDING = object()


def _load(path, default=None):
    p = pathlib.Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except (ValueError, OSError):
        return default


def _dig(obj, *keys, default=PENDING):
    """Walk nested dicts/lists, returning PENDING rather than raising."""
    for k in keys:
        if obj is None:
            return default
        try:
            obj = obj[k]
        except (KeyError, IndexError, TypeError):
            return default
    return default if obj is None else obj


def collect(run="main"):
    """macro name -> value. PENDING for anything not measured yet."""
    ens = ROOT / "runs" / "ensemble"
    corpus = _load(ROOT / "runs" / run / "corpus.json", [])
    stability = _load(ens / "stability.json", {})
    nullmodel = _load(ens / "nullmodel.json", {})
    floor = _load(ens / "noisefloor.json", {})
    verdict = _load(ens / "controlverdict.json", {})
    # Bundles are named by theory code, and which code plays which role is
    # recorded rather than assumed. Hardcoding either name here is what made
    # these five macros silently go pending the moment theories were renamed.
    roles = _load(ens / "roles.json", {})
    avail_inc = _load(ens / f"availability-{roles.get('subject')}.json", {})
    avail_cand = _load(ens / f"availability-{roles.get('control')}.json", {})
    diag = _load(ROOT / "runs" / run / "importance-diagnostics.json", {})
    minimisation = _load(ROOT / "runs" / run / "minimisation.json", {})
    sufficiency = _load(ROOT / "runs" / run / "sufficiency.json", {})
    footprints = _load(ROOT / "runs" / run / "footprints.json", {})

    by_src = stability.get("survival_by_source", {})
    imp = stability.get("importance_stability", {})
    spread = stability.get("corpus_spread", {})
    census = nullmodel.get("census", {})
    ref = nullmodel.get("reference", {})

    m = {
        # the corpus
        "euCorpusSize": len(corpus) if corpus else PENDING,
        "euGridMembers": stability.get("members", PENDING),
        "euGridTheory": stability.get("theory", PENDING),
        "euCorpusMin": _dig(spread, "kept", "min"),
        "euCorpusMax": _dig(spread, "kept", "max"),
        # the positive result: top-statement survival is the claim, the rank
        # correlation is the compromised one
        "euTopStatementSurvival": _dig(stability, "top_statement_survival", 0, "survives"),
        "euTopStatementOf": _dig(stability, "top_statement_survival", 0, "of"),
        # the positive result, finally against the same yardstick as the negative
        "euStatementChance": _dig(nullmodel, "statements", "chance_if_universal"),
        "euStatementExcess": _dig(nullmodel, "statements", "best_excess"),
        "euStatementsInEveryCorpus": _dig(nullmodel, "statements", "keys_in_every_corpus"),
        "euStatementPool": _dig(nullmodel, "statements", "mean_pool"),
        # what the importance measure turns out to be
        "euRedundantPairs": diag.get("redundant_pairs", PENDING),
        "euNotOrderPreserving": (
            len(diag["components_not_order_preserving"])
            if diag.get("components_not_order_preserving") is not None
            else PENDING
        ),
        "euVsInDegree": _dig(diag, "vs_in_degree", "spearman"),
        "euTopTenOverlap": _dig(diag, "vs_in_degree", "top10_overlap"),
        "euStabilityWindow": _dig(diag, "stability_window", "window"),
        "euStabilitySignal": _dig(diag, "stability_window", "with_signal"),
        "euStabilityTiebreak": _dig(diag, "stability_window", "by_tiebreak"),
        "euLargestTieGroup": (
            max((t["largest_tie_group"] for t in diag["ties"]), default=PENDING)
            if diag.get("ties")
            else PENDING
        ),
        "euTopTenWithSignal": _dig(diag, "top_of_ranking", "10"),
        "euImportanceRho": imp.get("mean_spearman", PENDING),
        "euImportanceRhoMin": imp.get("min_spearman", PENDING),
        "euImportanceRhoMax": imp.get("max_spearman", PENDING),
        "euMemberPairs": imp.get("pairs_compared", PENDING),
        # the negative result, and its scale
        "euBestSurvivalPremise": _dig(by_src, "premise-conjunction", "best_survival"),
        "euBestSurvivalQuant": _dig(by_src, "quantified", "best_survival"),
        "euBestSurvivalRole": _dig(by_src, "proof-role", "best_survival"),
        "euChancePremise": _dig(by_src, "premise-conjunction", "chance_survival"),
        "euChanceQuant": _dig(by_src, "quantified", "chance_survival"),
        "euChanceRole": _dig(by_src, "proof-role", "chance_survival"),
        "euSurvivingOverHalf": _dig(by_src, "premise-conjunction", "surviving_over_half"),
        # the decomposition: availability versus ranking
        "euBestAvailPremise": _dig(census, "premise-conjunction", "best_presence"),
        "euBestAvailQuant": _dig(census, "quantified", "best_presence"),
        "euKeysInEveryPool": _dig(census, "premise-conjunction", "keys_in_every_pool"),
        "euDistinctKeysPremise": _dig(census, "premise-conjunction", "distinct_keys"),
        "euBeatingChancePremise": _dig(census, "premise-conjunction", "keys_beating_chance"),
        "euBestExcessPremise": _dig(census, "premise-conjunction", "best_excess_over_chance"),
        "euMeanPoolPremise": _dig(ref, "premise-conjunction", "mean_pool"),
        # the noise floor
        "euReplicates": len(floor.get("replicates", [])) or PENDING,
        "euFloorBestRate": _dig(
            floor, "by_source", "premise-conjunction", "best_rate", "range"
        ),
        "euFloorAvail": _dig(
            floor, "by_source", "premise-conjunction", "best_availability_rate", "range"
        ),
        "euFloorOnceOnlyRole": _dig(
            floor, "by_source", "proof-role", "appearing_once_only", "range"
        ),
        # the control
        "euIncumbentBound": _fmt_bool(avail_inc.get("budget_bound", PENDING)),
        "euCandidateBound": _fmt_bool(avail_cand.get("budget_bound", PENDING)),
        "euIncumbentVacuous": avail_inc.get("vacuous_fraction", PENDING),
        "euCandidateVacuous": avail_cand.get("vacuous_fraction", PENDING),
        "euCandidateMembers": avail_cand.get("members", PENDING),
        "euControlVerdict": _verdict_word(verdict),
        # reverse mathematics: the sprint's one genuinely new result
        "euClaimsAttempted": sufficiency.get("claims_attempted", PENDING),
        "euClaimsVerified": sufficiency.get("verified", PENDING),
        "euClaimsRejected": sufficiency.get("rejected", PENDING),
        "euReproduced": minimisation.get("reproduced", PENDING),
        "euNotReproduced": minimisation.get("not_reproduced", PENDING),
        "euMeanFootprint": minimisation.get("mean_footprint", PENDING),
        "euMeanSufficient": minimisation.get("mean_sufficient", PENDING),
        "euMaxReduction": minimisation.get("max_reduction", PENDING),
        "euDirectCitationMean": _dig(footprints, "summary", "mean_direct"),
        "euTransitiveMean": _dig(footprints, "summary", "mean_transitive"),
        "euFootprintGrew": _dig(footprints, "summary", "theorems_whose_footprint_grew"),
        "euFootprintTheorems": _dig(footprints, "summary", "theorems"),
    }
    return m


def _fmt_bool(v):
    if v is PENDING or v is None:
        return PENDING
    return "yes" if v else "no"


def _verdict_word(v):
    if not v:
        return PENDING
    if v.get("unevaluated_conditions"):
        return "withheld"
    return "shows survival" if v.get("shows_survival") else "does not show survival"


def render(macros):
    L = [
        "% Generated by pipeline.report.texmacros. Do not edit by hand.",
        "%",
        "% Every number in the write-up comes from here. The prose contains no",
        "% digits, so it can be wrong about emphasis but not about arithmetic.",
        "",
        r"\providecommand{\euPending}{\textbf{[pending]}}",
        "",
    ]
    pending = []
    for name in sorted(macros):
        value = macros[name]
        if value is PENDING:
            pending.append(name)
            L.append(rf"\newcommand{{\{name}}}{{\euPending}}")
        else:
            L.append(rf"\newcommand{{\{name}}}{{{value}}}")
    L.append("")
    L.append(f"% {len(macros) - len(pending)} measured, {len(pending)} pending")
    for name in pending:
        L.append(f"%   pending: {name}")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    macros = collect(args.run)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(macros))

    measured = sum(1 for v in macros.values() if v is not PENDING)
    print(f"{measured}/{len(macros)} macros measured; wrote {out}")
    for name in sorted(macros):
        if macros[name] is PENDING:
            print(f"  pending  {name}")


if __name__ == "__main__":
    main()
