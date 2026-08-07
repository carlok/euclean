# Structural findings from an anonymous formal theory

Everything below was produced without any component being told what the
theory denotes. Relation and axiom identifiers are opaque and seeded; the
interpretation exists but is held outside this tree and was consulted only
after the results here were frozen.

## 1. Corpus

- **1904** consequences kept, **1904** kernel-verified
- **1904** distinct after canonicalization
- **154** carry no existential in the conclusion
- generation 190.48s, kernel check 8.17s

Rejections, by reason:

| reason | count |
|---|---|
| `unanchored-existential` | 26822 |
| `duplicate` | 8642 |
| `weaker-than-known` | 6530 |
| `quota-existential` | 1254 |
| `trivial-equation` | 707 |
| `irrelevant-hypothesis` | 424 |
| `assumption-restated` | 320 |

The rejection log is reported in full because it is the honest measure of
what the generator produced. Roughly ten times more candidates were
discarded than kept, and the largest single category is weak existential
claims — statements asserting that some configuration exists, with the
hypotheses doing no work. That is a property of forward saturation over
this theory, not of the filters.

## 2. Clustering

| method | space | clusters | largest | noise | lift | silhouette (own space) |
|---|---|---|---|---|---|---|
| `baseline_kmeans` | numeric | 28 | 292 | 0 | +0.1602 | 0.2314845836266914 |
| `baseline_single_linkage` | dependency | 161 | 1382 | 0 | +0.1715 | -0.11534302074928218 |
| `bucket_structure` | wl | 1789 | 6 | 0 | +0.4123 | 0.10871847771416364 |
| `kmeans_numeric` | numeric | 28 | 291 | 0 | +0.1681 | 0.26271960962658025 |
| `linkage_dependency` | dependency | 501 | 49 | 0 | +0.6674 | 0.530611058405357 |
| `density_dependency` | dependency | 157 | 41 | 343 | +0.394 | 0.3208577023054604 |
| `kmeans_wl_embedding` | wl | 28 | 208 | 0 | +0.1116 | 0.19963083203530177 |
| `spectral_wl` | wl | 28 | 361 | 0 | +0.1007 | 0.1928027015720481 |

Agreement across methods (normalized mutual information):

- `baseline_kmeans~baseline_single_linkage`: 0.3178
- `baseline_kmeans~bucket_structure`: 0.6168
- `baseline_kmeans~kmeans_numeric`: 0.8337
- `baseline_kmeans~linkage_dependency`: 0.5948
- `baseline_kmeans~density_dependency`: 0.4505
- `baseline_kmeans~kmeans_wl_embedding`: 0.4618
- `baseline_kmeans~spectral_wl`: 0.4504
- `baseline_single_linkage~bucket_structure`: 0.4874
- `baseline_single_linkage~kmeans_numeric`: 0.3346
- `baseline_single_linkage~linkage_dependency`: 0.558
- `baseline_single_linkage~density_dependency`: 0.4281
- `baseline_single_linkage~kmeans_wl_embedding`: 0.3379
- `baseline_single_linkage~spectral_wl`: 0.3143
- `bucket_structure~kmeans_numeric`: 0.6278
- `bucket_structure~linkage_dependency`: 0.8729
- `bucket_structure~density_dependency`: 0.7682
- `bucket_structure~kmeans_wl_embedding`: 0.6338
- `bucket_structure~spectral_wl`: 0.5851
- `kmeans_numeric~linkage_dependency`: 0.6074
- `kmeans_numeric~density_dependency`: 0.4683
- `kmeans_numeric~kmeans_wl_embedding`: 0.4994
- `kmeans_numeric~spectral_wl`: 0.4842
- `linkage_dependency~density_dependency`: 0.7939
- `linkage_dependency~kmeans_wl_embedding`: 0.5369
- `linkage_dependency~spectral_wl`: 0.5236
- `density_dependency~kmeans_wl_embedding`: 0.4013
- `density_dependency~spectral_wl`: 0.3725
- `kmeans_wl_embedding~spectral_wl`: 0.7641

All three beat a size-matched shuffled baseline, so the groupings are not
an artifact of the cluster-size distribution. One negative result belongs
here: `bucket_structure`, which buckets by exact formula signature, is
almost injective on this corpus — it produces nearly as many clusters as
there are statements. Its high cohesion score is therefore an artifact of
tiny clusters and should not be read as the method working well. It is
useful only as a control confirming that the canonical statements really
are structurally distinct from one another.

## 3. Schemas

**`kmeans_numeric`** — 24 clusters schematized, 24 with specificity ≥ 0.4.

