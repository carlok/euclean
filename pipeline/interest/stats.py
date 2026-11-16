"""Statistics for the audit, all with seeds fixed in the pre-registration.

Scores can be exact rationals far beyond float range (the unrolled proof tree),
so every comparison goes through ranks computed exactly once, and everything
downstream sees only those ranks.
"""

import math

import numpy as np
from scipy.stats import spearmanr

BOOTSTRAP = 2000
ENTROPY = 20260923  # the paper's submission date; fixed in the pre-registration
Z95 = 1.959963984540054


def rng(*keys):
    return np.random.default_rng([ENTROPY, *keys])


def exact_ranks(values):
    """Average ranks (1 = smallest), with ties sharing, on exact values."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return np.asarray(out, dtype=float)


def topk_weights(scores, k):
    """Membership weight in the top k, ties at the boundary shared fractionally.

    Breaking a tie by position would make the result depend on derivation
    order; giving every tied statement an equal share does not.
    """
    s = np.asarray(scores, dtype=float)
    n = len(s)
    if n <= k:
        return np.ones(n)
    theta = np.partition(s, n - k)[n - k]
    above = s > theta
    tied = s == theta
    w = above.astype(float)
    room = k - above.sum()
    if tied.sum():
        w[tied] = room / tied.sum()
    return w


def topk_share(scores, flags, k):
    w = topk_weights(scores, k)
    return float((w * np.asarray(flags, dtype=float)).sum() / min(k, len(w)))


def bootstrap_topk(scores, flags, k, seed_keys, b=BOOTSTRAP):
    """Percentile CI of the top-k share, resampling statements."""
    s = np.asarray(scores, dtype=float)
    f = np.asarray(flags, dtype=float)
    n = len(s)
    g = rng(*seed_keys)
    vals = np.empty(b)
    for i in range(b):
        idx = g.integers(0, n, n)
        vals[i] = topk_share(s[idx], f[idx], k)
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)


def spearman_ci(x, y, seed_keys, b=BOOTSTRAP):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    if n < 3:
        return None, None, None, n
    rho = spearmanr(x, y).statistic
    g = rng(*seed_keys)
    vals = []
    for _ in range(b):
        idx = g.integers(0, n, n)
        if np.ptp(x[idx]) == 0 or np.ptp(y[idx]) == 0:
            continue
        vals.append(spearmanr(x[idx], y[idx]).statistic)
    lo, hi = np.percentile(vals, [2.5, 97.5]) if vals else (math.nan, math.nan)
    return float(rho), float(lo), float(hi), n


def wilson(successes, n, z=Z95):
    if n == 0:
        return None, None, None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = 0.0 if successes == 0 else max(0.0, centre - half)
    hi = 1.0 if successes == n else min(1.0, centre + half)
    return p, lo, hi


def bootstrap_youden(flagged, positive, seed_keys, b=BOOTSTRAP):
    """J = recall on positives - false-positive rate on negatives, with a CI."""
    fl = np.asarray(flagged, dtype=bool)
    pos = np.asarray(positive, dtype=bool)

    def j(f, p):
        if p.sum() == 0 or (~p).sum() == 0:
            return math.nan
        return f[p].mean() - f[~p].mean()

    point = j(fl, pos)
    g = rng(*seed_keys)
    n = len(fl)
    vals = []
    for _ in range(b):
        idx = g.integers(0, n, n)
        v = j(fl[idx], pos[idx])
        if not math.isnan(v):
            vals.append(v)
    lo, hi = np.percentile(vals, [2.5, 97.5]) if vals else (math.nan, math.nan)
    return float(point), float(lo), float(hi)
