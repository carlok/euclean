# Sprint 3 design — is the failure in the candidates or in the criteria?

Date: 2026-08-07

## Problem

Sprint 2 established that no invented definition survives re-configuration. The
best-surviving one appears in 14 of 45 grid members, and six of the top ten never
appear at all unless disequalities are assumed. A restatement check sharpened it:
only 11 of 402 candidates in a representative member are independent of any
single axiom.

That verdict rests on a narrow evidence base. Every criterion currently computed
belongs to one family — description size, coverage, cluster spread. All of them
measure compression. The governing brief also lists reduction of search
complexity, ability to generate successful conjectures, and predictive ability,
and none of those was built. The accurate summary of sprint 2 is therefore:
*compression was falsified as a criterion, and the alternatives were never
tested.*

A second gap sits alongside it. Concept candidates come only from recurring
conjunctions of hypotheses, which is a syntactic notion of concept.
`pipeline/patterns/motifs.py` has computed which proof rule feeds which since
sprint 1 and has never been connected to concept proposal.

## Question

Is concept invention failing because the criteria are wrong, because the
candidates are wrong, or both?

## Falsifiable claim

Concepts derived from recurring proof roles survive re-seeding better than
concepts derived from recurring statement syntax, because proof structure depends
less than statement syntax on which atoms happened to be assumed.

The sprint-2 configuration grid tests this without modification. A null or
reversed result is reported as such.

## Scope

In: proof-role candidate mining; a held-out target set and per-concept ablation;
conjecture generation as a scoring input; re-scoring and a grid comparison of the
two candidate sources.

Out, and deferred deliberately: representation invariance across a second
encoding, a control domain, and any mode in which a language model inspects the
anonymous formulas.

Unchanged: the same axiom fragment, a symbolic chainer emitting proof terms,
and structure-only discovery with no language model inspecting the formulas.

## Components

**Role mining** (`pipeline/concepts/roles.py`). Frequent application motifs are
mined from `motifs.applications`, keyed by `(rule, argument-head tuple)` and
counted per theorem so that a motif repeated inside a single proof does not read
as widespread. Each frequent motif is turned into the composite lemma it
packages, with variables abstracted through the existing `invent.abstract`, and
emitted in the record form `invent.score` already consumes, tagged
`source="proof-role"`.

Role candidates are derived lemmas rather than definitions. A recurring proof
pattern is a reusable inference step, and the existing machinery already promotes
lemmas into the rule set. Consequence: the two sources are directly comparable on
acceleration, where both enter the environment as rules, and are *not* comparable
on description size. The report must not put them in one table on that axis.

The restatement check applies to role candidates unchanged. A motif that always
routes through one axiom is that axiom.

**Targets and ablation** (`pipeline/ablation/`). A target set is built once from a
deep run — statements that are existential-free, high in structural importance,
and first reached late — stored as arity-canonical keys so it survives identifier
permutation. A calibration gate requires the baseline to reach roughly 20–60% of
targets; all-or-nothing means the set measures nothing, and that is caught at
build time. Per concept, the chainer runs at a fixed tight budget with and
without that concept's rules, and targets reached are counted by canonical key.

Held-out targets rather than raw yield, because this generator emits large
volumes of weak existentials: raw yield rises when search degrades, whereas a
pre-committed target set cannot be gamed that way.

**Conjecture generation** (`pipeline/conjecture/`). Three sources, all reusing
existing machinery: permutations that `views/symmetry.py` reports are *not*
symmetries (which should fail) alongside ones it reports are (which should
succeed), giving a two-sided check of the symmetry view itself; hole completion
over `patterns/antiunify.py` schemas; and hypothesis dropping from verified
theorems. Each is attempted at a small budget, successes are kernel-verified, and
failures are recorded with their source.

**Scoring and comparison.** `invent.score` gains `targets_delta` and
`conjecture_yield`. The ensemble runs with both candidate sources across three
theory seeds, and `pipeline/ensemble/stability.py` — unchanged — compares survival
rates across the two sources.

## Verification

Guard and quarantine tests; the existing kernel and case-analysis gates plus new
tests for roles and conjectures; target-set calibration recorded in the artifact;
every reported proof kernel-verified; every conjecture failure recorded with its
source; `leakguard` clean and `secret/` absent from git history.

One gate deserves separate mention. If every concept scores `delta = 0` under
ablation, the criterion is dead, and the sprint reports that rather than
presenting a table of zeros as a finding.

## Expected outcomes

Three are possible and all are publishable. Role concepts prove more robust,
which supports the claim and suggests concept invention needs a
proof-structural rather than syntactic notion of candidate. They prove no
different, which localizes the failure in the criteria. Or they prove less
robust, which is the most interesting and the least convenient, and would suggest
that the corpus itself — not the mining strategy — is what varies.

If neither new criterion separates concepts better than compression did, the
conclusion is that automatic concept invention does not work in this setting.
That is a stronger and more useful claim than sprint 2 could make.