- `(∀ b0 b1 b2 b3 b4 b5, (R1 b0 b1 b2 b3 → (R1 b2 b3 b4 b5 → (∃ b6, ?a113))))`
  (stratum 37 of 43 members, specificity 0.955)
- `(∀ b0 b1 b2 b3 b4, (R0 b0 b1 b2 → (R0 b2 b3 b4 → ((¬ (b0 = b1)) → ((¬ (?a33 = ?a34)) → ((¬ (b2 = ?a35)) → (∃ b5, ?a36)))))))`
  (stratum 14 of 48 members, specificity 0.882)
- `(∀ b0 b1 b2 b3 b4, (R0 b0 b1 b2 → ((¬ (b0 = b1)) → ((¬ (b0 = b2)) → (∃ b5, (∃ b6, R1 ?a22 ?a23 ?a24 ?a25))))))`
  (stratum 8 of 34 members, specificity 0.867)

**`linkage_dependency`** — 73 clusters schematized, 73 with specificity ≥ 0.4.

- `(∀ b0 b1 b2 b3 b4 b5, (R0 b0 b1 b2 → (R0 b2 b3 b4 → ((¬ (b0 = b1)) → ((¬ (b0 = b2)) → ((¬ (b2 = b3)) → (∃ b6, ?a3)))))))`
  (stratum 4 of 16 members, specificity 0.971)
- `(∀ b0 b1 b2 b3 b4 b5, (R0 b0 b1 b2 → (R0 b2 b3 b4 → ((¬ (b0 = b1)) → ((¬ (b0 = b2)) → ((¬ (b0 = b5)) → ((¬ (b1 = b5)) → ((¬ (b2 = b3)) → ((¬ (b2 = b4)`
  (stratum 4 of 5 members, specificity 0.966)
- `(∀ b0 b1 b2 b3 b4 b5 b6 b7, (R0 b0 b1 b2 → (R0 b2 b3 b4 → ((¬ (b0 = b1)) → ((¬ (b0 = b2)) → ((¬ (b0 = b5)) → ((¬ (b2 = b3)) → ((¬ (b2 = b4)) → ((¬ (b4`
  (stratum 6 of 11 members, specificity 0.944)

**`bucket_structure`** — 7 clusters schematized, 7 with specificity ≥ 0.4.

- `(∀ b0 b1 b2, (∃ b3, R1 ?a11 b3 ?a12 ?a13))`
  (stratum 6 of 6 members, specificity 0.727)
- `(∀ b0 b1 b2, (∃ b3, R1 b3 ?a11 ?a12 ?a13))`
  (stratum 6 of 6 members, specificity 0.727)
- `(∀ b0 b1 b2, (∃ b3, R1 ?a12 ?a13 b3 ?a14))`
  (stratum 6 of 6 members, specificity 0.727)

Anti-unification had to be applied within form-homogeneous strata of a
cluster rather than across a whole cluster. Generalizing across different
quantifier forms collapses immediately to a single hole, because the
first structural mismatch generalizes the entire formula. This is a real
limitation of least-general generalization on a corpus this heterogeneous,
and the stratum sizes are reported alongside the cluster sizes so the
strength of each schema is visible.

## 4. Invented definitions

125 candidates passed the support
threshold; the top 10 were scored and emitted as definitional
extensions, all kernel-accepted.

| name | arity | covers | clusters | description-size reduction | cited by every user |
|---|---|---|---|---|---|
| `C00` | 3 | 1384 | 20 | 13823 | — |
| `C01` | 4 | 1087 | 21 | 9765 | — |
| `C02` | 4 | 982 | 20 | 8820 | — |
| `C03` | 4 | 965 | 19 | 8667 | — |
| `C04` | 3 | 1668 | 24 | 8328 | — |
| `C05` | 4 | 844 | 16 | 7578 | a1 |
| `C06` | 3 | 1481 | 22 | 7393 | — |
| `C07` | 5 | 888 | 17 | 7085 | — |
| `C08` | 5 | 888 | 17 | 7085 | — |
| `C09` | 3 | 1384 | 20 | 6908 | — |

The last column is the restatement check, and it changes how the rest of
the table should be read. A definition whose every supporting proof cites
the same axiom is that axiom showing through the corpus, not a structure
the corpus independently motivates — however large its coverage or
compression. Support counts and cluster spread cannot see this; both look
excellent for patterns that are wholly explained by one axiom.

### A control that changes the reading

The definitions above are dominated by conjunctions of the disequality
hypotheses that the generator was seeded with. That is a scoring artifact,
not a discovery: the concepts are frequent because the seeding made them
frequent. Re-running the identical pipeline with the assumed pairwise
disequalities removed collapses the candidate space to **2**
definitions:

