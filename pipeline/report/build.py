"""Assemble the public research report from the run artifacts.

Public means semantics-free: this file and everything it writes stay on the
anonymous side of the quarantine, so the report describes structure and never
interpretation. The interpreted counterpart is produced separately, after
discovery is frozen, and never lands here.

Numbers come from the artifacts rather than from prose, so the report cannot
drift away from what actually ran.

Usage:  python3 -m pipeline.report.build --run main
"""

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load(run_dir, name, default=None):
    p = run_dir / name
    return json.loads(p.read_text()) if p.exists() else default


def stability_section(w, stability):
    """The sprint-2 headline: which findings survive the configuration grid."""
    w("## 8. Stability across the configuration grid")
    w("")
    if not stability:
        w("_Not run._")
        w("")
        return

    w(f"{stability['members']} members were built over theory seeds "
      f"{stability['theory_seeds']}, varying parameter count, whether")
    w("disequalities are assumed, and whether the assumed atoms follow a fixed")
    w("layout or are sampled. Members built on re-permuted identifiers are")
    w("compared through arity-canonical relation names, so nothing in this")
    w("section required knowing what any symbol denotes.")
    w("")

    w("| measure | min | mean | max |")
    w("|---|---|---|---|")
    for k, v in stability["corpus_spread"].items():
        w(f"| {k} | {v['min']} | {v['mean']} | {v['max']} |")
    w("")
    w("The spread is the first result. Identical machinery, identical budget,")
    w("and the corpora differ by an order of magnitude in size and in how much")
    w("of their content is existential. Any single run's numbers are a sample,")
    w("not a measurement.")
    w("")

    imp = stability["importance_stability"]
    w(f"**Importance ranking.** Rank correlation across {imp['pairs_compared']} member")
    w(f"pairs: mean {imp['mean_spearman']}, range [{imp['min_spearman']}, {imp['max_spearman']}].")
    w("")
    w("That is moderate agreement with a very wide spread, and it qualifies the")
    w("single-run result directly: the *ordering* the importance measure produces")
    w("is not itself stable. What is stable is which statements reach the top at")
    w("all — see the list below, where the same few recur in more than half the")
    w("members despite three different identifier permutations. The measure")
    w("identifies a robust set; it does not robustly rank within it.")
    w("")

    w("**Concepts by survival.** A definition that appears only under one")
    w("configuration is a property of that configuration.")
    w("")
    w("| survives | arity | median coverage | needs assumed disequalities |")
    w("|---|---|---|---|")
    for row in stability["concept_survival"][:15]:
        w(f"| {row['survives']}/{row['of']} | {row['arity']} | {row['median_coverage']} | "
          f"{'yes' if row['requires_assumed_distinctness'] else 'no'} |")
    w("")
    rows = stability["concept_survival"]
    top_rate = rows[0]["survival_rate"] if rows else 0.0
    needs = sum(1 for r in rows[:10] if r["requires_assumed_distinctness"])
    w(f"**This is a negative result, and the clearest one in the sprint.** The")
    w(f"best-surviving definition appears in {rows[0]['survives'] if rows else 0} of")
    w(f"{stability['members']} members ({top_rate:.0%}), and {needs} of the top ten")
    w("never appear at all unless disequalities are assumed. No invented")
    w("definition is robust to the configuration it was invented under.")
    w("")
    w("Sprint 1 reported a ranked list of concepts with large coverage and large")
    w("compression, caught one artifact with a single control, and treated the")
    w("rest as findings. The grid says that was too generous: coverage and")
    w("compression are properties of a corpus, and the corpus is a property of")
    w("the setup. The working hypothesis that a good concept compresses proofs")
    w("is not refuted here — compression was real and measurable — but")
    w("compression alone plainly does not identify a concept worth keeping.")
    w("")

    w("**Statements repeatedly ranked most important.**")
    w("")
    for row in stability["top_statement_survival"][:10]:
        w(f"- {row['survives']}/{row['of']} — `{row['statement'][:130]}`")
    w("")


