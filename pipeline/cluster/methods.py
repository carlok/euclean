"""Three clustering mechanisms over three different views.

They are kept deliberately different rather than three tunings of one idea. If
the same families show up under a numeric k-means on proof shape, a linkage
clustering on which axioms a proof cites, and an exact bucketing on formula
structure, that agreement means something. If they disagree completely, that
means something too, and it should be reported rather than tuned away.

Pure Python on purpose — the corpus is small enough that a dependency on a
numerics stack would cost more than it buys.
"""

import math
import random


# --- k-means over standardized numeric features --------------------------


def _dist2(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def kmeans(matrix, k, seed=0, iterations=40):
    rng = random.Random(seed)
    n = len(matrix)
    k = min(k, n)

    # k-means++ seeding: spread the initial centres out, otherwise a couple of
    # dense syntactic families swallow every centre and the rest is one blob
    centres = [list(matrix[rng.randrange(n)])]
    while len(centres) < k:
        d = [min(_dist2(p, c) for c in centres) for p in matrix]
        total = sum(d)
        if total <= 0:
            centres.append(list(matrix[rng.randrange(n)]))
            continue
        r, acc = rng.random() * total, 0.0
        for i, w in enumerate(d):
            acc += w
            if acc >= r:
                centres.append(list(matrix[i]))
                break

    assign = [0] * n
    for _ in range(iterations):
        changed = False
        for i, p in enumerate(matrix):
            best = min(range(k), key=lambda c: _dist2(p, centres[c]))
            if best != assign[i]:
                assign[i] = best
                changed = True
        sums = [[0.0] * len(matrix[0]) for _ in range(k)]
        counts = [0] * k
        for i, p in enumerate(matrix):
            counts[assign[i]] += 1
            row = sums[assign[i]]
            for j, x in enumerate(p):
                row[j] += x
        for c in range(k):
            if counts[c]:
                centres[c] = [x / counts[c] for x in sums[c]]
        if not changed:
            break
    return assign


def kmeans_inertia(matrix, assign):
    k = max(assign) + 1
    centres = [[0.0] * len(matrix[0]) for _ in range(k)]
    counts = [0] * k
    for p, a in zip(matrix, assign):
        counts[a] += 1
        for j, x in enumerate(p):
            centres[a][j] += x
    for c in range(k):
        if counts[c]:
            centres[c] = [x / counts[c] for x in centres[c]]
    return sum(_dist2(p, centres[a]) for p, a in zip(matrix, assign))


# --- linkage clustering over dependency sets ------------------------------


def jaccard(a, b):
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b)


def single_linkage(sets, threshold=0.34):
    """Connected components of the graph joining sets closer than `threshold`.

    Single linkage chains, which is usually a vice. Here it is roughly what we
    want: theorems proved from overlapping axiom sets should end up together
    even when no two of them are individually close.
    """
    n = len(sets)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if jaccard(sets[i], sets[j]) <= threshold:
                a, b = find(i), find(j)
                if a != b:
                    parent[max(a, b)] = min(a, b)

    labels, out = {}, []
    for i in range(n):
        r = find(i)
        if r not in labels:
            labels[r] = len(labels)
        out.append(labels[r])
    return out


# --- exact structural bucketing -------------------------------------------


def bucket(signatures):
    labels, out = {}, []
    for s in signatures:
        if s not in labels:
            labels[s] = len(labels)
        out.append(labels[s])
    return out


# --- quality against a null model ----------------------------------------


def cohesion(assign, sets):
    """Mean within-cluster Jaccard similarity, ignoring singletons."""
    groups = {}
    for i, a in enumerate(assign):
        groups.setdefault(a, []).append(i)
    scores, weights = [], []
    for members in groups.values():
        if len(members) < 2:
            continue
        pairs = [
            1.0 - jaccard(sets[i], sets[j])
            for idx, i in enumerate(members)
            for j in members[idx + 1 :]
        ]
        if pairs:
            scores.append(sum(pairs) / len(pairs))
            weights.append(len(members))
    if not scores:
        return 0.0
    return sum(s * w for s, w in zip(scores, weights)) / sum(weights)


def shuffled_baseline(assign, sets, seed=0, trials=5):
    """The same cluster sizes, filled at random. Anything a clustering reports
    has to beat this or it is reporting the size distribution, not structure."""
    rng = random.Random(seed)
    out = []
    for _ in range(trials):
        shuffled = list(assign)
        rng.shuffle(shuffled)
        out.append(cohesion(shuffled, sets))
    return sum(out) / len(out)


def entropy_agreement(a, b):
    """Normalized mutual information between two labelings."""
    n = len(a)
    ca, cb, cab = {}, {}, {}
    for x, y in zip(a, b):
        ca[x] = ca.get(x, 0) + 1
        cb[y] = cb.get(y, 0) + 1
        cab[(x, y)] = cab.get((x, y), 0) + 1

    def H(counts):
        return -sum((c / n) * math.log(c / n) for c in counts.values() if c)

    ha, hb = H(ca), H(cb)
    mi = 0.0
    for (x, y), c in cab.items():
        p = c / n
        mi += p * math.log(p / ((ca[x] / n) * (cb[y] / n)))
    denom = math.sqrt(ha * hb)
    return mi / denom if denom > 0 else 0.0
