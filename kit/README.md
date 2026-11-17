# interestkit

An open, tested implementation of the interestingness quantities of
N. Patel, A. Rammal, A. Hayat, R. Munos, J. Kempe, *Learning to Discover
Interesting Mathematics* ([arXiv:2609.28603](https://arxiv.org/abs/2609.28603)),
over a plain JSON library format, plus a small benchmark with exact ground truth
on which statements merely restate an axiom.

Not affiliated with or endorsed by the paper's authors. The paper released no
code; everything here follows its text, and every choice the text leaves open is
a named parameter, not a hidden default.

## What is in it

| module | what |
|---|---|
| `interestkit/library.py` | the input format: declarations, what each proof cites, the cost of each step |
| `interestkit/metric.py` | L(T\|P) (Eq. 5), V(T\|P) by premise expansion, I(T\|P) and I₀ (Eq. 6), U₀ (Eq. 7), the reward with its penalties (Eq. 8) |
| `interestkit/filters.py` | relevance and restatement filters (App. C.1.2), with a threshold sweep; triviality is a callback |
| `interestkit/loop.py` | the growth loop (Sec. 3.4, App. D) with the paper's promotion rules |
| `interestkit/evaluate.py` | checks for any score against ground truth: top-k enrichment, filter recall and false-positive rate, Spearman, near-duplicate share |
| `data/euclean/` | 12 corpora in this format, with frozen restatement labels |
| `examples/near_duplicates.py` | one analysis, run end to end on the data |

Standard library only, Python 3.10 or later.

## Choices the paper leaves open

- **Premise expansion.** Each lemma in the closure is paid for once
  (`mode="dag"`, the reading of the paper's update rule), or once per citation
  (`mode="tree"`, the proof tree unrolled).
- **Statement size.** Characters as written (`metric.s_raw`, the paper's), or
  with identifiers collapsed to one symbol (`metric.s_canon`), which removes the
  advantage short names give.
- **The restatement filter.** The paper gives neither measure nor threshold.
  Here: token-set Jaccard similarity to the most similar premise, threshold
  0.70 by default. Run `filters.sweep` before trusting one value.
- **The reward's logarithm.** Natural log assumed.

## The input format

JSON Lines. The first line is a header with the definitions; every other line is
a declaration, listed after everything it cites. See `interestkit/library.py`
for the full description. A minimal library:

```json
{"format": "interestkit-library/1", "costs": ["loc"], "definitions": {"Obj": {"statement": "Type", "uses": []}, "R": {"statement": "Obj → Obj → Prop", "uses": ["Obj"]}}, "meta": {}}
{"name": "a0", "axiom": true, "statement": "∀ (x : Obj), R x x", "uses": ["Obj", "R"]}
{"name": "t1", "statement": "∃ (x : Obj), R x x", "uses": ["Obj", "R"], "premises": {"a0": 1}, "cost": {"loc": 2}}
```

Anything that can say what each proof cites and what each proof step costs can
be put in this form: a slice of Mathlib, a Lean project, the output of a prover.

## Use

```python
import sys; sys.path.insert(0, "kit")
from interestkit import Library, metric, evaluate

lib = Library.load("kit/data/euclean/interest-t0f85211-p0-s0.jsonl")
i0 = metric.i0(lib, cost="loc", mode="dag")              # exact Fractions
restated = {d["name"]: d["label"] != "N" for d in lib.theorems()}
print(evaluate.topk_enrichment({n: metric.log10(v) for n, v in i0.items()}, restated, k=50))
```

Any other scoring rule goes through the same checks: give `topk_enrichment` a
dict of scores.

## The data

`data/euclean/` holds the corpora of a pre-registered audit of this metric,
run on two small first-order theories under opaque names (one sort, a few
relations, 10 and 15 axioms), three identifier permutations and two seeds each.
Every statement was checked by the Lean 4 kernel. Each carries a label computed
from exact proof dependencies and frozen by hash before any score existed:

| label | meaning |
|---|---|
| `R0` | an axiom's conclusion, up to canonical form |
| `R1` | rests on a single axiom; follows by instantiation and argument permutation |
| `R2` | every proof supporting it cites the axiom whose conclusion it is |
| `N` | not a restatement |

Under `reference`, each declaration also carries the values the audit computed.
`tests/test_kit_data.py` recomputes them from the library alone and requires
exact agreement, so the code here is the audited metric, not an approximation of
it. The audit itself, with its pre-registration and verdicts, is
[`docs/interest-audit.md`](../docs/interest-audit.md).

What the theories are about is withheld on purpose; see the repository's
[`README`](../README.md).

## Licence

MIT, as the rest of the repository.