- `C00`, arity 6, covers 329 theorems across 14 clusters
- `C01`, arity 5, covers 34 theorems across 4 clusters

Both survivors are two-atom chaining patterns over a single relation —
the form in which one atom's trailing arguments are the next atom's
leading arguments. Running this control was the single most informative
thing in the experiment, and without it the headline concepts would have
been reported as findings when they are mostly an echo of the setup.

## 5. Concept-enriched rediscovery

| measure | T0 | T1 | delta |
|---|---|---|---|
| kept | 685 | 672 | -13 |
| distinct_statements | 685 | 672 | -13 |
| existential_free | 95 | 229 | +134 |
| mean_proof_size | 56.07 | 32.43 | -23.64 |
| median_proof_size | 44 | 30.0 | -14.0 |
| mean_statement_size | 35.7 | 32.35 | -3.3500000000000014 |
| max_proof_depth | 45 | 25 | -20 |
| seconds | 35.4 | 21.3 | -14.099999999999998 |

T1 is a definitional extension of T0, so it cannot prove anything T0
could not — the introduction and elimination bridges are the identity,
and the kernel accepted them as such. Any change is therefore a change
in what the search reaches and how compactly, never in what is true.

The effect is substantial and in the direction the working hypothesis
predicts: proofs get markedly shorter and shallower at essentially
unchanged theorem count, and the share of statements with no
existential in the conclusion rises sharply. This is the sprint's
clearest positive result — with the caveat from section 4 that the
concepts driving it are partly an artifact of the seeding.

## 6. Structural importance

Theorems were ranked by reuse, downstream closure, generality, symmetry,
cluster coverage and proof leverage — every component computed from the
corpus alone. The top of the ranking, deduplicated:

1. `∀ (b0 : Obj) (b1 : Obj), R0 b1 b0 b0` — 0.9863
2. `∀ (b0 : Obj) (b1 : Obj), R0 b0 b1 b1` — 0.9862
3. `∀ (b0 : Obj), R1 b0 b0 b0 b0` — 0.9748
4. `∀ (b0 : Obj) (b1 : Obj), R1 b0 b0 b1 b1` — 0.972
5. `∀ (b0 : Obj) (b1 : Obj), R1 b1 b1 b0 b0` — 0.9664
6. `∀ (b0 : Obj) (b1 : Obj), R1 b0 b1 b0 b1` — 0.9658
7. `∀ (b0 : Obj) (b1 : Obj), R1 b1 b0 b0 b1` — 0.9607
8. `∀ (b0 : Obj) (b1 : Obj), R1 b1 b0 b1 b0` — 0.9607
9. `∀ (b0 : Obj) (b1 : Obj) (b2 : Obj) (b3 : Obj) (b4 : Obj) (b5 : Obj), R1 b0 b1 b2 b3 → R1 b2 b3 b4 b5 → R1 b0 b1 b5 b4` — 0.9607
10. `∀ (b0 : Obj) (b1 : Obj) (b2 : Obj) (b3 : Obj) (b4 : Obj) (b5 : Obj), R1 b0 b1 b2 b3 → R1 b2 b3 b4 b5 → R1 b5 b4 b0 b1` — 0.9604
11. `∀ (b0 : Obj) (b1 : Obj) (b2 : Obj) (b3 : Obj) (b4 : Obj) (b5 : Obj), R1 b0 b1 b2 b3 → R1 b2 b3 b4 b5 → R1 b0 b1 b4 b5` — 0.96
12. `∀ (b0 : Obj) (b1 : Obj) (b2 : Obj) (b3 : Obj) (b4 : Obj) (b5 : Obj), R1 b0 b1 b2 b3 → R1 b2 b3 b4 b5 → R1 b4 b5 b1 b0` — 0.9597

Two families occupy the top of this list without anything having told the
ranker that they matter: the degenerate instances of both relations, and
a large family of conditional statements in which one 4-ary atom feeds
into another. Whether that corresponds to anything a mathematician would
call important is exactly the question the interpreted evaluation asks,
and it is answered outside this tree.

## 7. What did not work

- Exact-signature bucketing is not a clustering method on this corpus; it
  is nearly injective, and its cohesion number is misleading.
- Least-general generalization across a whole cluster is useless without
  stratification by form.
- Concept scoring is dominated by whatever the generator was seeded with,
  and needs the disequality control to be interpretable at all.
- The corpus is heavily skewed toward weak existential statements. Filters
  and a per-generation quota hold this down, but do not fix the underlying
  bias in what bounded forward saturation produces here.
