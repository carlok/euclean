# Interestingness against a theory with known restatements

A short note on the pre-registered audit of the interestingness metric of
Patel et al., *Learning to Discover Interesting Mathematics*
([arXiv:2609.28603](https://arxiv.org/abs/2609.28603)), run on this repository's
anonymized theories. The full report is
[`docs/interest-audit.md`](../../docs/interest-audit.md); the implementation and
labelled corpora are in [`kit/`](../../kit/).

| file | |
|---|---|
| `interest-audit.pdf` | the note |
| `interest-audit.tex` | its source |
| `extract.py` | reads every number in the note from the frozen report and from `near_duplicates.json`; writes `numbers.tex` |
| `near_duplicates.json` | output of `kit/examples/near_duplicates.py`, the one post-hoc measurement |

Nothing in the note is typed by hand. To rebuild, from the repository root:

```bash
uv run python kit/examples/near_duplicates.py --out paper/interest-audit/near_duplicates.json
```

```bash
uv run python paper/interest-audit/extract.py . paper/interest-audit
```

```bash
cd paper/interest-audit && latexmk -pdf interest-audit.tex && latexmk -c
```
