# Executive summary

**Question.** Given only an anonymized formal theory and a proof checker, can a
machine recover useful higher-level structure from the population of statements
it can prove — without being told what the theory means?

**Answer, three sprints in.** Partly, and the part that works is not the part
that was expected to. Structural importance computed with no semantic input
reliably identifies the same small set of statements as central, across three
independent anonymizations of the theory. Automatic concept invention fails, and
now fails under three independent attempts to rescue it: a second and more
mathematically motivated way of generating candidates does *worse* than the
first, a non-compression criterion cannot separate any concept from seed noise,
and conjecture yield cannot be measured against a prover this weak.

Everything below was produced without any component being told what the theory
denotes. The interpretation exists and is held outside this repository.

---

## What was built

A complete pipeline, dependency-light and reproducible end to end:

```
anonymous axioms → proved consequences → structural representations → clusters
                 → schemas → invented definitions → measured rediscovery loop
```

The load-bearing design decision was to build **proof terms in Python and let
Lean only kernel-check them**. Two consequences followed. The proof DAG comes
out exact and free, so dependency, size and depth are read off the term instead
of parsed back out of Lean. And emission becomes a pure function, which reduces
Lean's role to refutation: a rejected batch means the emitter is wrong, not that
the mathematics is unclear. Lean caught real emitter bugs on that basis.

**Scale.** A reference corpus of kernel-verified consequences, all distinct
after canonicalization and re-checkable in seconds, plus a much larger body
across the configuration grid. Exact counts are in the generated table at the
end of this document; none of the numbers below are typed by hand.

## What holds up

**Structural importance tracks something real.** Theorems were ranked by reuse,
downstream closure, generality, symmetry, cluster coverage and proof leverage —
every component computed from the corpus alone. The same handful of statements
about the 4-ary relation reach the top in 23–28 of 45 grid members, across three
different identifier permutations. They are the reflexivity, argument-swap and
composition family: exactly the statements that any development of this theory
has to establish before anything else can be built.

The ranking *within* that set is not stable: the mean rank correlation across
member pairs is well below 0.5 and its range spans from strongly negative to
1.0. The measure identifies a robust set; it does not robustly order it. Both
halves of that sentence are results.

**Definitional enrichment measurably compresses proofs.** Feeding invented
definitions back as a definitional extension — bridges that the kernel confirms
are the identity, so nothing new becomes provable — cut mean proof size 56 → 32,
median 44 → 30, and maximum depth 45 → 25, at essentially unchanged theorem
count. The share of statements with no existential in the conclusion rose from
95 to 229. The working hypothesis that a good concept compresses proofs is
supported on the compression side.

**Case analysis closed a hard reachability gap.** The first sprint produced 1904
theorems containing zero disjunctions. That was not a shortfall of search: the
calculus could introduce a disjunction and had no rule to consume one, and the
single axiom with a disjunctive conclusion needed premises the fixed seeding
could never produce. Any notion defined as a disjunction was therefore
*unreachable*, not merely undiscovered. Adding case analysis to the kernel, and
allowing repeated arguments in the sampled assumptions, produced 1446 disjunctive
and 1978 case-analysis-derived theorems across the grid.

## What does not hold up

**Concept invention fails the robustness test.** The best-surviving invented
definition appears in 14 of 45 members (31%). Six of the top ten never appear at
all unless disequalities are assumed. Sprint 1 reported a ranked list with large
coverage and large compression, caught one artifact with a single control, and
treated the rest as findings. The grid says that was too generous: coverage and
compression are properties of a corpus, and the corpus is a property of the
setup.

**Frequency and compression do not identify a concept.** A restatement check was
added — which axioms every supporting proof cites — and it reshapes the ranking
completely. Only **11 of 402** candidates in a representative member are
independent of any single axiom. The rest score well because one axiom is
showing through the corpus, which neither support counts nor cluster spread can
see.

That check also settles the sprint's most tempting result. The top disjunctive
candidate, recurring across 203 theorems, 6 distinct axiom profiles and 8
clusters, is a textbook defined notion of this theory — one deliberately withheld
from the system. All 203 supporting proofs cite the axiom whose conclusion it
literally is. It is a restatement propagated through the corpus, not an
invention, and it is graded as one.

**Hand-rolled numerics hid a bad result.** Sprint 1's clustering used a
hand-written single linkage, reported as a positive result. Re-run with a proper
library it puts 1382 of 1904 theorems in one cluster with a silhouette of
**−0.115** — worse than random on its own metric. Average linkage gives 501
clusters, largest 49, silhouette **+0.531**.