- No conjecture-generation stage was run, so the sprint has no data on
  whether the learned structure proposes statements that turn out true.
- Concept invention does not survive the configuration grid. See section 8;
  this supersedes the more optimistic reading in section 4.
- The corpus analyzed in sections 1-7 predates case analysis and contains
  no disjunction at all. Disjunctive results appear only in the grid.

## 8. Stability across the configuration grid

45 members were built over theory seeds [0, 1, 2], varying parameter count, whether
disequalities are assumed, and whether the assumed atoms follow a fixed
layout or are sampled. Members built on re-permuted identifiers are
compared through arity-canonical relation names, so nothing in this
section required knowing what any symbol denotes.

| measure | min | mean | max |
|---|---|---|---|
| kept | 84 | 386.0 | 907 |
| existential_free | 9 | 116.8 | 507 |
| disjunctive | 0 | 25.4 | 307 |
| case_analysis_derived | 0 | 33.5 | 372 |
| concept_candidates | 0 | 24.2 | 69 |

The spread is the first result. Identical machinery, identical budget,
and the corpora differ by an order of magnitude in size and in how much
of their content is existential. Any single run's numbers are a sample,
not a measurement.

**Importance ranking.** Rank correlation across 590 member
pairs: mean 0.4077, range [-0.7714, 1.0].

That is moderate agreement with a very wide spread, and it qualifies the
single-run result directly: the *ordering* the importance measure produces
is not itself stable. What is stable is which statements reach the top at
all — see the list below, where the same few recur in more than half the
members despite three different identifier permutations. The measure
identifies a robust set; it does not robustly rank within it.

**Concepts by survival.** A definition that appears only under one
configuration is a property of that configuration.

| survives | arity | median coverage | needs assumed disequalities |
|---|---|---|---|
| 14/45 | 3 | 49 | yes |
| 14/45 | 5 | 34 | no |
| 7/45 | 3 | 24 | yes |
| 6/45 | 6 | 44 | no |
| 6/45 | 6 | 36 | no |
| 6/45 | 4 | 21 | yes |
| 6/45 | 4 | 20 | yes |
| 5/45 | 3 | 24 | yes |
| 4/45 | 3 | 247 | yes |
| 4/45 | 3 | 130 | no |
| 4/45 | 3 | 101 | yes |
| 3/45 | 2 | 138 | yes |
| 3/45 | 3 | 113 | no |
| 3/45 | 4 | 89 | no |
| 3/45 | 3 | 25 | yes |

**This is a negative result, and the clearest one in the sprint.** The
best-surviving definition appears in 14 of
45 members (31%), and 6 of the top ten
never appear at all unless disequalities are assumed. No invented
definition is robust to the configuration it was invented under.

Sprint 1 reported a ranked list of concepts with large coverage and large
compression, caught one artifact with a single control, and treated the
rest as findings. The grid says that was too generous: coverage and
compression are properties of a corpus, and the corpus is a property of
the setup. The working hypothesis that a good concept compresses proofs
is not refuted here — compression was real and measurable — but
compression alone plainly does not identify a concept worth keeping.

**Statements repeatedly ranked most important.**

- 34/45 — `∀ (b0 : Obj) (b1 : Obj), Rel4_0 b1 b0 b0 b1`
- 31/45 — `∀ (b0 : Obj) (b1 : Obj), Rel4_0 b0 b1 b0 b1`
- 29/45 — `∀ (b0 : Obj) (b1 : Obj), Rel4_0 b1 b0 b1 b0`
- 22/45 — `∀ (b0 : Obj), Rel4_0 b0 b0 b0 b0`
- 14/45 — `∀ (b0 : Obj) (b1 : Obj), Rel3_0 b0 b1 b1`
- 14/45 — `∀ (b0 : Obj) (b1 : Obj), Rel4_0 b1 b1 b0 b0`
- 13/45 — `∀ (b0 : Obj) (b1 : Obj), Rel4_0 b0 b0 b1 b1`
- 10/45 — `∀ (b0 : Obj) (b1 : Obj), Rel3_0 b1 b0 b0`
- 8/45 — `∀ (b0 : Obj) (b1 : Obj) (b2 : Obj) (b3 : Obj), Rel4_0 b0 b1 b2 b3 → Rel4_0 b2 b3 b1 b0`
- 7/45 — `∀ (b0 : Obj) (b1 : Obj) (b2 : Obj) (b3 : Obj), Rel4_0 b0 b1 b2 b3 → Rel4_0 b1 b0 b2 b3`

## 9. Does any concept accelerate the search?

Each condition was run over seeds [0, 1, 2, 3, 4] at a fixed budget against
80 held-out targets, committed to before any concept was scored.

