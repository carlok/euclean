# euclean

An experiment in whether higher-level structure can be recovered from the
deductive behaviour of a formal theory whose vocabulary carries no meaning.

The theory under study is given only as opaque symbols: one sort `Obj`, two
relations `R0` and `R1`, ten axioms `a0`–`a9`. No component of the pipeline is
told what any of it denotes. The interpretation exists, but it is held outside
this tree and is consulted only after discovery has been frozen.

A second, richer theory is measured alongside it as a control. Theories are
identified in every artifact by an opaque code rather than by name, since a name
useful to a reader would describe its domain.

**Start here:** [`docs/EXECUTIVE_SUMMARY.md`](docs/EXECUTIVE_SUMMARY.md) — what
was found, what did not survive scrutiny, and why the interpretation stays
unpublished. Full structural detail in
[`docs/structural-findings.md`](docs/structural-findings.md).

## Pipeline

```
axioms  ->  proved consequences  ->  structural representations  ->  clusters
        ->  generalized patterns  ->  invented concepts  ->  new conjectures
```

Lean 4 is the source of truth. Nothing counts as a theorem until the kernel
accepts it; a claim that has not compiled is a conjecture, and is filed as one.

## Layout

| Path | Contents |
|---|---|
| `theory/` | the Lean package: axioms, invented definitions, verified batches |
| `theory/spec.json` | machine-readable form of the axioms; the pipeline's only theory input |
| `pipeline/kernel/` | proof-term calculus and the Lean emitter |
| `pipeline/chainer/` | consequence generation |
| `pipeline/canon/` | normalization |
| `pipeline/views/` | multi-view theorem representations |
| `pipeline/cluster/` `patterns/` `concepts/` | unsupervised structure extraction |
| `pipeline/ensemble/` | the configuration grid, chance baselines, noise floor, grid selection |
| `pipeline/report/` | importance ranking, diagnostics, generated report figures |
| `pipeline/reverse/` | axiom footprints, subset minimisation, sufficiency checks |
| `pipeline/backward/` | goal-directed search, run alongside forward saturation |
| `pipeline/admissibility/` | the gate a candidate theory must pass before it is measured |
| `pipeline/ablation/` `conjecture/` | held-out targets, proposers and bounded attempts |
| `pipeline/loop/` | the rediscovery driver |
| `generated/` `metadata/` | per-theorem source and provenance |
| `runs/` | per-run seeds, metrics, reports |
| `tools/leakguard.py` | fails the build if the public tree acquires semantics |
| `tools/ensemble_driver.py` | drives the grid across identifier permutations |
| `tools/rescore_importance.py` | rebuilds stored rankings after a scoring change |
| `tools/migrate_theory_names.py` | renames stored artifacts when theory identity changes |
| `tools/deanonymize.py` | reads findings back through the interpretation; writes only to `secret/` |

## Setup

```bash
uv venv --python 3.12 && uv sync
```

Everything below runs under `uv run python`. The pinned interpreter is 3.12
because that is where the numerics have wheels; the pipeline itself is
version-agnostic.

## Running

Guard first — it fails the moment the public tree acquires semantics:

```bash
uv run python tools/leakguard.py
```

**This command cannot succeed on a fresh clone, by design.** Its wordlist lives
in `secret/`, which is gitignored, because a public file enumerating the
domain's vocabulary would give away the domain as surely as the vocabulary
would. Without that file the guard exits non-zero rather than reporting a clean
tree it has not actually checked. A clone therefore reproduces the pipeline but
not the quarantine; only the repository owner can verify it.

Build a corpus (generation is stochastic; the run id names the output):

```bash
uv run python -m pipeline.chainer.run --seed 0 --generations 10 --run-id main
```

Re-verify a stored corpus against the kernel without regenerating it, and
restore its per-theorem files:

```bash
uv run python -m pipeline.kernel.recheck --run main
```

Then the analysis chain, in order:

```bash
uv run python -m pipeline.views.build --run main && uv run python -m pipeline.cluster.run --run main && uv run python -m pipeline.patterns.run --run main && uv run python -m pipeline.concepts.run --run main
```

Structural importance and the public report:

```bash
uv run python -m pipeline.report.importance main && uv run python -m pipeline.report.build --run main
```

The concept-enriched rediscovery comparison:

```bash
uv run python -m pipeline.loop.run --generations 4 --top 8 --run-id loop
```

The control that removes the seeded disequality assumptions:

```bash
uv run python -m pipeline.chainer.run --seed 0 --generations 4 --run-id control-nodistinct --no-distinct
```

The configuration grid, across three anonymizations of the theory, and the
stability analysis over it:

```bash
uv run python tools/ensemble_driver.py --theory-seeds 0 1 2 --generations 2
```

```bash
uv run python -m pipeline.ensemble.stability
```

Tests:

```bash
uv run python tests/test_kernel.py && uv run python tests/test_case_analysis.py && uv run python tests/test_quarantine.py
```

## Discipline

Five things are kept distinct and are never allowed to substitute for one
another: an observed pattern, a proposed abstraction, a conjecture, a
kernel-verified theorem, and an interpretation. Negative results are reported.

## Licence

MIT — see [LICENSE](LICENSE). This covers the public tree. The interpretation of
the theory lives outside it and is not distributed.
