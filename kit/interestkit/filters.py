"""The relevance, restatement and triviality filters (paper, App. C.1.2).

The paper says: a proposal must share at least one non-generic identifier with
its premise and definition context, else -0.25; "direct premise restatements
(as measured by token-level similarity) are marked trivial"; and anything
closed by assumption, rfl, simp, tauto or simp_all scores 0.

It gives neither the similarity measure nor the threshold. What is here is one
explicit reading, with both choices exposed as parameters: token-set Jaccard
similarity to the most similar premise, threshold 0.70 by default (the value
the paper uses for token-set Jaccard in App. C.2.1, for another purpose). Run
`sweep` before trusting any single threshold: in a small signature most
statements share most of their tokens with some premise, and the filter then
removes nearly everything.

Triviality needs a prover. It is taken here as a callback or a precomputed set.
"""

import re

TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*|[0-9]+|\S")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*")
LEAN_BINDER = re.compile(r"[∀∃]\s*\(?([^,:()]+?)\s*:")

THRESHOLD = 0.70
SWEEP = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.00)
TACTICS = ("assumption", "rfl", "simp", "tauto", "simp_all")


def tokens(text):
    return TOKEN.findall(text)


def unigrams(text):
    return frozenset(tokens(text))


def bigrams(text):
    t = tokens(text)
    return frozenset(zip(t, t[1:]))


TOKENIZERS = {"unigram": unigrams, "bigram": bigrams}


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def max_similarity(text, premise_texts, tokenizer=unigrams):
    """Largest token-set Jaccard similarity to any premise; 0.0 with none."""
    mine = tokenizer(text)
    best = 0.0
    for p in premise_texts:
        s = jaccard(mine, tokenizer(p))
        if s > best:
            best = s
            if best == 1.0:
                break
    return best


def is_restatement(text, premise_texts, threshold=THRESHOLD, tokenizer=unigrams):
    return max_similarity(text, premise_texts, tokenizer) >= threshold


def lean_bound_names(text):
    """Variables bound by ∀/∃ in a Lean-style statement, by pattern, not parsing."""
    out = set()
    for group in LEAN_BINDER.findall(text):
        out.update(group.split())
    return out


def is_relevant(text, context_texts, generic=()):
    """At least one identifier, other than `generic` ones and the statement's
    own bound variables, shared with the context."""
    mine = set(IDENT.findall(text)) - set(generic) - lean_bound_names(text)
    ctx = set()
    for c in context_texts:
        ctx |= set(IDENT.findall(c))
    return bool(mine & ctx)


def sweep(texts_and_contexts, flags, thresholds=SWEEP, tokenizer=unigrams):
    """Recall on flagged items and false-positive rate on the rest, per threshold.

    `texts_and_contexts` is a list of (statement, premise statements);
    `flags` the ground truth, aligned with it.
    """
    sims = [max_similarity(t, ctx, tokenizer) for t, ctx in texts_and_contexts]
    pos = sum(flags)
    neg = len(flags) - pos
    out = []
    for th in thresholds:
        hit = [s >= th for s in sims]
        tp = sum(1 for h, f in zip(hit, flags) if h and f)
        fp = sum(1 for h, f in zip(hit, flags) if h and not f)
        out.append({"threshold": th,
                    "recall": tp / pos if pos else None,
                    "fpr": fp / neg if neg else None,
                    "flagged": sum(hit)})
    return out