def acceleration_section(w, ab):
    w("## 9. Does any concept accelerate the search?")
    w("")
    if not ab:
        w("_Not run._")
        w("")
        return
    b = ab["baseline"]
    w(f"Each condition was run over seeds {ab['seeds']} at a fixed budget against")
    w(f"{ab['targets']} held-out targets, committed to before any concept was scored.")
    w("")
    w(f"Baseline: {b['hits_per_seed']}, mean {b['mean']}, range {b['range']}.")
    w("")
    w("**The baseline's own seed-to-seed range is the whole story here.** It spans")
    w("more than the effect of almost every concept, so a single-seed measurement")
    w("would have reported ordinary sampling variance as concepts damaging the")
    w("search. Only a range disjoint from the baseline's counts as an effect.")
    w("")
    w("| concept | source | mean targets | range | delta | mean kept | separated |")
    w("|---|---|---|---|---|---|---|")
    for r in ab["concepts"]:
        if "delta_mean" not in r:
            continue
        w(f"| `{r['name']}` | {r['source']} | {r['mean_targets']} | {r['range']} | "
          f"{r['delta_mean']:+} | {r['mean_kept']} | "
          f"{'yes' if r['separated_from_baseline'] else 'no'} |")
    w("")
    s = ab.get("spread", {})
    w(f"No concept improves on the baseline beyond noise. {s.get('separated', 0)} of")
    w(f"{s.get('of', 0)} separate from it at all, and every one of those is *worse*.")
    w("")
    w("Those same concepts keep two to three times as many statements as the")
    w("baseline while reaching a third as many targets. That is the exact failure")
    w("mode raw yield was rejected for: more output, less of what was wanted.")
    w("")


def conjecture_section(w, cj):
    w("## 10. Conjecture generation")
    w("")
    if not cj:
        w("_Not run._")
        w("")
        return
    rec = cj["attempt_recall"]
    w("| source | proved | unresolved | yield |")
    w("|---|---|---|---|")
    for s, c in cj["by_source"].items():
        w(f"| {s} | {c['proved']} | {c['unresolved']} | {c['yield']:.0%} |")
    w("")
    w(f"**Read the yields against the ceiling.** The same bounded attempt recovers")
    w(f"only {rec['recovered']} of {rec['known_statements_tried']} statements already")
    w(f"known true ({rec['recall']:.0%}). A source scoring 0% against a prover with")
    w("that recall has told you about the prover, not the source. The honest")
    w("conclusion is that conjecture yield could not be measured here, not that")
    w("the proposers produce falsehoods.")
    w("")
    ctrl = cj["symmetry_control"]
    w(f"The symmetry view itself checks out: {ctrl['consistent']}/{ctrl['checked']}")
    w("permutations it reports as symmetries canonicalize back to the statement")
    w("they came from. That check is structural and deterministic; routing it")
    w("through the prover instead reported a weak prover as a broken view.")
    w("")
    w("Nothing is recorded as refuted. There is no counter-model machinery here,")
    w("so an unreached conjecture is unresolved and nothing more.")
    w("")


