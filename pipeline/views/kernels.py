"""Weisfeiler-Lehman features over formula graphs, and embeddings fit on them.

This is §7's "graph representations, kernels" bullet, and it is deliberately not
its "learned embeddings" bullet. A pretrained text encoder would have seen
mathematics during training and could recognize these axioms through their
syntax however thoroughly the identifiers are scrubbed, which would put semantics
back into a pipeline whose entire premise is their absence. Everything here is
fit on this corpus and nothing else.

`features.wl_signature` already hashes a formula graph down to a single value,
which is the right thing for exact bucketing and the wrong thing for similarity —
two nearly identical formulas get unrelated hashes. Keeping the whole multiset of
WL labels instead gives a representation where overlap means something.
"""

import hashlib
from collections import Counter

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction import DictVectorizer
from sklearn.preprocessing import normalize

from . import features


def _h(s):
    return hashlib.blake2s(s.encode(), digest_size=8).hexdigest()


def wl_features(stmt, rounds=3):
    """Multiset of WL subtree labels, pooled across every round.

    Round 0 labels are node kinds, so they carry coarse similarity; later rounds
    carry progressively more context. Pooling all of them means the
    representation degrades gracefully — formulas that agree locally but not
    globally still land near each other.
    """
    labels, adj = features.formula_graph(stmt)
    cur = list(labels)
    out = Counter(f"r0:{lab}" for lab in cur)
    for r in range(1, rounds + 1):
        nxt = []
        for i, lab in enumerate(cur):
            neigh = sorted(f"{e}:{cur[j]}" for e, j in adj[i])
            nxt.append(_h(lab + "|" + ",".join(neigh)))
        cur = nxt
        out.update(f"r{r}:{lab}" for lab in cur)
    return out


def feature_matrix(statements, rounds=3, min_df=2):
    """Sparse WL-count matrix, L2 normalized. Features appearing in fewer than
    `min_df` statements are dropped — they are almost all one-off hashes from the
    deepest round and they otherwise dominate the dimension count."""
    counts = [dict(wl_features(s, rounds)) for s in statements]
    vec = DictVectorizer(sparse=True)
    X = vec.fit_transform(counts)

    if min_df > 1:
        keep = np.asarray((X > 0).sum(axis=0)).ravel() >= min_df
        if keep.any():
            X = X[:, keep]
    return normalize(X), vec


def svd_embedding(X, dim=32, seed=0):
    """Corpus-fit dense embedding of the WL counts."""
    dim = min(dim, X.shape[1] - 1) if X.shape[1] > 1 else 1
    model = TruncatedSVD(n_components=dim, random_state=seed)
    emb = model.fit_transform(X)
    return emb, float(model.explained_variance_ratio_.sum())


def gram(X):
    """Cosine kernel. Rows are already L2 normalized, so this is a plain inner
    product, and it is non-negative because the counts are — which is what
    spectral clustering needs from an affinity."""
    G = (X @ X.T).toarray() if hasattr(X @ X.T, "toarray") else np.asarray(X @ X.T)
    np.clip(G, 0.0, None, out=G)
    return G
