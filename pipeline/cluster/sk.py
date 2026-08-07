"""scikit-learn clustering, alongside the hand-rolled baselines in `methods.py`.

`methods.py` stays. It beat a shuffled null in sprint 1 and §7 asks for a
comparison of representations rather than a single blessed one, so the longhand
implementations remain as a documented baseline the library results are checked
against.

Two things here are genuine improvements rather than reimplementations:

  * average linkage instead of single linkage. Single linkage chains, and on the
    dependency view that produced one component holding most of the corpus.
  * density clustering, which is allowed to call a theorem noise instead of
    forcing every point into some cluster.

Everything is fit on this corpus alone. Nothing pretrained is used anywhere in
the pipeline, deliberately — see `views/kernels.py`.
"""

import numpy as np
from sklearn.cluster import HDBSCAN, AgglomerativeClustering, KMeans, SpectralClustering
from sklearn.metrics import (
    adjusted_rand_score,
    normalized_mutual_info_score,
    silhouette_score,
)


def jaccard_matrix(sets):
    """Dense pairwise Jaccard distance. n is a couple of thousand, so a dense
    matrix is a few tens of MB and simpler than anything sparse."""
    n = len(sets)
    universe = sorted({x for s in sets for x in s})
    index = {x: i for i, x in enumerate(universe)}
    membership = np.zeros((n, len(universe)), dtype=bool)
    for i, s in enumerate(sets):
        for x in s:
            membership[i, index[x]] = True

    inter = membership.astype(np.float32) @ membership.astype(np.float32).T
    sizes = membership.sum(axis=1).astype(np.float32)
    union = sizes[:, None] + sizes[None, :] - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(union > 0, inter / union, 0.0)
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)
    return dist.astype(np.float64)


def kmeans(matrix, k, seed=0):
    X = np.asarray(matrix, dtype=np.float64)
    k = min(k, len(X))
    model = KMeans(n_clusters=k, random_state=seed, n_init=10)
    return model.fit_predict(X).tolist()


def average_linkage(dist, threshold=0.34):
    model = AgglomerativeClustering(
        n_clusters=None,
        metric="precomputed",
        linkage="average",
        distance_threshold=threshold,
    )
    return model.fit_predict(dist).tolist()


def density(dist, min_cluster_size=5):
    """HDBSCAN on the precomputed distance. Label -1 means noise, and that is a
    useful answer: a theorem that belongs to no family is information.

    `copy=True` is not optional here. With the current default HDBSCAN rewrites
    the distance matrix in place, so every method scored after this one would be
    scored against a corrupted matrix — silently, since the result is still a
    well-formed array. It becomes the default in sklearn 1.10; setting it
    explicitly keeps the behaviour pinned either way.
    """
    model = HDBSCAN(metric="precomputed", min_cluster_size=min_cluster_size, copy=True)
    return model.fit_predict(dist).tolist()


def spectral(gram, k, seed=0):
    model = SpectralClustering(
        n_clusters=k, affinity="precomputed", random_state=seed, assign_labels="kmeans"
    )
    return model.fit_predict(np.asarray(gram, dtype=np.float64)).tolist()


# --- quality ---------------------------------------------------------------


def silhouette(dist, labels):
    """Silhouette on the precomputed distance, ignoring noise and degenerate
    labelings. Returns None when the score is undefined rather than a number
    that would be quietly meaningless."""
    labels = np.asarray(labels)
    keep = labels != -1
    if keep.sum() < 3:
        return None
    sub, lab = np.asarray(dist)[np.ix_(keep, keep)], labels[keep]
    if len(set(lab.tolist())) < 2 or len(set(lab.tolist())) >= len(lab):
        return None
    return float(silhouette_score(sub, lab, metric="precomputed"))


def nmi(a, b):
    return float(normalized_mutual_info_score(a, b))


def ari(a, b):
    return float(adjusted_rand_score(a, b))


def label_stats(labels):
    labels = np.asarray(labels)
    real = labels[labels != -1]
    _, counts = np.unique(real, return_counts=True)
    return {
        "clusters": int(len(counts)),
        "largest": int(counts.max()) if len(counts) else 0,
        "singletons": int((counts == 1).sum()),
        "noise": int((labels == -1).sum()),
    }


def l2_distance_matrix(matrix):
    """Pairwise L2 distance, for scoring a method in the space it used.

    Named for the norm rather than the geometer: the guard rejects the latter,
    and it is right to — a domain word in the discovery pipeline is a domain
    word regardless of how standard it is elsewhere."""
    X = np.asarray(matrix, dtype=np.float64)
    sq = (X * X).sum(axis=1)
    d2 = sq[:, None] + sq[None, :] - 2.0 * (X @ X.T)
    np.clip(d2, 0.0, None, out=d2)
    d = np.sqrt(d2)
    np.fill_diagonal(d, 0.0)
    return d