Baseline: [18, 12, 8, 20, 13], mean 14.2, range [8, 20].

**The baseline's own seed-to-seed range is the whole story here.** It spans
more than the effect of almost every concept, so a single-seed measurement
would have reported ordinary sampling variance as concepts damaging the
search. Only a range disjoint from the baseline's counts as an effect.

| concept | source | mean targets | range | delta | mean kept | separated |
|---|---|---|---|---|---|---|
| `S00` | premise-conjunction | 15.0 | [12, 19] | +0.8 | 141.2 | no |
| `S01` | premise-conjunction | 14.8 | [10, 21] | +0.6 | 112.4 | no |
| `S02` | premise-conjunction | 15.2 | [12, 19] | +1.0 | 147.2 | no |
| `S03` | premise-conjunction | 15.6 | [12, 18] | +1.4 | 146.6 | no |
| `S04` | premise-conjunction | 13.6 | [12, 16] | -0.6 | 118.4 | no |
| `S05` | premise-conjunction | 14.4 | [10, 20] | +0.2 | 125.4 | no |
| `S06` | premise-conjunction | 14.0 | [11, 17] | -0.2 | 133.4 | no |
| `S07` | premise-conjunction | 14.6 | [13, 18] | +0.4 | 143.2 | no |
| `R00` | proof-role | 5.6 | [4, 7] | -8.6 | 366.4 | yes |
| `R01` | proof-role | 13.0 | [6, 21] | -1.2 | 265.4 | no |
| `R02` | proof-role | 13.8 | [11, 17] | -0.4 | 212.0 | no |
| `R03` | proof-role | 14.2 | [8, 20] | +0.0 | 134.8 | no |
| `R04` | proof-role | 6.0 | [4, 8] | -8.2 | 401.6 | no |
| `R05` | proof-role | 14.2 | [8, 20] | +0.0 | 134.8 | no |
| `R06` | proof-role | 5.6 | [4, 7] | -8.6 | 366.4 | yes |
| `R07` | proof-role | 6.0 | [4, 8] | -8.2 | 401.6 | no |

No concept improves on the baseline beyond noise. 2 of
16 separate from it at all, and every one of those is *worse*.

Those same concepts keep two to three times as many statements as the
baseline while reaching a third as many targets. That is the exact failure
mode raw yield was rejected for: more output, less of what was wanted.

## 10. Conjecture generation

| source | proved | unresolved | yield |
|---|---|---|---|
| hypothesis-dropping | 0 | 40 | 0% |
| positive-control | 7 | 33 | 18% |
| symmetry | 0 | 41 | 0% |
| symmetry-control | 0 | 0 | 0% |

**Read the yields against the ceiling.** The same bounded attempt recovers
only 7 of 40 statements already
known true (18%). A source scoring 0% against a prover with
that recall has told you about the prover, not the source. The honest
conclusion is that conjecture yield could not be measured here, not that
the proposers produce falsehoods.

The symmetry view itself checks out: 12/12
permutations it reports as symmetries canonicalize back to the statement
they came from. That check is structural and deterministic; routing it
through the prover instead reported a weak prover as a broken view.

Nothing is recorded as refuted. There is no counter-model machinery here,
so an unreached conjecture is unresolved and nothing more.

## 11. Where the failure is: candidates or criteria?

Two candidate sources ran through all 45 grid members. One mines recurring
conjunctions of hypotheses from statements; the other mines recurring
inference steps from proof terms.

| source | candidates | best survival | mean | surviving over half | appearing once only |
|---|---|---|---|---|---|
| premise-conjunction | 201 | 14/45 | 1.65 | 0 | 132 |
| proof-role | 225 | 3/45 | 1.04 | 0 | 219 |

**The prediction was that proof-role candidates would be the more robust of
the two, and it is wrong.** They are markedly less robust: the best one
appears in 3 of 45 members against 14 of 45, and almost every one of them
appears in exactly one member and never again.

In hindsight the reason is not subtle. A role candidate is lifted from a
concrete proof subterm, and which subterms exist depends on which proofs the
search happened to build. Change the seeding and the proofs change wholesale.
Statement syntax is at least constrained by the axioms, so the same forms
recur across configurations; proof structure is far more contingent than it
looks.

Taken with sections 9 and 10, the answer to the question this sprint asked
is that the failure is not localized in the criteria or in the candidates.
A second, more mathematically motivated candidate source did worse; a
non-compression criterion could not separate any concept from seed noise;
and conjecture yield could not be measured against so weak a prover.
Automatic concept invention does not work in this setting, and that now
rests on three independent attempts to make it work rather than one.