**Concept invention fails on every criterion tried, not just compression.**
Sprint 2 falsified compression and left the alternatives untested. Sprint 3
built them.

*Search acceleration.* Against a target set frozen in advance, no concept from
either source improves on the baseline beyond noise. Two of sixteen separate
from the baseline at all and both are worse — while keeping two to three times
as many statements. More output, less of what was wanted, which is the precise
failure raw yield was rejected for.

*Candidate source.* The sprint's falsifiable prediction was that concepts mined
from recurring proof roles would outlast concepts mined from statement syntax,
because proof structure should depend less on the seeding. It is wrong. Role
candidates are markedly less robust: best survival 3 of 45 members against 14 of
45, with 222 of 227 appearing in exactly one member and never again. A role
candidate is lifted from a concrete proof subterm, and which subterms exist
depends entirely on which proofs the search happened to build.

*Conjecture yield.* Both proposers score 0%, and that number is not usable: the
same bounded attempt recovers only 18% of statements already known true. The
yield measures the prover, not the proposer, and is reported that way.

**Not attempted.** The representation-invariance test across a second encoding,
and a control domain. Both remain open.

## Reading the corpus numbers

Across the grid, on identical machinery and an identical budget, corpus size
and existential-free content each vary by more than an order of magnitude
(exact ranges in the generated table). Any single run's numbers are a sample,
not a measurement. This is the main methodological lesson and it applies
retroactively to every number the first sprint reported.

It applied to this document too. Six numbers here were once typed by hand and
had drifted from the run they described, because the prose was updated after a
re-run and the numbers were not. They are generated now.

## Should the interpretation be published?

Not yet, and the reasoning is worth stating because the question will recur.

De-anonymization has *already happened* privately: the interpretation was
restored after discovery was frozen, every major cluster and definition was
graded, and the machine ranking was compared against a human reference. That is
the evaluation step, and it is done. What remains open is only whether the
public tree should learn the mapping.

It should not, for three reasons.

1. **Nothing found so far earns it.** The grading scale reserves its top bands
   for a genuinely non-obvious consequence or a result worth checking against
   the literature. Neither exists here. The strongest finding is a recognizable
   structure recovered by structural means, and the most eye-catching one turned
   out to be a restatement. A reveal buys nothing a reader cannot already get
   from the graded evaluation held alongside the mapping.
2. **It is irreversible and it costs future experiments.** Seed permutation,
   re-runs, the representation-invariance test, and any later run where a
   language model is allowed to inspect the formulas all depend on the public
   tree being semantics-free. Publishing the mapping ends that permanently, for
   a repository that is already private and whose findings do not require it.
3. **The guard is doing real work.** It has caught a domain term in a function
   name, in a test file, and in a draft report. Each time the cheap fix was to
   rename rather than relax the rule. Relaxing it wholesale just where
   the results are least impressive would be the wrong trade.

The condition for revisiting: a finding in the top grade bands — a consequence
that is genuinely non-obvious, or a structure that survives the grid *and* the
restatement check *and* a second encoding. At that stage the interpretation
becomes part of the claim rather than a convenience, and publishing it is
justified.

## Where things stand

| | |
|---|---|
| Pipeline | complete, reproducible, dependency-pinned |
| Verified theorems | see the generated table below |
| Robust finding | structural importance identifies a stable central set |
| Negative finding | concept invention fails on compression, acceleration and candidate source alike |
| Open | representation invariance; a control domain |
| Interpretation | evaluated privately; not published, and should not be yet |

## Generated counts

<!-- generated by pipeline.report.build; do not edit by hand -->

| quantity | value |
|---|---|
| reference corpus, kernel-verified | 1904 |
| grid members | 45 |
| grid theorems, kernel-verified | 17369 |
| grid corpus size, min-max | 84-907 |
| grid existential-free, min-max | 9-507 |
| importance rank correlation, mean | 0.4077 |
| importance rank correlation, range | -0.7714 to 1.0 |
| member pairs compared | 590 |
| best concept survival, premise-conjunction | 14/45 |
| best concept survival, proof-role | 3/45 |
| mean proof size, T0 to T1 | 56.07 to 32.43 |
| max proof depth, T0 to T1 | 45 to 25 |
| concepts separating from the ablation baseline | 2/16 |
| conjecture attempt recall on known statements | 7/40 |
