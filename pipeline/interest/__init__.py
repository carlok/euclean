"""An audit of an interestingness metric for theorems, run on euclean's corpus.

The metric under audit is the one defined by N. Patel, A. Rammal, A. Hayat,
R. Munos and J. Kempe, *Learning to Discover Interesting Mathematics*,
arXiv:2609.28603 (2026). Every module in this package implements part of it, or
measures it, and equation numbers in docstrings are theirs.

The question is narrow. euclean can label restatements exactly, because its
proof DAG is exact: a statement that only carries one axiom's conclusion through
the corpus can be identified from the proof terms alone. Given those labels,
does the metric rank restatements highly, and do the paper's filters catch them?

The pre-registration in `docs/interest-prereg.md` fixes every definition,
threshold and seed used here. The code follows it; where the two disagree, the
pre-registration is the contract and the code is the bug.
"""