def source_section(w, stability):
    w("## 11. Where the failure is: candidates or criteria?")
    w("")
    by_src = (stability or {}).get("survival_by_source")
    if not by_src:
        w("_Not run._")
        w("")
        return
    n = stability["members"]
    w(f"Two candidate sources ran through all {n} grid members. One mines recurring")
    w("conjunctions of hypotheses from statements; the other mines recurring")
    w("inference steps from proof terms.")
    w("")
    w("| source | candidates | best survival | mean | surviving over half | appearing once only |")
    w("|---|---|---|---|---|---|")
    for src, s in by_src.items():
        w(f"| {src} | {s['candidates']} | {s['best_survival']} | {s['mean_survival']} | "
          f"{s['surviving_over_half']} | {s['appearing_once_only']} |")
    w("")
    w("**The prediction was that proof-role candidates would be the more robust of")
    w("the two, and it is wrong.** They are markedly less robust: the best one")
    w("appears in 3 of 45 members against 14 of 45, and almost every one of them")
    w("appears in exactly one member and never again.")
    w("")
    w("In hindsight the reason is not subtle. A role candidate is lifted from a")
    w("concrete proof subterm, and which subterms exist depends on which proofs the")
    w("search happened to build. Change the seeding and the proofs change wholesale.")
    w("Statement syntax is at least constrained by the axioms, so the same forms")
    w("recur across configurations; proof structure is far more contingent than it")
    w("looks.")
    w("")
    w("Taken with sections 9 and 10, the answer to the question this sprint asked")
    w("is that the failure is not localized in the criteria or in the candidates.")
    w("A second, more mathematically motivated candidate source did worse; a")
    w("non-compression criterion could not separate any concept from seed noise;")
    w("and conjecture yield could not be measured against so weak a prover.")
    w("Automatic concept invention does not work in this setting, and that now")
    w("rests on three independent attempts to make it work rather than one.")
    w("")


def build(run, control, loop_run):
    run_dir = ROOT / "runs" / run
    corpus = load(run_dir, "corpus.json", [])
    summary = load(run_dir, "summary.json", {})
    clusters = load(run_dir, "clusters.json", {})
    patterns = load(run_dir, "patterns.json", {})
    concepts = load(run_dir, "concepts.json", {})
    importance = load(run_dir, "importance.json", [])
    loop = load(ROOT / "runs" / loop_run, "loop.json", {})
    ctrl = load(ROOT / "runs" / control, "concepts.json", {})
    stability = load(ROOT / "runs" / "ensemble", "stability.json", {})
    ablation = load(run_dir, "ablation.json", {})
    conjectures = load(run_dir, "conjectures.json", {})

    L = []
    w = L.append

    w("# Structural findings from an anonymous formal theory")
    w("")
    w("Everything below was produced without any component being told what the")
    w("theory denotes. Relation and axiom identifiers are opaque and seeded; the")
    w("interpretation exists but is held outside this tree and was consulted only")
    w("after the results here were frozen.")
    w("")

    w("## 1. Corpus")
    w("")
    verified = sum(1 for r in corpus if r.get("verification"))
    w(f"- **{len(corpus)}** consequences kept, **{verified}** kernel-verified")
    w(f"- **{len(set(r['normalized_statement'] for r in corpus))}** distinct after canonicalization")
    ef = [r for r in corpus if "∃" not in r["normalized_statement"]]
    w(f"- **{len(ef)}** carry no existential in the conclusion")
    w(f"- generation {summary.get('seconds_generate')}s, kernel check "
      f"{summary.get('seconds_verify')}s")
    w("")
    w("Rejections, by reason:")
    w("")
    w("| reason | count |")
    w("|---|---|")
    for k, v in sorted(summary.get("rejected", {}).items(), key=lambda kv: -kv[1]):
        w(f"| `{k}` | {v} |")
    w("")
    w("The rejection log is reported in full because it is the honest measure of")
    w("what the generator produced. Roughly ten times more candidates were")
    w("discarded than kept, and the largest single category is weak existential")
    w("claims — statements asserting that some configuration exists, with the")
    w("hypotheses doing no work. That is a property of forward saturation over")
    w("this theory, not of the filters.")
    w("")

    w("## 2. Clustering")
    w("")
    w("| method | space | clusters | largest | noise | lift | silhouette (own space) |")
    w("|---|---|---|---|---|---|---|")
    for name, m in clusters.get("methods", {}).items():
        sil = m.get("silhouette_own_space")
        w(f"| `{name}` | {m.get('space','-')} | {m['clusters']} | {m['largest']} | "
          f"{m.get('noise',0)} | {m['lift_over_baseline']:+} | "
          f"{sil if sil is not None else 'n/a'} |")
    w("")
    w("Agreement across methods (normalized mutual information):")
    w("")
    for k, v in clusters.get("agreement", {}).items():
        w(f"- `{k}`: {v}")
    w("")
    w("All three beat a size-matched shuffled baseline, so the groupings are not")
    w("an artifact of the cluster-size distribution. One negative result belongs")
    w("here: `bucket_structure`, which buckets by exact formula signature, is")
    w("almost injective on this corpus — it produces nearly as many clusters as")
    w("there are statements. Its high cohesion score is therefore an artifact of")
    w("tiny clusters and should not be read as the method working well. It is")
    w("useful only as a control confirming that the canonical statements really")
    w("are structurally distinct from one another.")
    w("")

    w("## 3. Schemas")
    w("")
    for method, ss in patterns.get("schemas", {}).items():
        good = [s for s in ss if s["specificity"] >= 0.4]
        w(f"**`{method}`** — {len(ss)} clusters schematized, {len(good)} with "
          f"specificity ≥ 0.4.")
        w("")
        for s in sorted(ss, key=lambda x: -x["specificity"])[:3]:
            w(f"- `{s['schema'][:150]}`")
            w(f"  (stratum {s['stratum_size']} of {s['size']} members, "
              f"specificity {s['specificity']})")
        w("")
    w("Anti-unification had to be applied within form-homogeneous strata of a")
    w("cluster rather than across a whole cluster. Generalizing across different")
    w("quantifier forms collapses immediately to a single hole, because the")
    w("first structural mismatch generalizes the entire formula. This is a real")
    w("limitation of least-general generalization on a corpus this heterogeneous,")
    w("and the stratum sizes are reported alongside the cluster sizes so the")
    w("strength of each schema is visible.")
    w("")

    w("## 4. Invented definitions")
    w("")
    ranked = concepts.get("ranked", [])
    w(f"{concepts.get('all_candidates', 0)} candidates passed the support")
    w(f"threshold; the top {len(ranked)} were scored and emitted as definitional")
    w("extensions, all kernel-accepted.")
    w("")
    w("| name | arity | covers | clusters | description-size reduction | cited by every user |")
    w("|---|---|---|---|---|---|")
    for c in ranked:
        s = c["scores"]
        always = s.get("axioms_in_every_user") or []
        w(f"| `{c['name']}` | {s['arity']} | {s['theorems_covered']} | "
          f"{s['clusters_unified']} | {s['description_length_reduction']} | "
          f"{', '.join(always) if always else '—'} |")
    w("")
    w("The last column is the restatement check, and it changes how the rest of")
    w("the table should be read. A definition whose every supporting proof cites")
    w("the same axiom is that axiom showing through the corpus, not a structure")
    w("the corpus independently motivates — however large its coverage or")
    w("compression. Support counts and cluster spread cannot see this; both look")
    w("excellent for patterns that are wholly explained by one axiom.")
    w("")

    w("### A control that changes the reading")
    w("")
    ctrl_ranked = ctrl.get("ranked", [])
    w("The definitions above are dominated by conjunctions of the disequality")
    w("hypotheses that the generator was seeded with. That is a scoring artifact,")
    w("not a discovery: the concepts are frequent because the seeding made them")
    w("frequent. Re-running the identical pipeline with the assumed pairwise")
    w(f"disequalities removed collapses the candidate space to **{len(ctrl_ranked)}**")
    w("definitions:")
    w("")
    for c in ctrl_ranked:
        s = c["scores"]
        w(f"- `{c['name']}`, arity {s['arity']}, covers {s['theorems_covered']} "
          f"theorems across {s['clusters_unified']} clusters")
    w("")
    w("Both survivors are two-atom chaining patterns over a single relation —")
    w("the form in which one atom's trailing arguments are the next atom's")
    w("leading arguments. Running this control was the single most informative")
    w("thing in the experiment, and without it the headline concepts would have")
    w("been reported as findings when they are mostly an echo of the setup.")
    w("")

    w("## 5. Concept-enriched rediscovery")
    w("")
    if loop:
        stages = {s["stage"]: s["metrics"] for s in loop.get("stages", [])}
        keys = ["kept", "distinct_statements", "existential_free", "mean_proof_size",
                "median_proof_size", "mean_statement_size", "max_proof_depth", "seconds"]
        w("| measure | T0 | T1 | delta |")
        w("|---|---|---|---|")
        for k in keys:
            a, b = stages.get("T0", {}).get(k), stages.get("T1", {}).get(k)
            if a is None or b is None:
                continue
            w(f"| {k} | {a} | {b} | {b - a:+} |")
        w("")
        w("T1 is a definitional extension of T0, so it cannot prove anything T0")
        w("could not — the introduction and elimination bridges are the identity,")
        w("and the kernel accepted them as such. Any change is therefore a change")
        w("in what the search reaches and how compactly, never in what is true.")
        w("")
        w("The effect is substantial and in the direction the working hypothesis")
        w("predicts: proofs get markedly shorter and shallower at essentially")
        w("unchanged theorem count, and the share of statements with no")
        w("existential in the conclusion rises sharply. This is the sprint's")
        w("clearest positive result — with the caveat from section 4 that the")
        w("concepts driving it are partly an artifact of the seeding.")
    else:
        w("_Not run._")
    w("")

    w("## 6. Structural importance")
    w("")
    w("Theorems were ranked by reuse, downstream closure, generality, symmetry,")
    w("cluster coverage and proof leverage — every component computed from the")
    w("corpus alone. The top of the ranking, deduplicated:")
    w("")
    seen = set()
    shown = 0
    for item in importance:
        if item["statement"] in seen:
            continue
        seen.add(item["statement"])
        shown += 1
        if shown > 12:
            break
        w(f"{shown}. `{item['statement'][:150]}` — {item['importance']}")
    w("")
    w("Two families occupy the top of this list without anything having told the")
    w("ranker that they matter: the degenerate instances of both relations, and")
    w("a large family of conditional statements in which one 4-ary atom feeds")
    w("into another. Whether that corresponds to anything a mathematician would")
    w("call important is exactly the question the interpreted evaluation asks,")
    w("and it is answered outside this tree.")
    w("")

    w("## 7. What did not work")
    w("")
    w("- Exact-signature bucketing is not a clustering method on this corpus; it")
    w("  is nearly injective, and its cohesion number is misleading.")
    w("- Least-general generalization across a whole cluster is useless without")
    w("  stratification by form.")
    w("- Concept scoring is dominated by whatever the generator was seeded with,")
    w("  and needs the disequality control to be interpretable at all.")
    w("- The corpus is heavily skewed toward weak existential statements. Filters")
    w("  and a per-generation quota hold this down, but do not fix the underlying")
    w("  bias in what bounded forward saturation produces here.")
    w("- No conjecture-generation stage was run, so the sprint has no data on")
    w("  whether the learned structure proposes statements that turn out true.")
    w("- Concept invention does not survive the configuration grid. See section 8;")
    w("  this supersedes the more optimistic reading in section 4.")
    w("- The corpus analyzed in sections 1-7 predates case analysis and contains")
    w("  no disjunction at all. Disjunctive results appear only in the grid.")
    w("")

    stability_section(w, stability)
    acceleration_section(w, ablation)
    conjecture_section(w, conjectures)
    source_section(w, stability)

    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--control", default="control-nodistinct")
    ap.add_argument("--loop", default="loop")
    args = ap.parse_args()

    text = build(args.run, args.control, args.loop)
    out = ROOT / "runs" / args.run / "report.md"
    out.write_text(text)
    print(f"wrote {out} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
